"""Training-hunt review — pure parsing + note rendering (W3)."""
from app.services import training_review as tr


def test_parse_review_normalises_and_drops_bad_patterns():
    out = tr.parse_review({
        "overview": "  Credential access via LSASS.  ",
        "patterns": [
            {"name": "mimikatz", "signal": "sekurlsa::logonpasswords", "category": "malicious",
             "rationale": "direct LSASS read"},
            {"signal": "no name"},          # dropped — no name
            "not a dict",                    # dropped
        ],
        "false_positive_lessons": ["AV scanners read LSASS too", "  "],
        "takeaways": ["Baseline approved EDR processes"],
    })
    assert out["overview"] == "Credential access via LSASS."
    assert len(out["patterns"]) == 1
    assert out["patterns"][0]["name"] == "mimikatz"
    assert out["false_positive_lessons"] == ["AV scanners read LSASS too"]
    assert out["takeaways"] == ["Baseline approved EDR processes"]


def test_parse_review_defensive_on_garbage():
    empty = {"overview": "", "patterns": [], "false_positive_lessons": [], "takeaways": []}
    assert tr.parse_review(None) == empty
    assert tr.parse_review("nope") == empty


def test_review_as_note_renders_retrievable_lesson():
    note = tr.review_as_note({
        "overview": "Lateral movement via SMB.",
        "patterns": [{"name": "PsExec service install", "signal": "PSEXESVC", "category": "suspicious"}],
        "false_positive_lessons": ["Admin tooling uses PsExec legitimately"],
        "takeaways": ["Correlate service installs with source host"],
    })
    assert "Lateral movement via SMB." in note
    assert "PsExec service install" in note and "PSEXESVC" in note
    assert "Benign look-alike: Admin tooling" in note
    assert "Takeaway: Correlate service installs" in note
