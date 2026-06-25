"""QA phase — run, report, and re-run with feedback (tenant-scoped)."""
from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_tenant
from app.core.db import SessionLocal, get_db
from app.models import AnalysisJob, Finding, Hunt, QAReport, Tenant
from app.schemas import JobOut
from app.services import jobs, qa_runner

router = APIRouter(
    prefix="/api/tenants/{tenant_id}/hunts/{hunt_id}/qa", tags=["qa"]
)


def _resolve_hunt(db: Session, tenant: Tenant, hunt_id: int) -> Hunt:
    hunt = db.get(Hunt, hunt_id)
    if not hunt or hunt.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Hunt not found")
    return hunt


@router.get("")
def get_qa(
    hunt_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Latest QA report + per-finding QA state."""
    _resolve_hunt(db, tenant, hunt_id)
    report = (
        db.query(QAReport)
        .filter_by(tenant_id=tenant.id, hunt_id=hunt_id)
        .order_by(QAReport.id.desc())
        .first()
    )
    findings = (
        db.query(Finding)
        .filter_by(tenant_id=tenant.id, hunt_id=hunt_id)
        .filter(Finding.merged_into_id.is_(None))
        .order_by(Finding.id)
        .all()
    )
    return {
        "hunt_id": hunt_id,
        "report": None if report is None else {
            "status": report.status,
            "stage_checks": report.stage_checks,
            "totals": report.totals,
            "critical_issues": report.critical_issues,
            "actions": report.actions,
            "created_at": report.created_at,
        },
        "findings": [
            {"ref": f.finding_ref, "title": f.title, "category": f.category,
             "severity": f.severity, "qa": f.qa}
            for f in findings
        ],
    }


@router.post("/run", response_model=JobOut, status_code=202)
def run_qa_phase(
    hunt_id: int,
    background: BackgroundTasks,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
    feedback: str | None = Body(default=None, embed=True),
):
    """Start (or re-attach to) the QA phase. Optional reviewer feedback guides it."""
    _resolve_hunt(db, tenant, hunt_id)
    existing = jobs.active_job(db, tenant_id=tenant.id, hunt_id=hunt_id, phase="qa")
    if existing:
        return existing

    job = AnalysisJob(tenant_id=tenant.id, hunt_id=hunt_id, phase="qa", status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)

    def _task(job_id: int, fb: str | None):
        task_db = SessionLocal()
        try:
            qa_runner.run_qa(task_db, job_id, feedback=fb)
        finally:
            task_db.close()

    background.add_task(_task, job.id, feedback)
    return job


@router.post("/rollback")
def rollback_qa_changes(
    hunt_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Undo the automatic gap-fill edits made by the latest QA run."""
    _resolve_hunt(db, tenant, hunt_id)
    return qa_runner.rollback_qa(db, hunt_id, tenant.id)
