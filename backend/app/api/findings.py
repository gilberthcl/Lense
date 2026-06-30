"""Findings listing + validation workflow (validated findings feed learning)."""
import re

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant
from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.models import AnalysisJob, Dataset, Finding, Hunt, KnowledgeDocument, Tenant
from app.schemas import (
    FindingBulkUpdate, FindingDisposition, FindingDispositionResult, FindingOut,
    FindingRegenerate, FindingRevisionResult, FindingStatusUpdate,
    ImportFindingsCreate, ImportFindingsResult, JobOut, LearnFromFindingCreate,
    LearningNote, MissedFindingCreate, MissedLocateCreate, MissedFindingResult,
)
from app.services import (
    categories, csv_loader, dataset_locator, finding_details, finding_feedback,
    findings_export, knowledge, learning, missed_finding, tenant_models,
    training_import,
)
from app.services import ollama_client as ollama

router = APIRouter(prefix="/api/tenants/{tenant_id}/hunts/{hunt_id}/findings", tags=["findings"])

VALID_STATUSES = {"draft", "validated", "rejected"}


def _new_learning_job(db: Session, tenant_id: int, hunt_id: int,
                      model: str | None, task: str) -> AnalysisJob:
    """A visible AnalysisJob (phase='learning') for a findings-upload model pass,
    so it shows up in Config → AI Jobs (the user can see it run)."""
    job = AnalysisJob(
        tenant_id=tenant_id, hunt_id=hunt_id, phase="learning", status="running",
        model=model, current_task=task, progress=20,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _finish_job(db: Session, job: AnalysisJob, *, result: dict | None = None,
                error: str | None = None) -> None:
    job.status = "error" if error else "done"
    job.progress = 100
    job.current_task = "Failed" if error else "Complete"
    if error:
        job.error = error
    if result is not None:
        job.result = result
    db.commit()


def _index_doc_async(document_id: int) -> None:
    """Embed a knowledge document into the tenant KB (own session, fail-open)."""
    db = SessionLocal()
    try:
        knowledge.index_document_by_id(db, document_id)
    finally:
        db.close()


def _record_learning_async(
    tenant_id: int, hunt_id: int, finding_id: int,
    disposition: str | None, score: int | None, feedback: str | None,
    lesson: str | None = None,
) -> None:
    """Capture a learning signal (event + RAG mirror) off the request path. When a
    model reflection produced a generalisable `lesson`, store it as the event
    summary so the RAG note carries the distilled rule, not just raw feedback."""
    db = SessionLocal()
    try:
        learning.record_event(
            db, tenant_id=tenant_id, hunt_id=hunt_id, stage="finding",
            source="live_feedback", target_type="finding", target_id=finding_id,
            disposition=disposition, score=score, feedback_text=feedback,
            summary=lesson,
        )
    finally:
        db.close()


def _resolve_finding(db: Session, tenant_id: int, hunt_id: int, finding_id: int) -> Finding:
    finding = db.get(Finding, finding_id)
    if not finding or finding.tenant_id != tenant_id or finding.hunt_id != hunt_id:
        raise HTTPException(status_code=404, detail="Finding not found")
    return finding


def _record_missed_async(
    tenant_id: int, hunt_id: int, finding_id: int, description: str, summary: str,
    source: str = "missed_finding",
) -> None:
    db = SessionLocal()
    try:
        learning.record_event(
            db, tenant_id=tenant_id, hunt_id=hunt_id, stage="finding",
            source=source, target_type="finding", target_id=finding_id,
            disposition="added", feedback_text=description, summary=summary or None,
        )
    finally:
        db.close()


def _dataset_evidence(db: Session, tenant_id: int, hunt_id: int, dataset_id: int):
    """Resolve a dataset (tenant+hunt scoped) and rebuild its evidence package.
    409 if the file is gone — grounding needs it."""
    dataset = db.get(Dataset, dataset_id)
    if not dataset or dataset.tenant_id != tenant_id or dataset.hunt_id != hunt_id:
        raise HTTPException(status_code=404, detail="Dataset not found")
    try:
        df = csv_loader.load_csv(dataset.file_path, settings.max_upload_bytes)
        evidence = csv_loader.build_evidence_package(df, sample_rows=12)
    except Exception as exc:  # noqa: BLE001 — file gone / unreadable
        raise HTTPException(
            status_code=409,
            detail=f"Dataset file is no longer available to analyse ({exc}).",
        ) from exc
    return dataset, evidence


def _build_finding(tenant_id, hunt_id, dataset, ref, f, evidence, why=None) -> Finding:
    """Construct an analyst-confirmed (validated, disposition=added) finding from a
    structured dict + its dataset evidence."""
    detail = finding_details.build(f, evidence)
    return Finding(
        tenant_id=tenant_id, hunt_id=hunt_id, dataset_id=dataset.id,
        finding_ref=f"F-{ref:03d}",
        title=(f.get("title") or "Untitled finding")[:400],
        category=categories.normalize(f.get("category")),
        severity=f.get("severity"), confidence=f.get("confidence"),
        summary=f.get("summary"), evidence=f.get("evidence"), mitre=f.get("mitre"),
        affected_assets=f.get("affected_assets"), affected_users=f.get("affected_users"),
        recommendations=f.get("recommendations"),
        source_dataset=dataset.filename,
        entities=detail["entities"], time_range=detail["time_range"],
        behavioral_context=detail["behavioral_context"], evidence_rows=detail["evidence_rows"],
        status="validated", disposition="added", reviewer_notes=why,
    )


def _record_note_async(tenant_id: int, hunt_id: int, finding_id: int, text: str) -> None:
    db = SessionLocal()
    try:
        learning.record_event(
            db, tenant_id=tenant_id, hunt_id=hunt_id, stage="finding",
            source="missed_finding", target_type="finding", target_id=finding_id,
            summary=text,
        )
    finally:
        db.close()


def _promote_to_knowledge(db: Session, finding: Finding) -> int | None:
    """Create a validated_finding KB document. Returns its id (to index)."""
    doc = KnowledgeDocument(
        tenant_id=finding.tenant_id,
        doc_type="validated_finding",
        title=f"{finding.finding_ref}: {finding.title}",
        content="\n\n".join(
            p for p in (finding.summary, finding.recommendations, finding.reviewer_notes) if p
        ),
    )
    db.add(doc)
    db.flush()  # assign id without ending the transaction
    return doc.id


@router.delete("/{finding_id}", status_code=204)
def delete_finding(
    hunt_id: int,
    finding_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Hard-delete a finding everywhere — including any KB doc it was promoted to."""
    finding = db.get(Finding, finding_id)
    if not finding or finding.tenant_id != tenant.id or finding.hunt_id != hunt_id:
        raise HTTPException(status_code=404, detail="Finding not found")
    if finding.finding_ref:
        db.query(KnowledgeDocument).filter(
            KnowledgeDocument.tenant_id == tenant.id,
            KnowledgeDocument.doc_type == "validated_finding",
            KnowledgeDocument.title.like(f"{finding.finding_ref}:%"),
        ).delete(synchronize_session=False)
    db.delete(finding)
    db.commit()


@router.get("", response_model=list[FindingOut])
def list_findings(
    hunt_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    return (
        db.query(Finding)
        .filter_by(hunt_id=hunt_id, tenant_id=tenant.id)
        .order_by(Finding.finding_ref)
        .all()
    )


_EXPORT_FORMATS = {
    "csv": ("text/csv; charset=utf-8", "csv"),
    "md": ("text/markdown; charset=utf-8", "md"),
    "markdown": ("text/markdown; charset=utf-8", "md"),
    "json": ("application/json; charset=utf-8", "json"),
}


@router.get("/export")
def export_findings(
    hunt_id: int,
    format: str = "csv",
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Download this hunt's findings. `format`:
      • csv  — one row per finding (spreadsheet),
      • md   — readable report, each finding its own section,
      • json — the full structured record (every field, nothing dropped).
    Tenant-scoped: only this tenant's findings for this hunt are exported."""
    fmt = (format or "csv").lower()
    if fmt not in _EXPORT_FORMATS:
        raise HTTPException(status_code=422, detail="format must be csv, md, or json.")
    findings = (
        db.query(Finding)
        .filter_by(hunt_id=hunt_id, tenant_id=tenant.id)
        .order_by(Finding.finding_ref)
        .all()
    )
    dicts = [findings_export.serialize_finding(f) for f in findings]
    hunt = db.get(Hunt, hunt_id)
    hunt_name = (hunt.name if hunt else f"hunt-{hunt_id}") or f"hunt-{hunt_id}"

    if fmt == "csv":
        body = findings_export.to_csv(dicts)
    elif fmt in ("md", "markdown"):
        body = findings_export.to_markdown(hunt_name, dicts)
    else:
        body = findings_export.to_json(
            {"hunt": hunt_name, "hunt_id": hunt_id, "count": len(dicts)}, dicts
        )

    media_type, ext = _EXPORT_FORMATS[fmt]
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", hunt_name).strip("_")[:60] or "hunt"
    filename = f"{slug}_findings.{ext}"
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch("/{finding_id}", response_model=FindingOut)
def update_finding(
    hunt_id: int,
    finding_id: int,
    payload: FindingStatusUpdate,
    background: BackgroundTasks,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    if payload.status is not None and payload.status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid status")
    finding = db.get(Finding, finding_id)
    if not finding or finding.tenant_id != tenant.id or finding.hunt_id != hunt_id:
        raise HTTPException(status_code=404, detail="Finding not found")

    if payload.reviewer_notes is not None:
        finding.reviewer_notes = payload.reviewer_notes

    doc_id: int | None = None
    if payload.status is not None:
        becoming_validated = payload.status == "validated" and finding.status != "validated"
        finding.status = payload.status
        # Learning loop: a validated finding becomes tenant knowledge (+ embedded).
        if becoming_validated:
            doc_id = _promote_to_knowledge(db, finding)

    db.commit()
    db.refresh(finding)
    if doc_id is not None:
        background.add_task(_index_doc_async, doc_id)
    return finding


@router.post("/{finding_id}/disposition", response_model=FindingDispositionResult)
def disposition_finding(
    hunt_id: int,
    finding_id: int,
    payload: FindingDisposition,
    background: BackgroundTasks,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Rich disposition (W1): accept / reject / partial, each with optional score
    and feedback. Sets disposition + status, promotes accepts to the KB, and — when
    feedback is given — runs the analyst model to distil a generalisable lesson
    (the reflection), so accept/reject feedback visibly reaches the model and the
    RAG note carries the distilled rule."""
    err = finding_feedback.validate(payload.action, payload.feedback, payload.score)
    if err:
        raise HTTPException(status_code=422, detail=err)
    finding = _resolve_finding(db, tenant.id, hunt_id, finding_id)

    disposition, status = finding_feedback.map_action(payload.action)
    becoming_validated = status == "validated" and finding.status != "validated"

    # Reflect BEFORE we mutate — the model sees the finding as the analyst judged
    # it. Fail-soft: a model hiccup never blocks the disposition.
    reflection = (
        finding_feedback.reflect(finding_feedback.snapshot(finding), payload.action, payload.feedback,
                                 model=tenant_models.resolve_analyst_model(db, tenant.id))
        if payload.feedback else {}
    )

    finding.disposition = disposition
    finding.status = status
    if payload.score is not None:
        finding.score = int(payload.score)
    if payload.feedback:
        finding.reviewer_notes = payload.feedback

    doc_id = _promote_to_knowledge(db, finding) if becoming_validated else None
    db.commit()
    db.refresh(finding)
    if doc_id is not None:
        background.add_task(_index_doc_async, doc_id)
    background.add_task(
        _record_learning_async, tenant.id, hunt_id, finding.id,
        disposition, payload.score, payload.feedback, reflection.get("lesson"),
    )
    return FindingDispositionResult(
        finding=finding,
        reflection=reflection or None,
    )


@router.post("/{finding_id}/regenerate", response_model=FindingRevisionResult)
def regenerate_finding(
    hunt_id: int,
    finding_id: int,
    payload: FindingRegenerate,
    background: BackgroundTasks,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Partial-accept loop (W1): snapshot the current finding, rewrite it to
    satisfy the feedback (evidence-grounded), and return a VISIBLE outcome — the
    model's reasoning, a per-feedback-point checklist, and a before→after diff —
    so the analyst can see exactly what changed. Repeatable until they accept."""
    if not payload.feedback.strip():
        raise HTTPException(status_code=422, detail="Feedback is required to regenerate.")
    finding = _resolve_finding(db, tenant.id, hunt_id, finding_id)

    before = finding_feedback.snapshot(finding)
    # Snapshot BEFORE the rewrite — the before→feedback→after chain is the signal.
    learning.add_revision(
        db, tenant_id=tenant.id, finding_id=finding.id,
        content=before, feedback_text=payload.feedback,
    )
    try:
        revised = finding_feedback.revise(
            before, payload.feedback,
            model=tenant_models.resolve_analyst_model(db, tenant.id),
        )
    except ollama.OllamaError as exc:
        raise HTTPException(status_code=502, detail=f"Regeneration failed: {exc}") from exc

    applied = finding_feedback.apply_revised_fields(finding, revised)
    changes = finding_feedback.diff_changes(before, finding)
    meta = finding_feedback.revision_meta(revised)

    if applied:
        finding.disposition = "partial"
        finding.status = "draft"
        db.commit()
        db.refresh(finding)
        background.add_task(
            _record_learning_async, tenant.id, hunt_id, finding.id,
            "partial", None, payload.feedback,
        )

    # Even a no-op returns the model's reasoning so the action is never silent.
    return FindingRevisionResult(
        finding=finding,
        reasoning=meta["reasoning"],
        addressed=meta["addressed"],
        changes=changes,
        no_op=not applied,
    )


@router.post("/missed", response_model=MissedFindingResult)
def add_missed_finding(
    hunt_id: int,
    payload: MissedFindingCreate,
    background: BackgroundTasks,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Missed-finding wizard (W2): the analyst pastes a finding the automated pass
    missed + its dataset. The model reconstructs it (grounded in that dataset's
    evidence), diagnoses why it was missed, and the lessons are mirrored to RAG."""
    if not payload.description.strip():
        raise HTTPException(status_code=422, detail="A description of the finding is required.")
    dataset, evidence = _dataset_evidence(db, tenant.id, hunt_id, payload.dataset_id)

    model = tenant_models.resolve_analyst_model(db, tenant.id)
    job = _new_learning_job(db, tenant.id, hunt_id, model, "Reconstructing the missed finding…")
    try:
        out = missed_finding.analyze(dataset.filename, evidence, payload.description, model=model)
    except ollama.OllamaError as exc:
        _finish_job(db, job, error=str(exc))
        raise HTTPException(status_code=502, detail=f"Analysis failed: {exc}") from exc
    f, why, lessons = missed_finding.parse_result(out)
    if not f.get("title"):
        from app.services import model_fit  # lazy: avoid import cost on hot paths
        _finish_job(db, job, error="No structured finding could be reconstructed.")
        raise HTTPException(
            status_code=422,
            detail=(
                "The model could not reconstruct a structured finding — add more "
                "detail." + model_fit.weak_model_suffix(model)
            ),
        )

    from app.services.analysis_runner import _next_finding_seq  # lazy: avoid cycle
    ref = _next_finding_seq(db, hunt_id)
    finding = _build_finding(tenant.id, hunt_id, dataset, ref, f, evidence, why=why)
    db.add(finding)
    db.commit()
    db.refresh(finding)

    doc_id = _promote_to_knowledge(db, finding)
    db.commit()
    if doc_id is not None:
        background.add_task(_index_doc_async, doc_id)
    # Provenance: ingestion into a Training Hunt is training_hunt signal; into a
    # live hunt it's a missed finding (false negative).
    hunt = db.get(Hunt, hunt_id)
    source = "training_hunt" if hunt and hunt.kind == "training" else "missed_finding"
    background.add_task(
        _record_missed_async, tenant.id, hunt_id, finding.id,
        payload.description, missed_finding.lessons_summary(why, lessons), source,
    )
    _finish_job(db, job, result={"finding_ref": finding.finding_ref, "kind": source})
    return {"finding": finding, "why_missed": why, "lessons": lessons}


def _learn_from_match(db: Session, tenant_id: int, hunt_id: int, ds, evidence: dict,
                      description: str, source: str, model: str | None,
                      also_in: list[str] | None = None) -> dict | None:
    """Reconstruct + learn ONE grounded finding from the confirmed dataset (the
    same analysis the known-dataset path runs). `also_in` names the other datasets
    the finding was also observed in — recorded as context, NOT as duplicate
    findings. Returns a summary dict, or None if the model couldn't reconstruct a
    structured finding (incl. unparseable JSON — resilient, never aborts)."""
    from app.services.analysis_runner import _next_finding_seq  # lazy: avoid cycle

    try:
        out = missed_finding.analyze(ds.filename, evidence, description, model=model)
    except ollama.OllamaError:
        return None
    f, why, lessons = missed_finding.parse_result(out)
    if not f.get("title"):
        return None
    if also_in:
        note = "Also observed in: " + ", ".join(also_in)
        why = f"{why}\n{note}" if why else note
    ref = _next_finding_seq(db, hunt_id)
    finding = _build_finding(tenant_id, hunt_id, ds, ref, f, evidence, why=why)
    db.add(finding)
    db.commit()
    db.refresh(finding)
    doc_id = _promote_to_knowledge(db, finding)
    db.commit()
    if doc_id is not None:
        knowledge.index_document_by_id(db, doc_id)
    learning.record_event(
        db, tenant_id=tenant_id, hunt_id=hunt_id, stage="finding",
        source=source, target_type="finding", target_id=finding.id,
        disposition="added", feedback_text=description,
        summary=missed_finding.lessons_summary(why, lessons),
    )
    return {"ref": finding.finding_ref, "dataset": ds.filename}


def _locate_and_learn(tenant_id: int, hunt_id: int, job_id: int, description: str,
                      model: str | None) -> None:
    """Background worker: find which dataset the finding came from (descriptive-name
    priority), then reconstruct + learn ONE finding from the best match. A single
    pasted finding produces a SINGLE finding — never one duplicate per dataset; the
    other matching datasets are recorded on it as 'also observed in'."""
    from app.services import model_fit

    db = SessionLocal()
    try:
        job = db.get(AnalysisJob, job_id)

        def prog(msg: str, pct: int) -> None:
            # current_task is varchar(300) — never overflow it (filenames can be long).
            job.current_task = (msg or "")[:290]
            job.progress = pct
            db.commit()

        res = dataset_locator.locate_matches(
            db, tenant_id, hunt_id, description, model=model, on_progress=prog
        )
        matches = res.get("matches", [])
        if not matches:
            _finish_job(db, job, error=res.get("note") or "Could not locate the dataset.")
            return

        # matches are ranked best-first. Ground the ONE finding in the best match;
        # name the others as context so we don't create duplicate findings.
        best = matches[0]
        also_in = [m["dataset"].filename for m in matches[1:]]
        prog(f"Found in {best['dataset'].filename} — reconstructing & learning…", 88)
        hunt = db.get(Hunt, hunt_id)
        source = "training_hunt" if hunt and hunt.kind == "training" else "missed_finding"

        summary = _learn_from_match(
            db, tenant_id, hunt_id, best["dataset"], best["evidence"],
            description, source, model, also_in=also_in,
        )
        if not summary:
            _finish_job(db, job, error=(
                "Located the dataset but couldn't reconstruct a structured finding — "
                "add more detail." + model_fit.weak_model_suffix(model)
            ))
            return

        _finish_job(db, job, result={
            "located": True, "kind": source,
            "finding_refs": [summary["ref"]],
            "datasets": [summary["dataset"]],
            "also_in": also_in,
            "checked": res.get("checked"),
        })
    except Exception as exc:  # noqa: BLE001 — record any failure on the job
        db.rollback()
        job = db.get(AnalysisJob, job_id)
        if job:
            _finish_job(db, job, error=str(exc))
    finally:
        db.close()


@router.post("/missed/locate", response_model=JobOut, status_code=202)
def locate_missed_finding(
    hunt_id: int,
    payload: MissedLocateCreate,
    background: BackgroundTasks,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Find which dataset an offline finding came from (the analyst doesn't know),
    then learn from it. Runs in the background (it may scan several datasets);
    poll the returned job. Datasets are ranked by descriptive filename first, then
    entity overlap, and checked in that order until the source is found."""
    if not payload.description.strip():
        raise HTTPException(status_code=422, detail="Describe the finding to locate it.")
    model = tenant_models.resolve_analyst_model(db, tenant.id)
    job = _new_learning_job(db, tenant.id, hunt_id, model, "Locating the dataset for the finding…")
    background.add_task(_locate_and_learn, tenant.id, hunt_id, job.id, payload.description, model)
    return job


def _learn_from_existing_finding(tenant_id: int, hunt_id: int, finding_id: int, job_id: int,
                                 dataset_id: int | None, find_dataset: bool,
                                 model: str | None) -> None:
    """Background worker: learn the DETECTION LOGIC behind a historical ground-truth
    finding by analyzing it against its dataset. The finding is NEVER created or
    modified — only a learning signal is recorded (this is a training hunt)."""
    from app.services import model_fit

    db = SessionLocal()
    try:
        job = db.get(AnalysisJob, job_id)

        def prog(msg: str, pct: int) -> None:
            job.current_task = (msg or "")[:290]
            job.progress = pct
            db.commit()

        finding = db.get(Finding, finding_id)
        if finding is None:
            _finish_job(db, job, error="Finding not found.")
            return
        description = "\n".join(
            p for p in (finding.title, finding.summary, finding.reviewer_notes) if p
        )[:4000]

        also_in: list[str] = []
        if dataset_id:
            prog("Loading the dataset…", 40)
            dataset = db.get(Dataset, dataset_id)
            if not dataset or dataset.tenant_id != tenant_id or dataset.hunt_id != hunt_id:
                _finish_job(db, job, error="Dataset not found.")
                return
            try:
                df = csv_loader.load_csv(dataset.file_path, settings.max_upload_bytes)
                evidence = csv_loader.build_evidence_package(df, sample_rows=12)
            except Exception as exc:  # noqa: BLE001
                _finish_job(db, job, error=f"Dataset file unavailable ({exc}).")
                return
        elif find_dataset:
            res = dataset_locator.locate_matches(
                db, tenant_id, hunt_id, description, model=model, on_progress=prog
            )
            matches = res.get("matches", [])
            if not matches:
                _finish_job(db, job, error=res.get("note") or
                            "Could not locate the dataset for this finding.")
                return
            best = matches[0]
            dataset, evidence = best["dataset"], best["evidence"]
            also_in = [m["dataset"].filename for m in matches[1:]]
        else:
            _finish_job(db, job, error="Pick the dataset or enable 'find the dataset'.")
            return

        prog(f"Analyzing {finding.finding_ref} against {dataset.filename} — learning the logic…", 90)
        try:
            logic, lesson = missed_finding.learn_logic(dataset.filename, evidence, description, model=model)
        except ollama.OllamaError as exc:
            _finish_job(db, job, error=f"Analysis failed: {exc}" + model_fit.weak_model_suffix(model))
            return
        if not (logic or lesson):
            _finish_job(db, job, error=(
                "The model couldn't extract the detection logic from this dataset."
                + model_fit.weak_model_suffix(model)
            ))
            return

        # Record learning ONLY — the historical finding stays untouched.
        parts = []
        if logic:
            parts.append(f"Detection logic: {logic}")
        if lesson:
            parts.append(f"Lesson: {lesson}")
        summary = "\n".join(parts) or f"Learned logic for {finding.finding_ref}"
        learning.record_event(
            db, tenant_id=tenant_id, hunt_id=hunt_id, stage="finding",
            source="training_hunt", target_type="finding", target_id=finding.id,
            disposition="added", feedback_text=description, summary=summary,
        )
        _finish_job(db, job, result={
            "learned": True, "finding_ref": finding.finding_ref,
            "dataset": dataset.filename, "also_in": also_in,
            "detection_logic": logic, "lesson": lesson,
        })
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        job = db.get(AnalysisJob, job_id)
        if job:
            _finish_job(db, job, error=str(exc))
    finally:
        db.close()


@router.post("/{finding_id}/learn", response_model=JobOut, status_code=202)
def learn_from_finding(
    hunt_id: int,
    finding_id: int,
    payload: LearnFromFindingCreate,
    background: BackgroundTasks,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Learn the detection logic behind a HISTORICAL ground-truth finding (training
    hunt): analyze it against its dataset and record the learning. The finding is
    never modified. Either pass `dataset_id`, or set `find_dataset` to have the
    model locate it (descriptive-name priority). Runs in the background — poll the
    returned job."""
    finding = _resolve_finding(db, tenant.id, hunt_id, finding_id)
    if not (payload.dataset_id or payload.find_dataset):
        raise HTTPException(status_code=422, detail="Pick the dataset, or enable 'find the dataset'.")
    model = tenant_models.resolve_analyst_model(db, tenant.id)
    job = _new_learning_job(
        db, tenant.id, hunt_id, model, f"Learning the logic behind {finding.finding_ref}…"
    )
    background.add_task(
        _learn_from_existing_finding, tenant.id, hunt_id, finding.id, job.id,
        payload.dataset_id, payload.find_dataset, model,
    )
    return job


@router.post("/{finding_id}/missed-context", response_model=FindingOut)
def add_missed_context(
    hunt_id: int,
    finding_id: int,
    payload: LearningNote,
    background: BackgroundTasks,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Add extra analyst context to a finding's lesson (records a learning note
    that is mirrored to RAG)."""
    if not payload.text.strip():
        raise HTTPException(status_code=422, detail="Context text is required.")
    finding = _resolve_finding(db, tenant.id, hunt_id, finding_id)
    background.add_task(_record_note_async, tenant.id, hunt_id, finding.id, payload.text)
    return finding


@router.post("/import", response_model=ImportFindingsResult)
def import_findings(
    hunt_id: int,
    payload: ImportFindingsCreate,
    background: BackgroundTasks,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Batch import (W3): paste one or more already-reported findings + their
    dataset; the model structures each (grounded), they're added validated, and
    each records a learning signal (training_hunt on a Training Hunt)."""
    if not payload.text.strip():
        raise HTTPException(status_code=422, detail="Paste at least one finding.")
    dataset, evidence = _dataset_evidence(db, tenant.id, hunt_id, payload.dataset_id)
    model = tenant_models.resolve_analyst_model(db, tenant.id)
    job = _new_learning_job(db, tenant.id, hunt_id, model, "Structuring imported findings…")
    try:
        out = training_import.structure_findings(dataset.filename, evidence, payload.text, model=model)
    except ollama.OllamaError as exc:
        _finish_job(db, job, error=str(exc))
        raise HTTPException(status_code=502, detail=f"Import failed: {exc}") from exc
    items = out.get("findings", [])
    if not items:
        from app.services import model_fit  # lazy: avoid import cost on hot paths
        _finish_job(db, job, error="No structured findings could be extracted.")
        raise HTTPException(
            status_code=422,
            detail=(
                "The model could not extract any structured findings — check the "
                "pasted text." + model_fit.weak_model_suffix(model)
            ),
        )

    from app.services.analysis_runner import _next_finding_seq  # lazy: avoid cycle
    start = _next_finding_seq(db, hunt_id)
    hunt = db.get(Hunt, hunt_id)
    source = "training_hunt" if hunt and hunt.kind == "training" else "missed_finding"

    created: list[Finding] = []
    for i, f in enumerate(items):
        created.append(_build_finding(tenant.id, hunt_id, dataset, start + i, f, evidence))
    db.add_all(created)
    db.commit()
    for finding in created:
        db.refresh(finding)
        doc_id = _promote_to_knowledge(db, finding)
        db.commit()
        if doc_id is not None:
            background.add_task(_index_doc_async, doc_id)
        background.add_task(
            _record_missed_async, tenant.id, hunt_id, finding.id,
            f"Imported: {finding.title}", "", source,
        )
    _finish_job(db, job, result={"imported": len(created), "kind": source})
    return {"count": len(created), "findings": created}


@router.patch("", response_model=list[FindingOut])
def bulk_update_findings(
    hunt_id: int,
    payload: FindingBulkUpdate,
    background: BackgroundTasks,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Bulk validate/reject. Validated findings are promoted to the KB."""
    if payload.status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid status")
    findings = (
        db.query(Finding)
        .filter(
            Finding.id.in_(payload.finding_ids),
            Finding.tenant_id == tenant.id,
            Finding.hunt_id == hunt_id,
        )
        .all()
    )
    doc_ids: list[int] = []
    for finding in findings:
        becoming_validated = payload.status == "validated" and finding.status != "validated"
        finding.status = payload.status
        if becoming_validated:
            doc_ids.append(_promote_to_knowledge(db, finding))
    db.commit()
    for doc_id in doc_ids:
        background.add_task(_index_doc_async, doc_id)
    return findings
