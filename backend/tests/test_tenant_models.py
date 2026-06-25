"""Per-tenant model registry + promotion gate (in-memory SQLite)."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import TenantModel
from app.services import tenant_models as tm

_GOOD = {"precision": 0.9, "recall": 0.8, "f1": 0.85, "hallucination_rate": 0.03, "parse_error_rate": 0.0}


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    TenantModel.__table__.create(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def test_register_increments_version_per_tenant(db):
    a = tm.register(db, 1, base_model="llama3.1:8b", ollama_model_name="lens-t1-v1")
    b = tm.register(db, 1, base_model="llama3.1:8b", ollama_model_name="lens-t1-v2")
    other = tm.register(db, 2, base_model="llama3.1:8b", ollama_model_name="lens-t2-v1")
    assert (a.version, b.version, other.version) == (1, 2, 1)
    assert a.status == "validating"  # never live on registration


def test_resolve_is_none_until_active(db):
    tm.register(db, 1, base_model="b", ollama_model_name="lens-t1-v1")
    assert tm.resolve_analyst_model(db, 1) is None  # inert: no active model


def test_promote_blocked_without_eval(db):
    m = tm.register(db, 1, base_model="b", ollama_model_name="lens-t1-v1")
    with pytest.raises(tm.PromotionBlocked):
        tm.promote(db, m)  # no eval run yet


def test_promote_blocked_on_regression(db):
    m = tm.register(db, 1, base_model="b", ollama_model_name="lens-t1-v1")
    worse = {**_GOOD, "recall": 0.6}  # -0.2 recall vs baseline
    tm.record_eval(db, m, candidate_metrics=worse, baseline_metrics=_GOOD)
    assert m.comparison["regressed"] is True
    with pytest.raises(tm.PromotionBlocked):
        tm.promote(db, m)


def test_promote_succeeds_and_demotes_prior_active(db):
    v1 = tm.register(db, 1, base_model="b", ollama_model_name="lens-t1-v1")
    tm.record_eval(db, v1, candidate_metrics=_GOOD, baseline_metrics=_GOOD)
    tm.promote(db, v1)
    assert v1.status == "active"
    assert tm.resolve_analyst_model(db, 1) == "lens-t1-v1"  # routing now active

    v2 = tm.register(db, 1, base_model="b", ollama_model_name="lens-t1-v2")
    better = {**_GOOD, "precision": 0.95}
    tm.record_eval(db, v2, candidate_metrics=better, baseline_metrics=_GOOD)
    tm.promote(db, v2)
    assert v2.status == "active"
    assert v1.status == "retired"             # only one active per tenant
    assert tm.resolve_analyst_model(db, 1) == "lens-t1-v2"


def test_tenant_isolation_in_resolve(db):
    v1 = tm.register(db, 1, base_model="b", ollama_model_name="lens-t1-v1")
    tm.record_eval(db, v1, candidate_metrics=_GOOD, baseline_metrics=_GOOD)
    tm.promote(db, v1)
    assert tm.resolve_analyst_model(db, 1) == "lens-t1-v1"
    assert tm.resolve_analyst_model(db, 2) is None  # tenant 2 unaffected


def test_set_status_cannot_activate(db):
    m = tm.register(db, 1, base_model="b", ollama_model_name="lens-t1-v1")
    with pytest.raises(tm.PromotionBlocked):
        tm.set_status(db, m, "active")
    assert tm.set_status(db, m, "rejected").status == "rejected"
