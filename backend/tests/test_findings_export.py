"""Findings export — pure render functions (CSV / Markdown / JSON)."""
import csv
import io
import json

from app.services import findings_export as fx


def _sample():
    return [
        {
            "finding_ref": "F-001", "title": "Suspicious ROPC sign-ins",
            "category": "suspicious", "severity": "high", "confidence": "medium",
            "status": "validated", "disposition": "accepted", "score": 8,
            "source_dataset": "5-signins.csv",
            "summary": "External service accounts used ROPC.",
            "mitre": [{"id": "T1110", "name": "Brute Force"}],
            "affected_assets": ["host-1"], "affected_users": ["svc-acct"],
            "recommendations": "Disable ROPC.", "evidence": {"rows": 3},
        },
        {
            "finding_ref": "F-002", "title": "No Finding",
            "category": "unconfirmed", "severity": None, "confidence": None,
            "status": "draft", "disposition": None, "score": None,
            "source_dataset": "6-proc.csv", "summary": "", "mitre": {},
            "affected_assets": {}, "affected_users": {}, "recommendations": "",
        },
    ]


def test_flatten_handles_common_shapes():
    assert fx.flatten(None) == ""
    assert fx.flatten([]) == ""
    assert fx.flatten({}) == ""
    assert fx.flatten(["a", "b"]) == "a; b"
    assert fx.flatten([{"id": "T1110", "name": "Brute Force"}]) == "T1110 (Brute Force)"
    assert fx.flatten({"users": ["alice", "bob"]}) == "alice; bob"


def test_to_csv_has_header_and_one_row_per_finding():
    out = fx.to_csv(_sample())
    rows = list(csv.reader(io.StringIO(out)))
    assert rows[0][0] == "Ref" and "MITRE ATT&CK" in rows[0]
    assert len(rows) == 3  # header + 2 findings
    assert rows[1][0] == "F-001"
    assert "T1110 (Brute Force)" in rows[1]


def test_to_markdown_divides_each_finding():
    md = fx.to_markdown("Cred Access Hunt", _sample())
    assert "# Findings — Cred Access Hunt" in md
    assert md.count("\n---\n") == 2  # one divider per finding
    assert "## F-001: Suspicious ROPC sign-ins" in md
    assert "### Recommendations" in md


def test_to_json_is_full_and_parseable():
    payload = json.loads(fx.to_json({"hunt": "H", "count": 2}, _sample()))
    assert payload["count"] == 2
    assert payload["findings"][0]["evidence"] == {"rows": 3}  # full data preserved
