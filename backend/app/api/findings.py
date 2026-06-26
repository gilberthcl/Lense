"""Findings listing + validation workflow (validated findings feed learning)."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_tenant
from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.models import Dataset, Finding, Hunt, KnowledgeDocument, Tenant
from app.schemas import (
    FindingBulkUpdate, FindingDisposition, FindingOut, FindingRegenerate,
    FindingRevisionResult, FindingStatusUpdate, ImportFindingsCreate,
    ImportFindingsResult, LearningNote, MissedFindingCreate, MissedFindingResult,
)
from app.services import (
    categories, csv_loader, finding_details, finding_feedback, knowledge,
    learning, missed_finding, training_import,
)
from app.services import ollama_client as ollama

router = APIRouter(prefix="/api/tenants/{tenant_id}/hunts/{hunt_id}/findings", tags=["findings"])

VALID_STATUSES = {"draft", "validated", "rejected"}


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
) -> None:
    """Capture a learning signal (event + RAG mirror) off the request path."""
    db = SessionLocal()
    try:
        learning.record_event(
            db, tenant_id=tenant_id, hunt_id=hunt_id, stage="finding",
            source="live_feedback", target_type="finding", target_id=finding_id,
            disposition=disposition, score=score, feedback_text=feedback,
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


@router.post("/{finding_id}/disposition", response_model=FindingOut)
def disposition_finding(
    hunt_id: int,
    finding_id: int,
    payload: FindingDisposition,
    background: BackgroundTasks,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Rich disposition (W1): accept / reject / partial, each with optional score
    and feedback. Sets disposition + status, promotes accepts to the KB, and
    captures a learning signal (which mirrors the lesson into RAG)."""
    err = finding_feedback.validate(payload.action, payload.feedback, payload.score)
    if err:
        raise HTTPException(status_code=422, detail=err)
    finding = _resolve_finding(db, tenant.id, hunt_id, finding_id)

    disposition, status = finding_feedback.map_action(payload.action)
    becoming_validated = status == "validated" and finding.status != "validated"
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
        disposition, payload.score, payload.feedback,
    )
    return finding


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
        revised = finding_feedback.revise(before, payload.feedback)
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

    try:
        out = missed_finding.analyze(dataset.filename, evidence, payload.description)
    except ollama.OllamaError as exc:
        raise HTTPException(status_code=502, detail=f"Analysis failed: {exc}") from exc
    f, why, lessons = missed_finding.parse_result(out)
    if not f.get("title"):
        raise HTTPException(
            status_code=422,
            detail="The model could not reconstruct a structured finding — add more detail.",
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
    return {"finding": finding, "why_missed": why, "lessons": lessons}


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
    try:
        out = training_import.structure_findings(dataset.filename, evidence, payload.text)
    except ollama.OllamaError as exc:
        raise HTTPException(status_code=502, detail=f"Import failed: {exc}") from exc
    items = out.get("findings", [])
    if not items:
        raise HTTPException(
            status_code=422,
            detail="The model could not extract any structured findings — check the pasted text.",
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
