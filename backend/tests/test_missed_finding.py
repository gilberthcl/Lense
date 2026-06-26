"""Missed-finding analysis — pure result parsing (W2)."""
from app.services import missed_finding as mf


def test_parse_result_full():
    out = {
        "finding": {"title": "ROPC spray", "category": "suspicious"},
        "why_missed": "Spread across many users, no single threshold tripped.",
        "lessons": "Aggregate ROPC by source IP, not per-user.",
    }
    f, why, lessons = mf.parse_result(out)
    assert f["title"] == "ROPC spray"
    assert "threshold" in why and "Aggregate" in lessons


def test_parse_result_tolerates_missing_and_bad_shapes():
    assert mf.parse_result({}) == ({}, None, None)
    assert mf.parse_result({"finding": "oops"}) == ({}, None, None)  # finding not a dict
    assert mf.parse_result(["nope"]) == ({}, None, None)
    f, why, lessons = mf.parse_result({"finding": {"title": "x"}, "why_missed": ""})
    assert f == {"title": "x"} and why is None and lessons is None  # empty → None


def test_lessons_summary_combines_or_empties():
    assert mf.lessons_summary("missed it", "do better") == "Why missed: missed it\nLessons: do better"
    assert mf.lessons_summary(None, "do better") == "Lessons: do better"
    assert mf.lessons_summary(None, None) == ""
