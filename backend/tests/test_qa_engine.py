"""QA engine — deterministic process + finding checks."""
from types import SimpleNamespace

from app.services import qa_engine, qa_runner

_IDX = {8: {"entities": {"users": ["jdoe"], "hosts": ["wkstn-01"]}}}


def _finding(**kw):
    base = dict(
        finding_ref="F-001", dataset_id=8, category="suspicious", severity="medium",
        summary="x", evidence={"a": 1}, mitre=["T1110.003"], recommendations="do x",
        affected_assets=["WKSTN-01"], affected_users=["jdoe"], entities={"users": ["jdoe"]},
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
    assert by_stage["Correlation"] == "warn"         # not run yet ≠ failed
    assert by_stage["Methodology"] == "pass"


def test_parse_error_check_carries_dataset_meta():
    datasets = [SimpleNamespace(status="analyzed", id=7, filename="a.csv"),
                SimpleNamespace(status="analyzed", id=8, filename="b.csv")]
    checks = qa_engine.check_process(
        hunt=SimpleNamespace(methodology_text="m"), datasets=datasets,
        parse_error_datasets=[8], correlation_done=True,
    )
    integ = next(c for c in checks if c["stage"] == "Analysis integrity")
    assert integ["status"] == "fail"
    assert integ["fix"] == "reanalyze_datasets"
    assert integ["meta"]["dataset_ids"] == [8]
    assert integ["meta"]["dataset_names"] == ["b.csv"]


class _FakeDB:
    """Minimal stand-in for a Session covering rollback_qa's access patterns."""

    def __init__(self, report, findings):
        self._report = report
        self._findings = {f.id: f for f in findings}
        self.committed = False

    def query(self, _model):
        return self

    def filter_by(self, **_kw):
        return self

    def order_by(self, *_a):
        return self

    def first(self):
        return self._report

    def get(self, _model, fid):
        return self._findings.get(fid)

    def commit(self):
        self.committed = True


def test_rollback_restores_snapshotted_fields():
    finding = SimpleNamespace(id=1, tenant_id=2, mitre=["T1110.003"], recommendations="auto")
    report = SimpleNamespace(
        id=9, totals={"gap_filled": 1, "activity": ["did stuff"]},
        actions=[{
            "action": "gap_filled", "finding_ref": "F-001", "finding_id": 1,
            "fields": ["mitre", "recommendations"],
            "before": {"mitre": [], "recommendations": None}, "rolled_back": False,
        }],
    )
    db = _FakeDB(report, [finding])

    out = qa_runner.rollback_qa(db, hunt_id=5, tenant_id=2)

    assert out == {"reverted_findings": 1, "reverted_fields": 2}
    assert finding.mitre == [] and finding.recommendations is None  # restored
    assert report.actions[0]["rolled_back"] is True
    assert report.totals["gap_filled"] == 0
    # Idempotent: a second pass reverts nothing.
    assert qa_runner.rollback_qa(db, 5, 2)["reverted_findings"] == 0
