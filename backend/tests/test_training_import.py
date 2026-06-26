"""Training-hunt batch import — pure finding extraction (W3 slice 2)."""
from app.services import training_export, training_import as ti


def test_parse_findings_from_object_and_list():
    obj = {"findings": [{"title": "A"}, {"title": "B"}]}
    assert [f["title"] for f in ti.parse_findings(obj)] == ["A", "B"]
    bare = [{"title": "C"}, {"title": "D"}]
    assert [f["title"] for f in ti.parse_findings(bare)] == ["C", "D"]


def test_parse_findings_drops_titleless_and_bad_shapes():
    out = {"findings": [{"title": "ok"}, {"no_title": 1}, "string", None]}
    assert ti.parse_findings(out) == [{"title": "ok"}]
    assert ti.parse_findings("nope") == []
    assert ti.parse_findings({"other": 1}) == []


def test_exporter_labels_training_hunt_provenance():
    from types import SimpleNamespace
    live = SimpleNamespace(finding_ref="F-1", id=1, tenant_id=2, hunt_id=1,
                           dataset_id=3, category="suspicious", severity="high",
                           hunt=SimpleNamespace(kind="live"))
    hist = SimpleNamespace(finding_ref="F-2", id=2, tenant_id=2, hunt_id=9,
                           dataset_id=3, category="suspicious", severity="high",
                           hunt=SimpleNamespace(kind="training"))
    assert training_export._meta(live, "positive")["from_training_hunt"] is False
    assert training_export._meta(hist, "positive")["from_training_hunt"] is True
