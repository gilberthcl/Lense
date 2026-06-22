"""
Job lifecycle helpers: stale cleanup, de-duplication, and cooperative cancel.

Analysis jobs run as in-process background tasks. To keep the UI honest and the
local LLM from being overwhelmed by duplicate work, we:
  - mark any 'queued'/'running' jobs as failed on startup (a previous backend
    process can't still be running them);
  - refuse to start a second job of the same kind while one is active (the
    caller re-attaches to the existing one);
  - let the user cancel a job; long-running loops check `is_cancelled` at safe
    points and abort.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AnalysisJob

ACTIVE = ("queued", "running")


class JobCancelled(Exception):
    """Raised inside a running job when the operator has cancelled it."""


def cleanup_stale(db: Session) -> int:
    """Fail any jobs left active by a previous (now-dead) backend process."""
    n = (
        db.query(AnalysisJob)
        .filter(AnalysisJob.status.in_(ACTIVE))
        .update(
            {"status": "error", "error": "interrupted — backend was restarted"},
            synchronize_session=False,
        )
    )
    db.commit()
    return n


def active_job(
    db: Session,
    *,
    tenant_id: int,
    hunt_id: int,
    phase: str,
    dataset_id: int | None = None,
) -> AnalysisJob | None:
    q = db.query(AnalysisJob).filter(
        AnalysisJob.tenant_id == tenant_id,
        AnalysisJob.hunt_id == hunt_id,
        AnalysisJob.phase == phase,
        AnalysisJob.status.in_(ACTIVE),
    )
    if dataset_id is not None:
        q = q.filter(AnalysisJob.dataset_id == dataset_id)
    return q.order_by(AnalysisJob.created_at.desc()).first()


def is_cancelled(db: Session, job_id: int) -> bool:
    """Fresh read of the job's status (used by running tasks to honour cancels)."""
    return db.query(AnalysisJob.status).filter_by(id=job_id).scalar() == "cancelled"


def raise_if_cancelled(db: Session, job_id: int) -> None:
    if is_cancelled(db, job_id):
        raise JobCancelled()


def cancel(db: Session, job: AnalysisJob) -> bool:
    """Mark a job cancelled. Returns False if it was already finished."""
    if job.status not in ACTIVE:
        return False
    job.status = "cancelled"
    job.current_task = "Cancelled"
    job.error = "Cancelled by operator"
    db.commit()
    return True
