"""Global jobs view (for the Config → Jobs panel) + cancel."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import AnalysisJob, Hunt, Tenant
from app.services import jobs

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _serialize(job: AnalysisJob, tenant_name: str | None, hunt_name: str | None) -> dict:
    return {
        "id": job.id,
        "tenant_id": job.tenant_id,
        "tenant_name": tenant_name,
        "hunt_id": job.hunt_id,
        "hunt_name": hunt_name,
        "dataset_id": job.dataset_id,
        "phase": job.phase,
        "status": job.status,
        "progress": job.progress,
        "current_task": job.current_task,
        "model": job.model,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


@router.get("")
def list_jobs(active: bool = False, limit: int = 40, db: Session = Depends(get_db)):
    """Recent jobs across all clients (active first). For the Jobs admin view."""
    q = db.query(AnalysisJob)
    if active:
        q = q.filter(AnalysisJob.status.in_(jobs.ACTIVE))
    rows = q.order_by(AnalysisJob.created_at.desc()).limit(max(1, min(limit, 200))).all()
    names_t = dict(db.query(Tenant.id, Tenant.name).all())
    names_h = dict(db.query(Hunt.id, Hunt.name).all())
    # active jobs first, then by recency
    rows.sort(key=lambda j: (j.status not in jobs.ACTIVE, ), reverse=False)
    return [_serialize(j, names_t.get(j.tenant_id), names_h.get(j.hunt_id)) for j in rows]


@router.post("/{job_id}/cancel")
def cancel_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    cancelled = jobs.cancel(db, job)
    return {"id": job.id, "status": job.status, "cancelled": cancelled}
