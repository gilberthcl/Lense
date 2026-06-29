"""Per-dataset analysis report assembly (pure)."""
from app.services import dataset_report as dr


def _evidence():
    return {
        "schema": ["UserPrincipalName", "IPAddress", "AppId"],
        "stats": {"row_count": 120, "col_count": 3},
        "entities": {"users": ["svc-a", "svc-b"], "ips": ["1.2.3.4"], "hosts": []},
    }


def test_build_report_with_findings():
    rep = dr.build(
        dataset_filename="5-signins.csv",
        analyst_model="cyberpal2.0-20b",
        dataset_focus="Topic 1: ROPC anomalous sign-ins [MITRE: T1110]",
        result={
            "dataset_assessment": "Multiple service accounts used ROPC.",
            "findings": [{}],
            "trace": {"analyst_count": 1, "dropped_empty": 0, "analyst_secs": 4.2},
        },
        evidence=_evidence(),
        findings=[{"ref": "F-001", "title": "ROPC abuse", "category": "suspicious", "severity": "high"}],
        generated_at="2026-06-29T00:00:00Z",
    )
    assert rep["found_count"] == 1
    assert rep["clean"] is False
    assert rep["model"] == "cyberpal2.0-20b"
    assert "T1110" in rep["methodology_context"]
    assert rep["data_overview"]["entities"]["users"] == ["svc-a", "svc-b"]
    assert rep["data_overview"]["entities"].get("hosts") is None  # empty dropped
    assert rep["trace"]["parse_ok"] is True


def test_clean_result_is_marked_clean_not_failed():
    rep = dr.build(
        dataset_filename="6-proc.csv", analyst_model=None, dataset_focus="",
        result={"dataset_assessment": "Nothing anomalous.", "findings": [], "trace": {}},
        evidence=_evidence(), findings=[], generated_at="2026-06-29T00:00:00Z",
    )
    assert rep["found_count"] == 0
    assert rep["clean"] is True          # examined, nothing reportable
    assert rep["trace"]["parse_ok"] is True


def test_parse_error_is_not_clean():
    rep = dr.build(
        dataset_filename="x.csv", analyst_model=None, dataset_focus="",
        result={"findings": [], "trace": {"analyst_parse_error": True}},
        evidence=_evidence(), findings=[], generated_at="2026-06-29T00:00:00Z",
    )
    assert rep["clean"] is False         # a parse failure is NOT a clean result
    assert rep["trace"]["parse_ok"] is False


def test_entity_pool_for_dataset_lookup():
    rep = dr.build(
        dataset_filename="x.csv", analyst_model=None, dataset_focus="",
        result={"findings": [], "trace": {}}, evidence=_evidence(),
        findings=[], generated_at="2026-06-29T00:00:00Z",
    )
    pool = dr.entity_pool(rep)
    assert "svc-a" in pool and "1.2.3.4" in pool
    assert dr.entity_pool(None) == set()
