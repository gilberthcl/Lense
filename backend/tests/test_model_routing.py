"""Per-client model routing — every pipeline stage must use the TENANT's model,
never the global default. Regression guard for the critical W0b precedence bug."""
from app.services import (
    correlation_engine as ce,
    finding_feedback as ff,
    findings_engine,
    methodology,
    missed_finding,
    training_import,
    training_review,
)


def _capture(monkeypatch, module):
    """Patch module.ollama.analyst to record the model kwarg and return empty JSON."""
    seen = {}

    def fake_analyst(sys, user, **kw):
        seen["model"] = kw.get("model")
        return "{}"

    monkeypatch.setattr(module.ollama, "analyst", fake_analyst)
    return seen


def test_finding_revise_routes_tenant_model(monkeypatch):
    seen = _capture(monkeypatch, ff)
    ff.revise({"title": "x"}, "tighten it", model="tenant-model:7b")
    assert seen["model"] == "tenant-model:7b"


def test_finding_reflect_routes_tenant_model(monkeypatch):
    seen = _capture(monkeypatch, ff)
    ff.reflect({"title": "x"}, "reject", "false positive", model="tenant-model:7b")
    assert seen["model"] == "tenant-model:7b"


def test_correlation_routes_tenant_model(monkeypatch):
    seen = _capture(monkeypatch, ce)
    ce.run_llm_correlation([{"finding_ref": "F-1"}], {"links": [], "clusters": []},
                           model="tenant-model:7b")
    assert seen["model"] == "tenant-model:7b"


def test_missed_finding_routes_tenant_model(monkeypatch):
    seen = _capture(monkeypatch, missed_finding)
    missed_finding.analyze("ds.csv", {}, "found it", model="tenant-model:7b")
    assert seen["model"] == "tenant-model:7b"


def test_training_import_routes_tenant_model(monkeypatch):
    seen = _capture(monkeypatch, training_import)
    training_import.structure_findings("ds.csv", {}, "a finding", model="tenant-model:7b")
    assert seen["model"] == "tenant-model:7b"


def test_training_review_routes_tenant_model(monkeypatch):
    seen = _capture(monkeypatch, training_review)
    training_review.summarize_learning([{"title": "x"}], [], model="tenant-model:7b")
    assert seen["model"] == "tenant-model:7b"


def test_methodology_comprehend_routes_tenant_model(monkeypatch):
    seen = _capture(monkeypatch, methodology)
    methodology.comprehend("some methodology text", model="tenant-model:7b")
    assert seen["model"] == "tenant-model:7b"


def test_dataset_analysis_routes_all_three_substeps_to_tenant_model(monkeypatch):
    # The analyst, the Senior Reviewer, AND the Writer must ALL run the tenant's
    # model — no sub-step may leak to the global default.
    calls = {}
    monkeypatch.setattr(
        findings_engine.ollama, "analyst",
        lambda s, u, **kw: (calls.__setitem__("analyst", kw.get("model")),
                            '{"findings":[{"title":"t","category":"suspicious"}]}')[1],
    )
    monkeypatch.setattr(
        findings_engine.ollama, "reviewer",
        lambda s, u, **kw: (calls.__setitem__("reviewer", kw.get("model")),
                            '{"reviewed_findings":[{"title":"t","category":"suspicious"}]}')[1],
    )
    monkeypatch.setattr(
        findings_engine.ollama, "qa",
        lambda s, u, **kw: (calls.__setitem__("qa", kw.get("model")),
                            '[{"title":"t","category":"suspicious"}]')[1],
    )
    findings_engine.analyze_dataset(
        dataset_name="ds.csv",
        evidence_package={"entities": {"users": ["jdoe"]}, "sample_rows": [{"u": "jdoe"}]},
        methodology="m",
        analyst_model="tenant-model:7b",
    )
    assert calls["analyst"] == "tenant-model:7b"
    assert calls["reviewer"] == "tenant-model:7b"   # was leaking to global before the fix
    assert calls["qa"] == "tenant-model:7b"         # was leaking to global before the fix


def test_none_model_falls_back_to_global(monkeypatch):
    # When a client has no configured model, None flows through (ollama applies
    # the global default itself) — never a hard-coded global at the call site.
    seen = _capture(monkeypatch, ff)
    ff.revise({"title": "x"}, "tighten it")
    assert seen["model"] is None
