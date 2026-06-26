"""Behavioral evidence signals + threat-intel enrichment."""
from __future__ import annotations

import datetime

import pandas as pd

from app.services import csv_loader, enrichment


def _spray_df() -> pd.DataFrame:
    base = datetime.datetime(2026, 5, 20, 0, 14, 0)
    rows = []
    # One external IP authenticating 25 distinct users in a tight window.
    for i in range(25):
        rows.append({
            "timestamp": (base + datetime.timedelta(seconds=i * 10)).isoformat() + "Z",
            "user": f"user{i:03d}",
            "udm.principal.ip": "1.1.1.1",
            "user_agent": "Python Requests",
        })
    # An internal service account dominating its own event stream.
    for i in range(50):
        rows.append({
            "timestamp": (base + datetime.timedelta(minutes=i)).isoformat() + "Z",
            "user": "svc_app",
            "udm.principal.ip": "10.0.0.5",
            "user_agent": "UserContext",
        })
    return pd.DataFrame(rows)


def test_fan_out_detects_spray():
    ev = csv_loader.build_evidence_package(_spray_df(), sample_rows=3)
    fan = ev["behavioral"]["fan_out"]
    # The external IP -> user pair must surface with many distinct targets.
    sources = [s for pair in fan for s in pair["top_sources"]]
    spray = next(s for s in sources if s["source"] == "1.1.1.1")
    assert spray["distinct_targets"] == 25
    assert spray.get("time_span_min", 99) < 10  # tight window


def test_concentration_flags_dominant_actor():
    ev = csv_loader.build_evidence_package(_spray_df(), sample_rows=3)
    conc = ev["behavioral"]["concentration"]
    user_col = next(c for c in conc if c["column"] == "user")
    assert user_col["dominant"] is True
    assert user_col["top"][0]["value"] == "svc_app"


def test_ip_classification_splits_external_internal():
    ev = csv_loader.build_evidence_package(_spray_df(), sample_rows=3)
    ipc = ev["behavioral"]["ip_classification"]
    assert "1.1.1.1" in ipc["external_ips"]
    assert ipc["internal_ip_count"] == 1  # 10.0.0.5


def test_reputation_dataset_detection():
    ti_cols = ["indicator", "GTI Score", "Malicious Vendors", "Tags", "ASN"]
    assert enrichment.is_reputation_dataset(ti_cols) is True
    # A plain auth log is not a reputation dataset.
    assert enrichment.is_reputation_dataset(["timestamp", "user", "user_agent"]) is False


def test_threat_intel_join_enriches_matching_indicator():
    ev = csv_loader.build_evidence_package(_spray_df(), sample_rows=3)
    ti = pd.DataFrame([
        {"indicator": "1.1.1.1", "GTI Score": "72 - Suspicious",
         "Malicious Vendors": "14/91", "Tags": "TOR Exit Node", "ASN": "AS14061"},
        {"indicator": "8.8.8.8", "GTI Score": "0", "Malicious Vendors": "0/91",
         "Tags": "", "ASN": "AS15169"},
    ])
    index = enrichment.build_intel_index(ti)
    hits = enrichment.enrich_evidence(ev, index)
    # The spray IP is enriched; the unrelated clean IP is not.
    indicators = {h["indicator"] for h in hits}
    assert "1.1.1.1" in indicators
    assert "8.8.8.8" not in indicators
    spray = next(h for h in hits if h["indicator"] == "1.1.1.1")
    assert spray["attributes"]["Tags"] == "TOR Exit Node"
    # Enriched values are citable by the anti-hallucination gate.
    assert "tor exit node" in enrichment.intel_values(hits)
