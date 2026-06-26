from fastapi import (
    APIRouter, BackgroundTasks, Body, Depends, File, HTTPException, UploadFile,
)
from sqlalchemy.orm import Session

from app.api.deps import get_tenant
from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.models import AnalysisJob, Dataset, Finding, Hunt, KnowledgeDocument, Tenant
from app.schemas import HuntCreate, HuntOut, HuntUpdate, JobOut, StageFeedback
import time

from app.services import (
    doc_loader, jobs, learning, methodology, methodology_parser, tenant_models,
    training_review,
)
from app.services import ollama_client as ollama
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
        kind="training" if payload.kind == "training" else "live",
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


@router.post("/{hunt_id}/complete", response_model=HuntOut)
def complete_hunt(
    hunt_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Mark a live hunt completed → it moves to the Historic list."""
    hunt = _resolve_hunt(db, tenant, hunt_id)
    hunt.status = "completed"
    db.commit()
    db.refresh(hunt)
    return hunt


@router.post("/{hunt_id}/reopen", response_model=HuntOut)
def reopen_hunt(
    hunt_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Reopen a completed hunt → back to the Live list."""
    hunt = _resolve_hunt(db, tenant, hunt_id)
    hunt.status = "analyzed" if hunt.status == "completed" else hunt.status
    db.commit()
    db.refresh(hunt)
    return hunt


# ── Training-hunt review (W3): "what I learned" + accept/reject loop ──────────

def _require_training(hunt: Hunt) -> None:
    if hunt.kind != "training":
        raise HTTPException(
            status_code=422,
            detail="The learning review is only for training hunts.",
        )


def _training_findings(db: Session, tenant_id: int, hunt_id: int) -> list[dict]:
    rows = (
        db.query(Finding)
        .filter_by(tenant_id=tenant_id, hunt_id=hunt_id)
        .filter(Finding.merged_into_id.is_(None))
        .all()
    )
    return [
        {
            "finding_ref": f.finding_ref, "title": f.title, "category": f.category,
            "severity": f.severity, "summary": f.summary,
            "affected_assets": f.affected_assets, "affected_users": f.affected_users,
            "mitre": f.mitre,
        }
        for f in rows
    ]


def _training_datasets(db: Session, tenant_id: int, hunt_id: int) -> list[dict]:
    rows = db.query(Dataset).filter_by(tenant_id=tenant_id, hunt_id=hunt_id).all()
    return [
        {
            "filename": d.filename, "status": d.status,
            "rows": d.row_count, "cols": d.col_count,
            "columns": [c.get("name") for c in (d.columns or []) if isinstance(c, dict)][:40],
        }
        for d in rows
    ]


@router.post("/{hunt_id}/training/review", response_model=HuntOut)
def training_review_run(
    hunt_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
    feedback: str | None = Body(default=None, embed=True),
):
    """Run (or regenerate-with-feedback) the 'what I learned' review of a training
    hunt: the model studies the confirmed findings + datasets and articulates the
    detection logic it learned. Stored on the hunt for the analyst to accept/reject."""
    hunt = _resolve_hunt(db, tenant, hunt_id)
    _require_training(hunt)
    findings = _training_findings(db, tenant.id, hunt_id)
    if not findings:
        raise HTTPException(
            status_code=409,
            detail="Add the hunt's findings first — there's nothing to learn from yet.",
        )
    try:
        report = training_review.summarize_learning(
            findings, _training_datasets(db, tenant.id, hunt_id), feedback=feedback,
            model=tenant_models.resolve_analyst_model(db, tenant.id),
        )
    except ollama.OllamaError as exc:
        raise HTTPException(status_code=502, detail=f"Review failed: {exc}") from exc
    hunt.training_review = {
        "report": report,
        "disposition": None,        # pending the analyst's accept/reject
        "feedback": (feedback or "").strip() or None,
    }
    db.commit()
    db.refresh(hunt)
    return hunt


@router.post("/{hunt_id}/training/review/disposition", response_model=HuntOut)
def training_review_disposition(
    hunt_id: int,
    background: BackgroundTasks,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
    action: str = Body(..., embed=True),                 # accept | reject
    feedback: str | None = Body(default=None, embed=True),
):
    """Accept or reject the learning review. Accepting records it as a learning
    signal (source=training_hunt) so the detection logic informs future hunts."""
    hunt = _resolve_hunt(db, tenant, hunt_id)
    _require_training(hunt)
    if action not in ("accept", "reject"):
        raise HTTPException(status_code=422, detail="action must be 'accept' or 'reject'.")
    review = dict(hunt.training_review or {})
    if not review.get("report"):
        raise HTTPException(status_code=409, detail="Run the review first.")
    review["disposition"] = "accepted" if action == "accept" else "rejected"
    if feedback:
        review["feedback"] = feedback
    hunt.training_review = review
    db.commit()
    db.refresh(hunt)

    if action == "accept":
        # Mirror the distilled detection logic into the client's knowledge base as
        # a training-hunt learning signal (informs future hunts; no retraining).
        note = training_review.review_as_note(review["report"])
        background.add_task(_record_training_note, tenant.id, hunt_id, note)
    return hunt


def _record_training_note(tenant_id: int, hunt_id: int, note: str) -> None:
    if not (note or "").strip():
        return
    db = SessionLocal()
    try:
        learning.record_event(
            db, tenant_id=tenant_id, hunt_id=hunt_id, stage="analysis",
            source="training_hunt", target_type="training_review",
            summary=note,
        )
    finally:
        db.close()


def _stage_feedback_async(
    tenant_id: int, hunt_id: int, stage: str, disposition: str | None,
    score: int | None, feedback: str | None, target_type: str | None, target_id: int | None,
) -> None:
    db = SessionLocal()
    try:
        learning.record_event(
            db, tenant_id=tenant_id, hunt_id=hunt_id, stage=stage,
            source="live_feedback", disposition=disposition, score=score,
            feedback_text=feedback, target_type=target_type or stage, target_id=target_id,
        )
    finally:
        db.close()


@router.post("/{hunt_id}/stages/{stage}/feedback")
def stage_feedback(
    hunt_id: int,
    stage: str,
    payload: StageFeedback,
    background: BackgroundTasks,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Record disposition/score/feedback on any pipeline stage's output (W4).
    The lesson is mirrored to RAG like every other learning signal."""
    if stage not in learning.VALID_STAGES:
        raise HTTPException(status_code=422, detail=f"Unknown stage '{stage}'.")
    if payload.score is not None and not (1 <= int(payload.score) <= 10):
        raise HTTPException(status_code=422, detail="Score must be between 1 and 10.")
    if not (payload.feedback or "").strip() and payload.score is None and not payload.disposition:
        raise HTTPException(status_code=422, detail="Provide feedback, a score, or a disposition.")
    _resolve_hunt(db, tenant, hunt_id)
    background.add_task(
        _stage_feedback_async, tenant.id, hunt_id, stage, payload.disposition,
        payload.score, payload.feedback, payload.target_type, payload.target_id,
    )
    return {"ok": True}


@router.get("/{hunt_id}/learning-summary")
def learning_summary(
    hunt_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Per-stage summary of the learning signals recorded for this hunt (W4)."""
    _resolve_hunt(db, tenant, hunt_id)
    events = learning.list_events(db, tenant.id, hunt_id=hunt_id)
    return learning.summarize_events(events)


@router.get("/{hunt_id}/analysis-summary")
def analysis_summary(
    hunt_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """
    A readable summary of the ANALYSIS phase: overall totals, and dataset-by-
    dataset what was observed (the analyst's per-dataset assessment) plus the
    findings each dataset produced.
    """
    hunt = _resolve_hunt(db, tenant, hunt_id)
    datasets = (
        db.query(Dataset)
        .filter_by(tenant_id=tenant.id, hunt_id=hunt_id)
        .order_by(Dataset.filename)
        .all()
    )
    findings = db.query(Finding).filter_by(tenant_id=tenant.id, hunt_id=hunt_id).all()

    findings_by_ds: dict[int, list] = {}
    for f in findings:
        findings_by_ds.setdefault(f.dataset_id, []).append(f)

    # Latest done analysis job per dataset → its assessment text.
    assessment: dict[int, str] = {}
    for j in (
        db.query(AnalysisJob)
        .filter_by(tenant_id=tenant.id, hunt_id=hunt_id, phase="analysis", status="done")
        .order_by(AnalysisJob.created_at.desc())
        .all()
    ):
        if j.dataset_id and j.dataset_id not in assessment:
            assessment[j.dataset_id] = (j.result or {}).get("assessment")

    def fcount(seq, key, value):
        return sum(1 for f in seq if getattr(f, key) == value)

    active = [f for f in findings if not f.merged_into_id]
    by_category: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for f in active:
        if f.category:
            by_category[f.category] = by_category.get(f.category, 0) + 1
        if f.severity:
            by_severity[f.severity] = by_severity.get(f.severity, 0) + 1

    datasets_out = []
    for d in datasets:
        fs = findings_by_ds.get(d.id, [])
        datasets_out.append({
            "id": d.id,
            "filename": d.filename,
            "status": d.status,
            "row_count": d.row_count,
            "col_count": d.col_count,
            "assessment": assessment.get(d.id),
            "finding_count": len(fs),
            "findings": [
                {"ref": f.finding_ref, "title": f.title,
                 "category": f.category, "severity": f.severity,
                 "merged": bool(f.merged_into_id)}
                for f in fs
            ],
        })

    return {
        "hunt_id": hunt_id,
        "totals": {
            "datasets": len(datasets),
            "analyzed": fcount(datasets, "status", "analyzed"),
            "findings": len(findings),
            "active_findings": len(active),
            "by_category": by_category,
            "by_severity": by_severity,
        },
        "datasets": datasets_out,
    }


@router.patch("/{hunt_id}", response_model=HuntOut)
def update_hunt(
    hunt_id: int,
    payload: HuntUpdate,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    hunt = _resolve_hunt(db, tenant, hunt_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(hunt, field, value)
    db.commit()
    db.refresh(hunt)
    return hunt


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
    feedback: str | None = Body(default=None, embed=True),
):
    """Kick off the methodology comprehension pass (background). When `feedback`
    is given, the model REVISES its prior understanding to address it
    (regenerate-with-feedback), and the correction is recorded as a learning
    signal for this client."""
    hunt = _resolve_hunt(db, tenant, hunt_id)
    if not (hunt.methodology_text or "").strip():
        raise HTTPException(status_code=422, detail="No methodology to analyze")

    existing = jobs.active_job(db, tenant_id=tenant.id, hunt_id=hunt_id, phase="methodology")
    if existing:
        return existing

    fb = (feedback or "").strip() or None
    # CRITICAL: run THIS client's configured model, never the global default.
    model_name = tenant_models.resolve_analyst_model(db, tenant.id)
    job = AnalysisJob(
        tenant_id=tenant.id, hunt_id=hunt_id, dataset_id=None,
        phase="methodology", status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    if fb:
        background.add_task(
            _stage_feedback_async, tenant.id, hunt_id, "methodology",
            None, None, fb, "methodology", None,
        )

    def _task(job_id: int, h_id: int, feedback_text: str | None = fb,
              model: str | None = model_name):
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
                j.model = model or methodology.analyst_model()
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
                if feedback_text:
                    emit(j, "Revising comprehension to address your feedback…", 22)
                else:
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
                        jobs.raise_if_cancelled(task_db, job_id)

                brief = methodology.comprehend_stream(
                    h.methodology_text or "", edr=h.edr, siem=h.siem,
                    language=h.report_language, feedback=feedback_text,
                    model=model, on_chunk=on_chunk,
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
            except jobs.JobCancelled:
                task_db.rollback()
                j = task_db.get(AnalysisJob, job_id)
                j.status = "cancelled"
                j.current_task = "Cancelled"
                j.log = (j.log or []) + [
                    {"at": round(time.monotonic() - t0, 1), "msg": "Cancelled by operator"}
                ]
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
