"""Training-set exporter — example shape + readiness gate."""
import json
from types import SimpleNamespace

from app.services import training_export as tx


def _finding(**kw):
    base = dict(
        id=1, finding_ref="F-001", tenant_id=2, hunt_id=7, dataset_id=8,
        status="validated", title="ROPC spray", category="suspicious",
        severity="high", confidence="high", summary="A did B",
        evidence={"verbatim_values": ["camilo", "EP-01"]},
        mitre=[{"technique_id": "T1110.003", "name": "Password Spraying"}],
        affected_assets=["EP-01"], affected_users=["camilo"],
        recommendations="Investigate", reviewer_notes=None,
        entities={"users": ["camilo"]}, time_range={"start": "t"},
        behavioral_context={"fan_out": []}, evidence_rows=[{"x": 1}],
        source_dataset="ds8.csv", dataset=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_positive_example_is_valid_chat_jsonl():
    ex = tx.build_positive(_finding())
    assert [m["role"] for m in ex["messages"]] == ["system", "user", "assistant"]
    # user turn carries the evidence, not the answer
    assert "camilo" in ex["messages"][1]["content"]
    # assistant turn is the finding in the analyst output shape
    target = json.loads(ex["messages"][2]["content"])
    assert target["findings"][0]["title"] == "ROPC spray"
    assert target["findings"][0]["category"] == "suspicious"
    assert ex["meta"]["label"] == "positive" and ex["meta"]["finding_ref"] == "F-001"


def test_positive_target_omits_unsupported_assessment():
    # We don't persist a per-finding dataset_assessment; it must not be fabricated.
    target = tx.finding_target(_finding())
    assert "dataset_assessment" not in target


def test_negative_example_targets_empty_findings_and_keeps_reason():
    f = _finding(status="rejected", reviewer_notes="Known scanner, benign.")
    ex = tx.build_negative(f)
    target = json.loads(ex["messages"][2]["content"])
    assert target == {"findings": []}
    assert ex["meta"]["label"] == "negative"
    assert ex["meta"]["reason"] == "Known scanner, benign."
    assert ex["meta"]["rejected_title"] == "ROPC spray"


def test_input_context_prunes_empty_fields():
    ctx = tx.input_context(_finding(behavioral_context={}, time_range=None))
    assert "behavioral_context" not in ctx and "time_range" not in ctx
    assert "entities" in ctx


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def filter_by(self, **_kw):
        return self

    def filter(self, *_a):
        return self

    def order_by(self, *_a):
        return self

    def all(self):
        return self._rows


class _DB:
    def __init__(self, rows):
        self._rows = rows

    def query(self, _model):
        return _Query(self._rows)


def test_export_writes_jsonl_files(tmp_path):
    rows = [
        _finding(id=1, status="validated"),
        _finding(id=2, status="validated"),
        _finding(id=3, status="rejected", reviewer_notes="benign"),
    ]
    stats = tx.export_tenant(_DB(rows), tenant_id=2, out_root=tmp_path, min_validated=1)
    sft = tmp_path / "tenant_2"
    sft_files = list(sft.glob("*.sft.jsonl"))
    neg_files = list(sft.glob("*.negatives.jsonl"))
    assert len(sft_files) == 1 and len(neg_files) == 1
    sft_lines = sft_files[0].read_text(encoding="utf-8").splitlines()
    assert len(sft_lines) == 2  # two validated positives
    assert all(json.loads(line)["meta"]["label"] == "positive" for line in sft_lines)
    assert len(neg_files[0].read_text(encoding="utf-8").splitlines()) == 1
    assert stats["written"]["sft_examples"] == 2
    assert stats["ready_for_training"] is True  # min_validated=1


def test_stats_gate_and_thin_filtering():
    rows = (
        [_finding(id=i, status="validated") for i in range(3)]
        + [_finding(id=99, status="validated", evidence=None)]  # thin → skipped
        + [_finding(id=100, status="rejected")]
    )
    stats = tx.training_stats(_DB(rows), tenant_id=2)
    assert stats["validated"] == 4
    assert stats["eligible_positives"] == 3
    assert stats["thin_validated_skipped"] == 1
    assert stats["rejected"] == 1
    assert stats["ready_for_training"] is False  # 3 < MIN_VALIDATED
    assert stats["by_category"]["suspicious"] == 3
