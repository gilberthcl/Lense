"""
Learning spine (W0) — the single entry point every learning signal flows through.

Whatever the source (a finding disposition, a missed-finding wizard, a training
hunt, a per-stage review), it calls `record_event`, which:
  1. persists a tenant-scoped `LearningEvent` (the durable record the training
     exporter reads), and
  2. mirrors the human-readable lesson into the per-tenant RAG knowledge base as a
     `learning_note` document, so the model benefits on the NEXT hunt with no
     fine-tune (the "immediate channel").

Strictly tenant-scoped: every write carries tenant_id; the RAG mirror inherits it.
The mirror is best-effort/fail-open — a missing Ollama never blocks the record.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import FindingRevision, KnowledgeDocument, LearningEvent
from app.services import knowledge

logger = logging.getLogger("lens.learning")

LEARNING_NOTE = "learning_note"

VALID_STAGES = {
    "methodology", "plan", "analysis", "correlation", "qa", "writing", "finding",
}
VALID_SOURCES = {"live_feedback", "training_hunt", "missed_finding", "import"}


def record_event(
    db: Session, *, tenant_id: int, stage: str, source: str,
    hunt_id: int | None = None, target_type: str | None = None,
    target_id: int | None = None, disposition: str | None = None,
    score: int | None = None, feedback_text: str | None = None,
    summary: str | None = None, author: str | None = None,
    mirror_to_knowledge: bool = True,
) -> LearningEvent:
    """Persist a learning signal and (optionally) mirror it into RAG knowledge."""
    ev = LearningEvent(
        tenant_id=tenant_id, hunt_id=hunt_id, stage=stage, source=source,
        target_type=target_type, target_id=target_id, disposition=disposition,
        score=score, feedback_text=feedback_text, summary=summary, author=author,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    if mirror_to_knowledge:
        _mirror_to_rag(db, ev)
    return ev


def _note_text(ev: LearningEvent) -> str:
    """Render a learning event as a retrievable lesson. Empty when there's no
    human-authored content worth retrieving (a bare disposition teaches nothing)."""
    if not (ev.feedback_text or ev.summary):
        return ""
    bits = [f"Stage: {ev.stage}."]
    if ev.disposition:
        d = ev.disposition + (f" (score {ev.score}/10)" if ev.score is not None else "")
        bits.append(f"Analyst disposition: {d}.")
    if ev.feedback_text:
        bits.append(f"Analyst feedback: {ev.feedback_text.strip()}")
    if ev.summary:
        bits.append(f"Lesson: {ev.summary.strip()}")
    return "\n".join(bits)


def _note_title(ev: LearningEvent) -> str:
    ref = f" {ev.target_type}#{ev.target_id}" if ev.target_type else ""
    return f"Learning · {ev.stage}{ref}"[:300]


def _mirror_to_rag(db: Session, ev: LearningEvent) -> None:
    """Create a tenant-scoped learning_note doc and embed it. Fail-open."""
    text = _note_text(ev)
    if not text:
        return
    try:
        doc = KnowledgeDocument(
            tenant_id=ev.tenant_id, doc_type=LEARNING_NOTE,
            title=_note_title(ev), content=text,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        knowledge.index_document_by_id(db, doc.id)  # fail-open inside
    except Exception:  # noqa: BLE001 — never let the RAG mirror break a record
        logger.exception("learning RAG mirror failed (event=%s)", ev.id)
        db.rollback()


def add_revision(
    db: Session, *, tenant_id: int, finding_id: int, content: dict | None,
    feedback_text: str | None = None,
) -> FindingRevision:
    """Append a finding revision (the before→feedback→after chain for partial
    accepts). Version auto-increments per finding."""
    top = (
        db.query(FindingRevision.version)
        .filter_by(tenant_id=tenant_id, finding_id=finding_id)
        .order_by(FindingRevision.version.desc())
        .first()
    )
    rev = FindingRevision(
        tenant_id=tenant_id, finding_id=finding_id,
        version=(top[0] + 1) if top else 1,
        content=content, feedback_text=feedback_text,
    )
    db.add(rev)
    db.commit()
    db.refresh(rev)
    return rev


def list_events(
    db: Session, tenant_id: int, *, hunt_id: int | None = None,
    stage: str | None = None, limit: int = 500,
) -> list[LearningEvent]:
    q = db.query(LearningEvent).filter_by(tenant_id=tenant_id)
    if hunt_id is not None:
        q = q.filter(LearningEvent.hunt_id == hunt_id)
    if stage is not None:
        q = q.filter(LearningEvent.stage == stage)
    return q.order_by(LearningEvent.id.desc()).limit(limit).all()


def list_revisions(db: Session, tenant_id: int, finding_id: int) -> list[FindingRevision]:
    return (
        db.query(FindingRevision)
        .filter_by(tenant_id=tenant_id, finding_id=finding_id)
        .order_by(FindingRevision.version)
        .all()
    )
