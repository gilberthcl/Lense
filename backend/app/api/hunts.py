from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile,
)
from sqlalchemy.orm import Session

from app.api.deps import get_tenant
from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.models import AnalysisJob, Hunt, KnowledgeDocument, Tenant
from app.schemas import HuntCreate, HuntOut, JobOut
from app.services import doc_loader
from app.services.analysis_runner import ensure_methodology_brief

router = APIRouter(prefix="/api/tenants/{tenant_id}/hunts", tags=["hunts"])


def _resolve_hunt(db: Session, tenant: Tenant, hunt_id: int) -> Hunt:
    hunt = db.get(Hunt, hunt_id)
    if not hunt or hunt.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Hunt not found")
    return hunt


@router.get("", response_model=list[HuntOut])
def list_hunts(tenant: Tenant = Depends(get_tenant), db: Session = Depends(get_db)):
    return (
        db.query(Hunt)
        .filter_by(tenant_id=tenant.id)
        .order_by(Hunt.created_at.desc())
        .all()
    )


@router.post("", response_model=HuntOut, status_code=201)
def create_hunt(
    payload: HuntCreate,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    methodology = payload.methodology_text
    # Default to the tenant's methodology doc if none supplied for this hunt.
    if not methodology:
        doc = (
            db.query(KnowledgeDocument)
            .filter_by(tenant_id=tenant.id, doc_type="methodology")
            .order_by(KnowledgeDocument.created_at.desc())
            .first()
        )
        methodology = doc.content if doc else None
    hunt = Hunt(
        tenant_id=tenant.id,
        name=payload.name,
        objective=payload.objective,
        methodology_text=methodology,
        report_language=payload.report_language or "English",
        edr=payload.edr,
        siem=payload.siem,
    )
    db.add(hunt)
    db.commit()
    db.refresh(hunt)
    return hunt


@router.get("/{hunt_id}", response_model=HuntOut)
def get_hunt(
    hunt_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    return _resolve_hunt(db, tenant, hunt_id)


@router.post("/{hunt_id}/methodology", response_model=HuntOut)
async def upload_methodology(
    hunt_id: int,
    file: UploadFile = File(...),
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Upload a methodology file (.docx/.txt/.md); extract text and reset the brief."""
    hunt = _resolve_hunt(db, tenant, hunt_id)
    lower = (file.filename or "").lower()
    if not lower.endswith(doc_loader.SUPPORTED_SUFFIXES):
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type. Allowed: {', '.join(doc_loader.SUPPORTED_SUFFIXES)}",
        )
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Methodology file exceeds the size cap")
    try:
        text = doc_loader.extract_text(file.filename, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not text.strip():
        raise HTTPException(status_code=422, detail="No text could be extracted from the file")

    hunt.methodology_text = text
    hunt.methodology_brief = None  # force re-comprehension
    db.commit()
    db.refresh(hunt)
    return hunt


@router.post("/{hunt_id}/methodology/analyze", response_model=JobOut, status_code=202)
def analyze_methodology(
    hunt_id: int,
    background: BackgroundTasks,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Kick off the methodology comprehension pass (background)."""
    hunt = _resolve_hunt(db, tenant, hunt_id)
    if not (hunt.methodology_text or "").strip():
        raise HTTPException(status_code=422, detail="No methodology to analyze")

    job = AnalysisJob(
        tenant_id=tenant.id, hunt_id=hunt_id, dataset_id=None,
        phase="methodology", status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    def _task(job_id: int, h_id: int):
        task_db = SessionLocal()
        try:
            j = task_db.get(AnalysisJob, job_id)
            h = task_db.get(Hunt, h_id)
            try:
                j.status = "running"
                j.current_task = "Comprehending hunt methodology"
                j.progress = 30
                task_db.commit()
                h.methodology_brief = None
                brief = ensure_methodology_brief(task_db, h)
                j.status = "done"
                j.progress = 100
                j.current_task = "Complete"
                j.result = {"topics": len((brief or {}).get("topics", []))}
                task_db.commit()
            except Exception as exc:  # noqa: BLE001
                task_db.rollback()
                j.status = "error"
                j.error = str(exc)
                task_db.commit()
        finally:
            task_db.close()

    background.add_task(_task, job.id, hunt_id)
    return job
