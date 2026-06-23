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


# Spanish layout: ES headings, "N." topic numbering, Descripción|Query|Resultados,
# a global MITRE line, and a query containing ` | ` pipes.
SAMPLE_ES = """\
Metodología
El flujo ROPC permite obtener tokens enviando credenciales directamente.
Plan de Acción
Se diseñó un plan estructurado en dos líneas de investigación.
Detección de autenticaciones ROPC anómalas en Entra ID
Sign-ins con authentication_protocol igual a ropc confirmando bypass de MFA.
Cuentas Member que utilizan ROPC por primera vez en 30 días.
Password spraying mediante ROPC
Múltiples intentos fallidos desde una misma IP contra distintas cuentas.
Queries de Threat Hunting
Plataformas: CrowdStrike Falcon LogScale | Google SecOps. MITRE ATT&CK: T1078.004, T1110.003, T1114.
1. Detección de autenticaciones ROPC anómalas en Entra ID

[TABLE]
Descripción | Query | Resultados
ROPC-01 (Google SecOps) Bypass de MFA confirmado | metadata.event_type = "USER_LOGIN" | result = "SUCCESS" | 0 eventos
ROPC-02 (Google SecOps) ROPC not-seen-before | metadata.log_type = "AZURE_AD" | 1240 eventos
[/TABLE]

2. Password spraying mediante ROPC

[TABLE]
Descripción | Query | Resultados
ROPC-10 (Google SecOps) Password spray multi-cuenta | metadata.event_type = "USER_LOGIN" |
[/TABLE]
"""


def test_unavailable_on_empty():
    assert mp.parse_methodology("")["available"] is False


def test_spanish_layout():
    r = mp.parse_methodology(SAMPLE_ES)
    assert r["available"] is True
    assert "ROPC" in r["description"]

    # ES Plan headings matched, 2 topics with indicators
    poa = r["plan_of_action"]
    assert len(poa["topics"]) == 2
    assert len(poa["topics"][0]["indicators"]) == 2

    # 'N.' numbered query topics, multiple per section
    q = r["queries"]
    assert len(q) == 2
    assert q[0]["number"] == 1 and len(q[0]["rows"]) == 2

    # Query cell with embedded pipe is preserved; ES counts parsed
    r01 = q[0]["rows"][0]
    assert r01["query"] == 'metadata.event_type = "USER_LOGIN" | result = "SUCCESS"'
    assert r01["result_count"] == 0 and r01["status"] == "no_results"
    assert q[0]["rows"][1]["result_count"] == 1240 and q[0]["rows"][1]["status"] == "results"
    assert q[1]["rows"][0]["status"] == "pending"  # empty Resultados

    # Global MITRE line picked up as coverage
    assert [m["technique"] for m in r["mitre_coverage"]] == ["T1078.004", "T1110.003", "T1114"]


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
