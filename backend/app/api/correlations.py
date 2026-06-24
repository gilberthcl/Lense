"""Cross-dataset entity correlation + the correlation PHASE (tenant-scoped)."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_tenant
from app.core.db import SessionLocal, get_db
from app.models import AnalysisJob, Dataset, Finding, Hunt, Incident, Tenant
from app.schemas import JobOut
from app.services import correlation, correlation_runner, jobs

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


@router.post("/run", response_model=JobOut, status_code=202)
def run_correlation_phase(
    hunt_id: int,
    background: BackgroundTasks,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Start (or re-attach to) the correlation phase for the hunt."""
    hunt = db.get(Hunt, hunt_id)
    if not hunt or hunt.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Hunt not found")

    existing = jobs.active_job(
        db, tenant_id=tenant.id, hunt_id=hunt_id, phase="correlation"
    )
    if existing:
        return existing

    job = AnalysisJob(
        tenant_id=tenant.id, hunt_id=hunt_id, phase="correlation", status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    def _task(job_id: int):
        task_db = SessionLocal()
        try:
            correlation_runner.run_correlation(task_db, job_id)
        finally:
            task_db.close()

    background.add_task(_task, job.id)
    return job
