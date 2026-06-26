"""Learning spine (W0) — recording, RAG mirror, revisions, tenant isolation."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import FindingRevision, KnowledgeDocument, LearningEvent
from app.services import learning
from tests.isolation import assert_tenant_scoped


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    for model in (LearningEvent, FindingRevision, KnowledgeDocument):
        model.__table__.create(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def test_record_event_persists_fields(db):
    ev = learning.record_event(
        db, tenant_id=1, stage="finding", source="live_feedback",
        hunt_id=7, target_type="finding", target_id=42,
        disposition="rejected", score=3, feedback_text="Known scanner, benign.",
        mirror_to_knowledge=False,
    )
    assert ev.id and ev.tenant_id == 1 and ev.disposition == "rejected" and ev.score == 3


def test_list_events_is_tenant_scoped(db):
    learning.record_event(db, tenant_id=1, stage="finding", source="live_feedback",
                          feedback_text="t1 a", mirror_to_knowledge=False)
    learning.record_event(db, tenant_id=1, stage="qa", source="live_feedback",
                          feedback_text="t1 b", mirror_to_knowledge=False)
    learning.record_event(db, tenant_id=2, stage="finding", source="live_feedback",
                          feedback_text="t2 a", mirror_to_knowledge=False)
    rows = learning.list_events(db, 1)
    assert len(rows) == 2
    assert_tenant_scoped(rows, 1, label="learning.list_events")


def test_list_events_filters_by_stage(db):
    learning.record_event(db, tenant_id=1, stage="finding", source="live_feedback",
                          mirror_to_knowledge=False)
    learning.record_event(db, tenant_id=1, stage="qa", source="live_feedback",
                          mirror_to_knowledge=False)
    assert len(learning.list_events(db, 1, stage="qa")) == 1


def test_revisions_version_and_scope(db):
    learning.add_revision(db, tenant_id=1, finding_id=5, content={"v": 1})
    learning.add_revision(db, tenant_id=1, finding_id=5, content={"v": 2}, feedback_text="tighten")
    learning.add_revision(db, tenant_id=2, finding_id=5, content={"other": True})
    revs = learning.list_revisions(db, 1, 5)
    assert [r.version for r in revs] == [1, 2]
    assert_tenant_scoped(revs, 1, label="learning.list_revisions")


def test_mirror_creates_learning_note(db, monkeypatch):
    # Avoid embeddings/pgvector: stub the indexer.
    monkeypatch.setattr(learning.knowledge, "index_document_by_id", lambda *_a, **_k: 0)
    learning.record_event(
        db, tenant_id=1, stage="analysis", source="live_feedback",
        disposition="rejected", score=2, feedback_text="This is normal admin behaviour.",
        mirror_to_knowledge=True,
    )
    docs = db.query(KnowledgeDocument).all()
    assert len(docs) == 1
    assert docs[0].doc_type == "learning_note" and docs[0].tenant_id == 1
    assert "normal admin behaviour" in docs[0].content


def test_summarize_events_aggregates_per_stage():
    from types import SimpleNamespace

    def ev(stage, score=None, disp=None, fb=None):
        return SimpleNamespace(stage=stage, score=score, disposition=disp,
                               feedback_text=fb, summary=None)
    events = [  # newest-first, like list_events
        ev("qa", score=8, disp="accepted", fb="good"),
        ev("qa", score=6, disp="needs_work", fb="tighten"),
        ev("finding", disp="rejected"),
    ]
    out = learning.summarize_events(events)
    assert out["total"] == 3
    qa = out["by_stage"]["qa"]
    assert qa["count"] == 2 and qa["avg_score"] == 7.0
    assert qa["dispositions"] == {"accepted": 1, "needs_work": 1}
    assert len(qa["recent"]) == 2
    # a stage with no scores → avg None
    assert out["by_stage"]["finding"]["avg_score"] is None


def test_mirror_skipped_without_human_content(db, monkeypatch):
    monkeypatch.setattr(learning.knowledge, "index_document_by_id", lambda *_a, **_k: 0)
    # A bare disposition with no feedback/summary teaches nothing → no RAG note.
    learning.record_event(db, tenant_id=1, stage="finding", source="live_feedback",
                          disposition="accepted", mirror_to_knowledge=True)
    assert db.query(KnowledgeDocument).count() == 0
