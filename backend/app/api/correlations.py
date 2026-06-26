"""Cross-dataset entity correlation + the correlation PHASE (tenant-scoped)."""
from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_tenant
from app.core.db import SessionLocal, get_db
from app.models import AnalysisJob, Dataset, Finding, Hunt, Incident, Tenant
from app.schemas import JobOut
from app.services import correlation, correlation_runner, jobs, learning

router = APIRouter(
    prefix="/api/tenants/{tenant_id}/hunts/{hunt_id}/correlations", tags=["correlations"]
)


def _finding_to_dict(f: Finding) -> dict:
    return {
        "id": f.id,
        "finding_ref": f.finding_ref,
        "title": f.title,
        "category": f.category,
        "dataset_id": f.dataset_id,
        "affected_assets": f.affected_assets,
        "affected_users": f.affected_users,
        "evidence": f.evidence,
    }


@router.get("")
def get_correlations(
    hunt_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    hunt = db.get(Hunt, hunt_id)
    if not hunt or hunt.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Hunt not found")

    findings = (
        db.query(Finding).filter_by(tenant_id=tenant.id, hunt_id=hunt_id).all()
    )
    datasets = db.query(Dataset).filter_by(tenant_id=tenant.id, hunt_id=hunt_id).all()
    dataset_names = {d.id: d.filename for d in datasets}

    result = correlation.compute_correlations(
        (_finding_to_dict(f) for f in findings), dataset_names
    )
    result["hunt_id"] = hunt_id
    return result


def _incident_to_dict(inc: Incident, ref_by_id: dict[int, str]) -> dict:
    return {
        "id": inc.id,
        "title": inc.title,
        "narrative": inc.narrative,
        "severity": inc.severity,
        "confidence": inc.confidence,
        "mitre_chain": inc.mitre_chain,
        "timeline": inc.timeline,
        "finding_ids": inc.finding_ids,
        "finding_refs": [ref_by_id.get(i) for i in (inc.finding_ids or [])],
        "created_at": inc.created_at,
    }


@router.get("/incidents")
def list_incidents(
    hunt_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Correlation-phase incidents (attack-chains) for the hunt."""
    hunt = db.get(Hunt, hunt_id)
    if not hunt or hunt.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Hunt not found")
    incidents = (
        db.query(Incident)
        .filter_by(tenant_id=tenant.id, hunt_id=hunt_id)
        .order_by(Incident.id)
        .all()
    )
    ref_by_id = {
        f.id: f.finding_ref
        for f in db.query(Finding).filter_by(tenant_id=tenant.id, hunt_id=hunt_id).all()
    }
    return {
        "hunt_id": hunt_id,
        "incidents": [_incident_to_dict(i, ref_by_id) for i in incidents],
    }


@router.get("/summary")
def correlation_summary(
    hunt_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """What the correlation phase did: incidents built, findings merged/enriched."""
    hunt = db.get(Hunt, hunt_id)
    if not hunt or hunt.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Hunt not found")

    findings = db.query(Finding).filter_by(tenant_id=tenant.id, hunt_id=hunt_id).all()
    by_id = {f.id: f for f in findings}
    ref_by_id = {f.id: f.finding_ref for f in findings}

    merged = []
    for f in findings:
        if f.merged_into_id:
            survivor = by_id.get(f.merged_into_id)
            merged.append({
                "finding_id": f.id,
                "ref": f.finding_ref,
                "title": f.title,
                "into_ref": survivor.finding_ref if survivor else None,
                "into_title": survivor.title if survivor else None,
            })

    enriched = []
    for f in findings:
        if f.enrichment:
            enriched.append({
                "ref": f.finding_ref,
                "title": f.title,
                "note": (f.enrichment or {}).get("note"),
                "corroborating_datasets": (f.enrichment or {}).get("corroborating_datasets"),
            })

    incidents = (
        db.query(Incident)
        .filter_by(tenant_id=tenant.id, hunt_id=hunt_id)
        .order_by(Incident.id)
        .all()
    )
    active = [f for f in findings if not f.merged_into_id]
    # The FINAL curated set — what survives after correlation is applied. Merged
    # duplicates are dropped; each survivor is flagged if it was enriched or is
    # part of an attack-chain. This is the "Applied correlation" view.
    sev_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4}
    curated = [
        {
            "id": f.id,
            "ref": f.finding_ref,
            "title": f.title,
            "category": f.category,
            "severity": f.severity,
            "enriched": bool(f.enrichment),
            "in_chain": f.chain_id is not None,
            "chain_id": f.chain_id,
        }
        for f in sorted(active, key=lambda f: (sev_rank.get((f.severity or "").lower(), 5), f.id))
    ]
    return {
        "hunt_id": hunt_id,
        "totals": {
            "findings": len(findings),
            "active_findings": len(active),
            "incidents": len(incidents),
            "merged": len(merged),
            "enriched": len(enriched),
        },
        "incidents": [_incident_to_dict(i, ref_by_id) for i in incidents],
        "merged": merged,
        "enriched": enriched,
        "curated": curated,
    }


@router.post("/findings/{finding_id}/unmerge")
def unmerge_finding(
    hunt_id: int,
    finding_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Undo a correlation merge — restore the finding as a separate item."""
    f = db.get(Finding, finding_id)
    if not f or f.tenant_id != tenant.id or f.hunt_id != hunt_id:
        raise HTTPException(status_code=404, detail="Finding not found")
    f.merged_into_id = None
    if f.status == "merged":
        f.status = "draft"
    db.commit()
    return {"ok": True, "finding_id": finding_id}


def _record_correlation_feedback(tenant_id: int, hunt_id: int, feedback: str) -> None:
    db = SessionLocal()
    try:
        learning.record_event(
            db, tenant_id=tenant_id, hunt_id=hunt_id, stage="correlation",
            source="live_feedback", target_type="correlation", feedback_text=feedback,
        )
    finally:
        db.close()


@router.post("/run", response_model=JobOut, status_code=202)
def run_correlation_phase(
    hunt_id: int,
    background: BackgroundTasks,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
    feedback: str | None = Body(default=None, embed=True),
):
    """Start (or re-attach to) the correlation phase for the hunt. When `feedback`
    is given, the model REDOES the correlation addressing it (re-correlate with
    feedback), and the correction is recorded as a learning signal."""
    hunt = db.get(Hunt, hunt_id)
    if not hunt or hunt.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Hunt not found")

    existing = jobs.active_job(
        db, tenant_id=tenant.id, hunt_id=hunt_id, phase="correlation"
    )
    if existing:
        return existing

    fb = (feedback or "").strip() or None
    job = AnalysisJob(
        tenant_id=tenant.id, hunt_id=hunt_id, phase="correlation", status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    if fb:
        background.add_task(_record_correlation_feedback, tenant.id, hunt_id, fb)

    def _task(job_id: int, feedback_text: str | None = fb):
        task_db = SessionLocal()
        try:
            correlation_runner.run_correlation(task_db, job_id, feedback=feedback_text)
        finally:
            task_db.close()

    background.add_task(_task, job.id)
    return job
