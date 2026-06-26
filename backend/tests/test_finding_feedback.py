"""Finding disposition + revision helpers (W1, pure)."""
from types import SimpleNamespace

from app.services import finding_feedback as ff


def test_validate_requires_feedback_for_reject_and_partial():
    assert ff.validate("reject", None, None)
    assert ff.validate("partial", "  ", None)
    assert ff.validate("accept", None, None) is None       # accept feedback optional
    assert ff.validate("reject", "false positive", None) is None


def test_validate_action_and_score_bounds():
    assert ff.validate("bogus", "x", None)
    assert ff.validate("accept", None, 0)
    assert ff.validate("accept", None, 11)
    assert ff.validate("accept", None, 7) is None


def test_map_action():
    assert ff.map_action("accept") == ("accepted", "validated")
    assert ff.map_action("reject") == ("rejected", "rejected")
    assert ff.map_action("partial") == ("partial", "draft")


def test_snapshot_includes_grounding_not_just_revisable():
    f = SimpleNamespace(
        title="t", category="suspicious", severity="high", confidence="high",
        summary="s", mitre=[], affected_assets=["WKSTN-01"], affected_users=["u"],
        recommendations="r", evidence={"v": 1}, evidence_rows=[{"x": 1}], entities={"users": ["u"]},
    )
    snap = ff.snapshot(f)
    assert snap["evidence"] == {"v": 1} and snap["title"] == "t"
    assert "evidence_rows" in snap and "entities" in snap


def test_apply_revised_fields_only_changes_nonempty_revisable():
    f = SimpleNamespace(
        title="old", severity="low", summary="old", evidence={"keep": 1},
        category="suspicious", confidence="low", mitre=[], affected_assets=[],
        affected_users=[], recommendations="",
    )
    applied = ff.apply_revised_fields(f, {
        "title": "new title", "severity": "high", "summary": "",  # empty ignored
        "evidence": {"hacked": 1},  # not revisable — must be ignored
    })
    assert applied == {"title": "new title", "severity": "high"}
    assert f.title == "new title" and f.severity == "high"
    assert f.summary == "old"               # empty value ignored
    assert f.evidence == {"keep": 1}        # evidence never rewritten


def test_apply_revised_fields_handles_non_dict():
    f = SimpleNamespace(title="x")
    assert ff.apply_revised_fields(f, ["not", "a", "dict"]) == {}


def test_diff_changes_reports_only_changed_revisable_fields():
    before = {"title": "old", "severity": "low", "summary": "s", "evidence": {"v": 1}}
    f = SimpleNamespace(
        title="new", severity="low", summary="s2", category=None, confidence=None,
        mitre=None, affected_assets=None, affected_users=None, recommendations=None,
    )
    changes = ff.diff_changes(before, f)
    fields = {c["field"] for c in changes}
    assert fields == {"title", "summary"}           # severity unchanged, evidence not revisable
    title = next(c for c in changes if c["field"] == "title")
    assert title["before"] == "old" and title["after"] == "new"


def test_revision_meta_extracts_reasoning_and_checklist():
    meta = ff.revision_meta({
        "reasoning": "  Raised severity and added MITRE.  ",
        "addressed": [
            {"point": "raise severity", "addressed": True, "how": "set to high"},
            {"point": "add T1003", "addressed": False, "how": "no evidence of LSASS access"},
            {"bad": "no point key"},   # dropped
        ],
    })
    assert meta["reasoning"] == "Raised severity and added MITRE."
    assert len(meta["addressed"]) == 2
    assert meta["addressed"][0] == {"point": "raise severity", "addressed": True, "how": "set to high"}
    assert meta["addressed"][1]["addressed"] is False


def test_revision_meta_defensive_on_garbage():
    assert ff.revision_meta(None) == {"reasoning": None, "addressed": []}
    assert ff.revision_meta({"addressed": "nope"}) == {"reasoning": None, "addressed": []}


def test_reflect_skips_model_when_no_feedback():
    # No feedback → no lesson to distil → no model call (returns empty).
    assert ff.reflect({"title": "x"}, "accept", "") == {}
    assert ff.reflect({"title": "x"}, "reject", "   ") == {}
