"""Tests for the deterministic methodology parser."""
from app.services import methodology_parser as mp

# Mirrors the real doc_loader output shape (tables as [TABLE]..[/TABLE], ` | `).
SAMPLE = """\
THREAT HUNT METHODOLOGY
Lateral Movement
MITRE ATT&CK Coverage

[TABLE]
Technique ID & Name | Tactic
T1021 – Remote Services | Lateral Movement
T1078 – Valid Accounts | Privilege Escalation
[/TABLE]

Methodology
Lateral movement is a consequential phase of intrusion.
This hunt is strictly behavioral and context-driven.
Plan of Action
The investigation was structured into two hunt topics.
Remote Authentication via SMB and Windows Admin Shares
Connections to administrative shares from unexpected hosts.
Event ID 5140 and 5145 on the destination host.
Lateral Movement via RDP with Compromised Credentials
Event ID 4624 Logon Type 10 from non-admin workstations.
The two investigation lines provide comprehensive coverage of the techniques described above and close the plan with a deliberately long final paragraph that comfortably exceeds four hundred characters in length so that the parser reliably treats it as the closing summary of the plan rather than as an indicator bullet belonging to the last hunt topic, which is precisely what keeps the per-topic indicator lists clean, accurate, and faithful to the structure of the source methodology document exactly as it was originally written by the threat hunting analyst.
Definitions
Remote Authentication via SMB and Windows Admin Shares
SMB shares are a common lateral movement vector.
Queries
Topic 1 – Remote Authentication via SMB & Windows Admin Shares
MITRE ATT&CK: T1021.002 – SMB/Windows Admin Shares

[TABLE]
Query Name / Purpose | Query | Outcome
G01 – SMB Outbound Covers: Q01 | event_platform=Win | RemotePort=445 | table([a, b]) | 0 events in the last 30 days
G02 – SMB Scanning Covers: Q03 | groupBy([Host]) | distinct >= 5 | 9568 events in the last 30 days
[/TABLE]

Topic 2 – Lateral Movement via RDP with Compromised Credentials
MITRE ATT&CK: T1021.001 – Remote Desktop Protocol

[TABLE]
Query Name / Purpose | Query | Outcome
G03 – RDP Outbound Covers: Q04 | RemotePort=3389 | ignored
[/TABLE]
"""


def test_unavailable_on_empty():
    assert mp.parse_methodology("")["available"] is False


def test_full_parse():
    r = mp.parse_methodology(SAMPLE)
    assert r["available"] is True

    # MITRE coverage table
    assert len(r["mitre_coverage"]) == 2
    assert r["mitre_coverage"][0] == {"technique": "T1021 – Remote Services", "tactic": "Lateral Movement"}

    # Description prose
    assert "behavioral and context-driven" in r["description"]

    # Plan of Action: 2 topics in order, indicators captured, closing detached
    poa = r["plan_of_action"]
    assert len(poa["topics"]) == 2
    assert poa["topics"][0]["name"].startswith("Remote Authentication via SMB")
    assert len(poa["topics"][0]["indicators"]) == 2
    assert len(poa["topics"][1]["indicators"]) == 1
    assert "two investigation lines" in poa["closing"]
    assert poa["intro"]

    # MITRE attached to PoA topics from the matching query topic
    assert poa["topics"][0]["mitre"].startswith("T1021.002")


def test_query_table_pipe_handling_and_counts():
    r = mp.parse_methodology(SAMPLE)
    q = r["queries"]
    assert len(q) == 2
    t1 = q[0]
    assert t1["number"] == 1 and t1["mitre"].startswith("T1021.002")
    assert len(t1["rows"]) == 2

    g01 = t1["rows"][0]
    # Query cell embeds ` | ` — must be reconstructed, not truncated.
    assert g01["query"] == "event_platform=Win | RemotePort=445 | table([a, b])"
    assert g01["result_count"] == 0 and g01["status"] == "no_results"

    g02 = t1["rows"][1]
    assert g02["result_count"] == 9568 and g02["status"] == "results"

    # 'ignored' outcome -> pending, no count
    g03 = r["queries"][1]["rows"][0]
    assert g03["result_count"] is None and g03["status"] == "pending"

    assert r["stats"] == {"topic_count": 2, "query_count": 3, "queries_with_results": 1}
