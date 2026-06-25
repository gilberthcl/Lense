"""QA engine — deterministic process + finding checks."""
from types import SimpleNamespace

from app.services import qa_engine

_IDX = {8: {"entities": {"users": ["camilo"], "hosts": ["ep-01"]}}}


def _finding(**kw):
    base = dict(
        finding_ref="F-001", dataset_id=8, category="suspicious", severity="medium",
        summary="x", evidence={"a": 1}, mitre=["T1110.003"], recommendations="do x",
        affected_assets=["EP-01"], affected_users=["camilo"], entities={"users": ["camilo"]},
        time_range={"start": "t"}, behavioral_context={"fan_out": []},
        source_dataset="ds8.csv", evidence_rows=[{"x": 1}],
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_complete_finding_passes():
    r = qa_engine.check_finding(_finding(), _IDX)
    assert r["status"] == "pass" and r["score"] == 100 and not r["gaps"]


def test_missing_fields_flagged_incomplete():
    r = qa_engine.check_finding(_finding(mitre=None, recommendations=None), _IDX)
    assert r["status"] == "incomplete"
    assert "mitre" in r["gaps"] and "recommendations" in r["gaps"]


def test_ungrounded_entity_is_critical():
    r = qa_engine.check_finding(_finding(affected_assets=["GHOST-PC"]), _IDX)
    assert r["status"] == "critical"
    assert any("GHOST-PC" in g for g in r["grounding_issues"])


def test_invalid_mitre_flagged():
    r = qa_engine.check_finding(_finding(mitre=["not-a-technique"]), _IDX)
    assert r["mitre_issues"]


def test_process_checks_detect_unanalyzed_and_no_correlation():
    datasets = [SimpleNamespace(status="analyzed"), SimpleNamespace(status="error")]
    hunt = SimpleNamespace(methodology_text="m")
    checks = qa_engine.check_process(
        hunt=hunt, datasets=datasets, parse_error_datasets=[], correlation_done=False
    )
    by_stage = {c["stage"]: c["status"] for c in checks}
    assert by_stage["Dataset analysis"] == "fail"    # one errored
    assert by_stage["Correlation"] == "fail"         # never ran
    assert by_stage["Methodology"] == "pass"
