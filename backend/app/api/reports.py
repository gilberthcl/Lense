"""DOCX report generation endpoint (tenant-scoped, bilingual)."""
from datetime import datetime, timezone

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import get_tenant
from app.core.db import get_db
from app.models import AnalysisJob, Dataset, Finding, Hunt, Tenant
from app.services import report_docx

router = APIRouter(prefix="/api/tenants/{tenant_id}/hunts/{hunt_id}/report", tags=["reports"])

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def _finding_to_dict(f: Finding) -> dict:
    return {
        "id": f.id,
        "finding_ref": f.finding_ref,
        "title": f.title,
        "category": f.category,
        "severity": f.severity,
        "confidence": f.confidence,
        "status": f.status,
        "summary": f.summary,
        "evidence": f.evidence,
        "mitre": f.mitre,
        "affected_assets": f.affected_assets,
        "affected_users": f.affected_users,
        "recommendations": f.recommendations,
        "dataset_id": f.dataset_id,
    }


def _latest_assessments(db: Session, tenant_id: int, hunt_id: int) -> dict[int, str]:
    """Most recent completed analysis assessment per dataset."""
    jobs = (
        db.query(AnalysisJob)
        .filter_by(tenant_id=tenant_id, hunt_id=hunt_id, phase="analysis", status="done")
        .order_by(desc(AnalysisJob.created_at))
        .all()
    )
    out: dict[int, str] = {}
    for job in jobs:
        if job.dataset_id is None or job.dataset_id in out:
            continue
        result = job.result or {}
        if isinstance(result, dict) and result.get("assessment"):
            out[job.dataset_id] = result["assessment"]
    return out


def _lang_from_hunt(hunt: Hunt) -> str:
    """Map the hunt's report_language to the report's en/es switch."""
    lang = (hunt.report_language or "").strip().lower()
    return "es" if lang.startswith(("es", "spa", "español", "espanol")) else "en"


@router.get("")
def generate_report(
    hunt_id: int,
    lang: Optional[str] = Query(None, pattern="^(en|es)$"),
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    hunt = db.get(Hunt, hunt_id)
    if not hunt or hunt.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Hunt not found")
    # Default to the hunt's configured report language unless overridden.
    lang = lang or _lang_from_hunt(hunt)

    findings = (
        db.query(Finding)
        .filter_by(tenant_id=tenant.id, hunt_id=hunt_id)
        .order_by(Finding.finding_ref)
        .all()
    )
    datasets = (
        db.query(Dataset)
        .filter_by(tenant_id=tenant.id, hunt_id=hunt_id)
        .order_by(Dataset.created_at)
        .all()
    )
    assessments = _latest_assessments(db, tenant.id, hunt_id)

    docx_bytes = report_docx.build_report(
        tenant_name=tenant.name,
        hunt={"name": hunt.name, "objective": hunt.objective},
        findings=[_finding_to_dict(f) for f in findings],
        datasets=[
            {"dataset_id": d.id, "filename": d.filename, "assessment": assessments.get(d.id)}
            for d in datasets
        ],
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        lang=lang,
    )

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in hunt.name)[:60]
    filename = f"lens_report_{safe_name or hunt_id}_{lang}.docx"
    return Response(
        content=docx_bytes,
        media_type=DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
