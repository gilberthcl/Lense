from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile,
)
from sqlalchemy.orm import Session

from app.api.deps import get_tenant
from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.models import AnalysisJob, Hunt, KnowledgeDocument, Tenant
from app.schemas import HuntCreate, HuntOut, JobOut
import time

from app.services import doc_loader, methodology, methodology_parser
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
    hunt.methodology_brief = None      # force re-comprehension
    hunt.methodology_sections = None   # force re-parse
    db.commit()
    db.refresh(hunt)
    return hunt


@router.delete("/{hunt_id}", status_code=204)
def delete_hunt(
    hunt_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Delete a hunt and everything scoped to it (datasets, findings, jobs)."""
    hunt = _resolve_hunt(db, tenant, hunt_id)
    db.delete(hunt)
    db.commit()


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
                j.model = methodology.analyst_model()
                j.current_task = "Parsing methodology structure"
                emit(j, "Parsing methodology structure (deterministic)…", 8)

                # 1) Deterministic structural parse — always available, no LLM.
                sections = methodology_parser.parse_methodology(h.methodology_text or "")
                h.methodology_sections = sections
                if sections.get("available"):
                    st = sections["stats"]
                    emit(j, f"Parsed {st['topic_count']} topics and {st['query_count']} "
                            f"queries ({st['queries_with_results']} returned results).", 18)
                else:
                    emit(j, "Document structure not recognized; using raw text.", 18)

                # 2) LLM comprehension (streamed) for the "understanding" layer.
                j.current_task = f"Comprehending with {j.model}"
                emit(j, f"Sending methodology to {j.model} for comprehension…", 22)
                h.methodology_brief = None
                task_db.commit()

                state = {"tokens": 0, "last": time.monotonic(), "pct": 22}

                def on_chunk(_tok: str) -> None:
                    state["tokens"] += 1
                    now = time.monotonic()
                    if now - state["last"] >= 1.3:
                        state["last"] = now
                        state["pct"] = min(88, state["pct"] + 4)
                        emit(j, f"{j.model} is reading… {state['tokens']} tokens generated",
                             state["pct"])

                brief = methodology.comprehend_stream(
                    h.methodology_text or "", edr=h.edr, siem=h.siem,
                    language=h.report_language, on_chunk=on_chunk,
                )
                h.methodology_brief = brief
                topics = len((brief or {}).get("topics", []))
                emit(j, f"Comprehension complete — model understood {topics} topics.", 96)

                j.status = "done"
                j.progress = 100
                j.current_task = "Complete"
                j.result = {
                    "topics": topics,
                    "parsed": sections.get("stats") if sections.get("available") else None,
                }
                task_db.commit()
            except Exception as exc:  # noqa: BLE001
                task_db.rollback()
                j = task_db.get(AnalysisJob, job_id)
                j.status = "error"
                j.error = str(exc)
                j.log = (j.log or []) + [
                    {"at": round(time.monotonic() - t0, 1), "msg": f"Error: {exc}"}
                ]
                # The deterministic sections (committed above) remain available.
                task_db.commit()
        finally:
            task_db.close()

    background.add_task(_task, job.id, hunt_id)
    return job
