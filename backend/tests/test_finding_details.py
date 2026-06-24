"""Phase A — structured finding detail extraction for the correlation phase."""
from app.services import finding_details as fd

_EV = {
    "entities": {
        "users": ["camilo.burgos", "svc_integration"],
        "ips": ["100.27.38.176", "10.0.0.5"],
        "hosts": ["EP-01"],
    },
    "stats": {"time_range": {"start": "2026-05-20T00:14:00Z", "end": "2026-05-20T00:19:00Z"}},
    "behavioral": {
        "fan_out": [{"source_column": "ip", "target_column": "user",
                     "top_sources": [{"source": "100.27.38.176", "distinct_targets": 30,
                                      "events": 30, "time_span_min": 4.8}]}],
        "concentration": [{"column": "user", "dominant": True,
                           "top": [{"value": "svc_integration", "events": 60, "pct": 54.5}]}],
        "ip_classification": {"external_ips": ["100.27.38.176"],
                              "external_ip_count": 1, "internal_ip_count": 1},
    },
    "threat_intel": [{"indicator": "100.27.38.176", "type": "ip",
                      "attributes": {"Tags": "TOR Exit Node"}}],
    "targeted_rows": [{"user": "camilo.burgos", "ip": "100.27.38.176"}],
}


def test_extract_entities_types_and_recovers_from_evidence():
    finding = {
        "affected_users": ["camilo.burgos"],
        "affected_assets": ["EP-01"],
        "summary": "Spray from an external IP",
        "evidence": {"rows": ["100.27.38.176 authenticated camilo.burgos"]},
    }
    ents = fd.extract_entities(finding, _EV)
    assert ents["users"] == ["camilo.burgos"]
    assert ents["hosts"] == ["EP-01"]
    # The IP is only in the evidence text, not affected_assets — must be recovered.
    assert "100.27.38.176" in ents["ips"]


def test_build_carries_all_detail():
    d = fd.build({"affected_users": ["camilo.burgos"]}, _EV)
    assert d["time_range"]["start"].startswith("2026-05-20")
    assert set(d["behavioral_context"]) >= {"fan_out", "concentration", "ip_classification"}
    assert d["behavioral_context"]["threat_intel"][0]["indicator"] == "100.27.38.176"
    assert d["evidence_rows"] == [{"user": "camilo.burgos", "ip": "100.27.38.176"}]


def test_dataset_index_exposes_entities_for_cross_reference():
    idx = fd.dataset_index(_EV)
    assert "svc_integration" in idx["entities"]["users"]
    assert idx["time_range"]["end"].endswith("Z")
