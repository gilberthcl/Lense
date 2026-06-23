"""Dataset upload + preview + per-dataset analysis + pre-analysis planning."""
import re
import time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import (
    APIRouter, BackgroundTasks, Body, Depends, HTTPException, UploadFile, File,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_tenant
from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.models import AnalysisJob, Dataset, Hunt, Tenant
from app.schemas import DatasetOut, HuntOut, JobOut
from app.services import analysis_planner, csv_loader, jobs
from app.services.analysis_runner import run_dataset_analysis


class PlanRequest(BaseModel):
    feedback: str | None = None

router = APIRouter(prefix="/api/tenants/{tenant_id}/hunts/{hunt_id}", tags=["datasets"])

UPLOAD_ROOT = Path("uploads")


def _resolve_hunt(db: Session, tenant: Tenant, hunt_id: int) -> Hunt:
    hunt = db.get(Hunt, hunt_id)
    if not hunt or hunt.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Hunt not found")
    return hunt


@router.get("/datasets", response_model=list[DatasetOut])
def list_datasets(
    hunt_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    _resolve_hunt(db, tenant, hunt_id)
    return (
        db.query(Dataset)
        .filter_by(hunt_id=hunt_id, tenant_id=tenant.id)
        .order_by(Dataset.created_at)
        .all()
    )


@router.post("/datasets", response_model=DatasetOut, status_code=201)
async def upload_dataset(
    hunt_id: int,
    file: UploadFile = File(...),
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    hunt = _resolve_hunt(db, tenant, hunt_id)
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="Only .csv files are accepted")

    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File exceeds 20 MB dataset cap")

    # Store under tenant/hunt scoped path; randomized name avoids collisions.
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", file.filename)
    dest_dir = UPLOAD_ROOT / f"tenant_{tenant.id}" / f"hunt_{hunt_id}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{uuid.uuid4().hex}_{safe}"
    dest.write_bytes(data)

    # Cheap metadata pass so the table + analysis plan have real numbers
    # (full statistics are computed later during analysis). Never fail upload.
    row_count = col_count = 0
    columns = None
    try:
        df = csv_loader.load_csv(dest, settings.max_upload_bytes)
        row_count = int(df.shape[0])
        col_count = int(df.shape[1])
        columns = [{"name": str(c)} for c in df.columns]
    except Exception:  # noqa: BLE001 — metadata is best-effort
        pass

    dataset = Dataset(
        tenant_id=tenant.id,
        hunt_id=hunt.id,
        filename=file.filename,
        file_path=str(dest),
        file_size=len(data),
        row_count=row_count,
        col_count=col_count,
        columns=columns,
        status="uploaded",
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return dataset


@router.get("/datasets/{dataset_id}/preview")
def preview_dataset(
    hunt_id: int,
    dataset_id: int,
    rows: int = 20,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Return the column list and first N rows of a dataset (capped at 50)."""
    _resolve_hunt(db, tenant, hunt_id)
    dataset = db.get(Dataset, dataset_id)
    if not dataset or dataset.tenant_id != tenant.id or dataset.hunt_id != hunt_id:
        raise HTTPException(status_code=404, detail="Dataset not found")
    try:
        df = csv_loader.load_csv(dataset.file_path, settings.max_upload_bytes)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Could not read CSV: {exc}")
    n = max(1, min(rows, 50))
    head = df.head(n)
    return {
        "filename": dataset.filename,
        "row_count": int(df.shape[0]),
        "col_count": int(df.shape[1]),
        "columns": [str(c) for c in df.columns],
        "rows": [[("" if v is None else str(v)) for v in rec]
                 for rec in head.itertuples(index=False, name=None)],
    }


@router.post("/analysis-plan", response_model=JobOut, status_code=202)
def create_analysis_plan(
    hunt_id: int,
    background: BackgroundTasks,
    payload: PlanRequest = Body(default=PlanRequest()),
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Plan the analysis (phases/batches/complexity/QA) from dataset metadata.

    An optional `feedback` revises the previous plan instead of starting fresh.
    """
    _resolve_hunt(db, tenant, hunt_id)
    if not db.query(Dataset).filter_by(hunt_id=hunt_id, tenant_id=tenant.id).first():
        raise HTTPException(status_code=422, detail="Upload datasets before planning")

    existing = jobs.active_job(db, tenant_id=tenant.id, hunt_id=hunt_id, phase="plan")
    if existing:
        return existing

    feedback = (payload.feedback or "").strip() or None
    job = AnalysisJob(
        tenant_id=tenant.id, hunt_id=hunt_id, dataset_id=None,
        phase="plan", status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    def _task(job_id: int, h_id: int, t_id: int):
        task_db = SessionLocal()
        t0 = time.monotonic()

        def emit(j: AnalysisJob, msg: str, pct: int | None = None) -> None:
            j.log = (j.log or []) + [{"at": round(time.monotonic() - t0, 1), "msg": msg}]
            if pct is not None:
                j.progress = pct
            task_db.commit()

        try:
            j = task_db.get(AnalysisJob, job_id)
            h = task_db.get(Hunt, h_id)
            try:
                j.status = "running"
                j.model = analysis_planner.planner_model()
                emit(j, "Collecting dataset metadata…", 10)
                metas = analysis_planner.dataset_meta(task_db, h_id, t_id)
                verb = "Revising" if feedback else "Planning"
                emit(j, f"{verb} across {len(metas)} datasets with {j.model}…", 20)
                previous = h.analysis_plan if feedback else None

                state = {"last": time.monotonic(), "pct": 20, "tok": 0}

                def on_chunk(_t: str) -> None:
                    state["tok"] += 1
                    now = time.monotonic()
                    if now - state["last"] >= 1.3:
                        state["last"] = now
                        state["pct"] = min(90, state["pct"] + 5)
                        emit(j, f"{j.model} {verb.lower()}… {state['tok']} tokens", state["pct"])
                        jobs.raise_if_cancelled(task_db, job_id)

                plan = analysis_planner.plan_stream(
                    h, metas, on_chunk=on_chunk, feedback=feedback, previous=previous
                )
                h.analysis_plan = plan
                # Reset review state: a (re)generated plan starts as a draft.
                h.plan_state = {"status": "draft", "feedback": feedback, "accepted_at": None}
                emit(j, f"Plan ready — {len(plan.get('phases', []))} phases, "
                        f"{plan.get('estimated_rounds', '?')} rounds.", 98)
                j.status = "done"
                j.progress = 100
                j.current_task = "Complete"
                j.result = {"phases": len(plan.get("phases", []))}
                task_db.commit()
            except jobs.JobCancelled:
                task_db.rollback()
                j = task_db.get(AnalysisJob, job_id)
                j.status = "cancelled"
                j.current_task = "Cancelled"
                j.log = (j.log or []) + [{"at": round(time.monotonic() - t0, 1), "msg": "Cancelled by operator"}]
                task_db.commit()
            except Exception as exc:  # noqa: BLE001
                task_db.rollback()
                j = task_db.get(AnalysisJob, job_id)
                j.status = "error"
                j.error = str(exc)
                j.log = (j.log or []) + [{"at": round(time.monotonic() - t0, 1), "msg": f"Error: {exc}"}]
                task_db.commit()
        finally:
            task_db.close()

    background.add_task(_task, job.id, hunt_id, tenant.id)  # feedback captured via closure
    return job


@router.post("/plan/accept", response_model=HuntOut)
def accept_plan(
    hunt_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Approve the current plan — unlocks phase-by-phase execution in the UI."""
    hunt = _resolve_hunt(db, tenant, hunt_id)
    if not hunt.analysis_plan:
        raise HTTPException(status_code=422, detail="No plan to accept")
    state = dict(hunt.plan_state or {})
    state["status"] = "accepted"
    state["accepted_at"] = datetime.utcnow().isoformat()
    hunt.plan_state = state
    db.commit()
    db.refresh(hunt)
    return hunt


@router.get("/jobs", response_model=list[JobOut])
def list_hunt_jobs(
    hunt_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Recent jobs for this hunt (active first) — used to re-attach the UI."""
    _resolve_hunt(db, tenant, hunt_id)
    return (
        db.query(AnalysisJob)
        .filter_by(tenant_id=tenant.id, hunt_id=hunt_id)
        .order_by(AnalysisJob.created_at.desc())
        .limit(30)
        .all()
    )


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_hunt_job(
    hunt_id: int,
    job_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    job = db.get(AnalysisJob, job_id)
    if not job or job.tenant_id != tenant.id or job.hunt_id != hunt_id:
        raise HTTPException(status_code=404, detail="Job not found")
    jobs.cancel(db, job)
    return job


@router.post("/datasets/{dataset_id}/analyze", response_model=JobOut, status_code=202)
def analyze_dataset_endpoint(
    hunt_id: int,
    dataset_id: int,
    background: BackgroundTasks,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    _resolve_hunt(db, tenant, hunt_id)
    dataset = db.get(Dataset, dataset_id)
    if not dataset or dataset.tenant_id != tenant.id or dataset.hunt_id != hunt_id:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Re-attach to an in-flight analysis for this dataset instead of starting a
    # duplicate Ollama run.
    existing = jobs.active_job(
        db, tenant_id=tenant.id, hunt_id=hunt_id, phase="analysis", dataset_id=dataset_id
    )
    if existing:
        return existing

    job = AnalysisJob(
        tenant_id=tenant.id, hunt_id=hunt_id, dataset_id=dataset_id,
        phase="analysis", status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Background task needs its own session (request session closes on return).
    def _task(job_id: int):
        task_db = SessionLocal()
        try:
            run_dataset_analysis(task_db, job_id)
        finally:
            task_db.close()

    background.add_task(_task, job.id)
    return job


@router.get("/jobs/{job_id}", response_model=JobOut)
def job_status(
    hunt_id: int,
    job_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    job = db.get(AnalysisJob, job_id)
    if not job or job.tenant_id != tenant.id or job.hunt_id != hunt_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
