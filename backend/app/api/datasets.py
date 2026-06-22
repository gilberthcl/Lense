"""Dataset upload + per-dataset analysis trigger."""
import re
import uuid
from pathlib import Path

from fastapi import (
    APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File,
)
from sqlalchemy.orm import Session

from app.api.deps import get_tenant
from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.models import AnalysisJob, Dataset, Hunt, Tenant
from app.schemas import DatasetOut, JobOut
from app.services.analysis_runner import run_dataset_analysis

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

    dataset = Dataset(
        tenant_id=tenant.id,
        hunt_id=hunt.id,
        filename=file.filename,
        file_path=str(dest),
        file_size=len(data),
        status="uploaded",
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return dataset


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
