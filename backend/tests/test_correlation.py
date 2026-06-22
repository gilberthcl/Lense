"""Unit tests for cross-dataset correlation (no DB / no network required)."""
from app.services import correlation


def _finding(**kw):
    base = {
        "id": kw.get("id", 1),
        "finding_ref": kw.get("finding_ref", "F-001"),
        "title": kw.get("title", "t"),
        "category": kw.get("category", "suspicious"),
        "dataset_id": kw.get("dataset_id", 1),
        "affected_assets": kw.get("affected_assets"),
        "affected_users": kw.get("affected_users"),
        "evidence": kw.get("evidence"),
    }
    return base


def test_classify_indicator():
    assert correlation._classify_indicator("10.0.0.5") == "ip"
    assert correlation._classify_indicator("999.1.1.1") is None  # invalid octet
    assert correlation._classify_indicator("a" * 64) == "hash"
    assert correlation._classify_indicator("evil.example.com") == "domain"
    assert correlation._classify_indicator("mimikatz.exe") is None  # file, not domain
    assert correlation._classify_indicator("not-an-ioc") is None


def test_as_str_list_handles_shapes():
    assert correlation._as_str_list(None) == []
    assert correlation._as_str_list("host1") == ["host1"]
    assert correlation._as_str_list(["a", "b"]) == ["a", "b"]
    assert correlation._as_str_list({"hosts": ["a"], "x": "b"}) == ["a", "b"]
    assert correlation._as_str_list(["nan", "-", "real"]) == ["real"]


def test_cross_dataset_correlation_detected():
    findings = [
        _finding(id=1, dataset_id=1, affected_assets=["WKSTN-01"], finding_ref="F-001"),
        _finding(id=2, dataset_id=2, affected_assets=["WKSTN-01"], finding_ref="F-002",
                 category="malicious"),
        _finding(id=3, dataset_id=1, affected_assets=["WKSTN-99"], finding_ref="F-003"),
    ]
    names = {1: "logons.csv", 2: "processes.csv"}
    out = correlation.compute_correlations(findings, names)

    corr = out["correlations"]
    assert len(corr) == 1  # only WKSTN-01 spans two datasets
    c = corr[0]
    assert c["value"] == "WKSTN-01"
    assert c["entity_type"] == "host"
    assert c["dataset_count"] == 2
    assert c["finding_count"] == 2
    assert c["max_category"] == "malicious"  # worst category wins
    assert {d["filename"] for d in c["datasets"]} == {"logons.csv", "processes.csv"}


def test_iocs_extracted_from_evidence():
    findings = [
        _finding(id=1, dataset_id=1,
                 evidence={"verbatim_values": ["185.220.101.5", "deadbeef" * 8]}),
        _finding(id=2, dataset_id=2,
                 evidence={"rows": ["conn to 185.220.101.5 detected"]}),
    ]
    out = correlation.compute_correlations(findings, {1: "a.csv", 2: "b.csv"})
    ioc_values = {i["value"]: i for i in out["iocs"]}
    assert "185.220.101.5" in ioc_values
    assert ioc_values["185.220.101.5"]["entity_type"] == "ip"
    assert ioc_values["185.220.101.5"]["finding_count"] == 2
    # the IP also spans two datasets, so it is a correlation candidate
    assert any(c["value"] == "185.220.101.5" for c in out["correlations"])


def test_no_finding_rows_ignored():
    findings = [
        _finding(id=1, dataset_id=1, category="no_finding", affected_assets=["HOST-A"]),
        _finding(id=2, dataset_id=2, category="no_finding", affected_assets=["HOST-A"]),
    ]
    out = correlation.compute_correlations(findings, {1: "a", 2: "b"})
    assert out["entity_count"] == 0
    assert out["correlations"] == []
