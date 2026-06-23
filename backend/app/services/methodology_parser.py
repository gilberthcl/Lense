"""
Deterministic, format-tolerant methodology parser.

Threat-hunt methodologies share a structure but not an exact format. They may be
in English or Spanish, use different headings, number topics as "Topic N -" or
"N.", and place one or several query tables per topic. This module splits the
document text (as produced by `doc_loader`, which renders tables as
`[TABLE] ... [/TABLE]` blocks with ` | `-separated cells) into structured
sections WITHOUT an LLM, so the Description / Plan of Action / Queries sub-tabs
stay faithful to the source. The LLM layer adds an "understanding" on top.

Canonical section keys: description, plan, definitions, queries, mitre, findings.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

_TABLE_OPEN = "[TABLE]"
_TABLE_CLOSE = "[/TABLE]"

# Heading aliases → canonical section key (accent/`&`-insensitive, EN + ES).
_EXACT = {
    "methodology": "description", "metodologia": "description",
    "plan of action": "plan", "plan de accion": "plan",
    "definitions": "definitions", "definiciones": "definitions",
    "hallazgos": "findings", "findings": "findings", "resultados": "findings",
}
_PREFIX = [
    ("queries", "queries"), ("consultas", "queries"), ("queries de", "queries"),
    ("cobertura mitre", "mitre"), ("mitre att ck coverage", "mitre"),
]

_TOPIC_RE = re.compile(r"^(?:topic\s+|tema\s+)?(\d+)\s*[.)\-–:]\s*(.+)$", re.IGNORECASE)
_MITRE_RE = re.compile(r"mitre\s*att&?ck\s*:?\s*(.+)", re.IGNORECASE)
_TECH_RE = re.compile(r"T\d{4}(?:\.\d{3})?")


def _normalize(s: str) -> str:
    """Accent-stripped, lowercased, alnum-spaced key for loose matching."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("&", " ")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _tokens(s: str) -> set[str]:
    return set(_normalize(s).split())


def _heading_at(line: str) -> str | None:
    s = line.strip()
    if not s or len(s) > 70:
        return None
    norm = _normalize(s)
    if norm in _EXACT:
        return _EXACT[norm]
    for pref, canon in _PREFIX:
        if norm == pref or norm.startswith(pref + " "):
            return canon
    return None


def _sections(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {"_pre": []}
    current = "_pre"
    for raw in text.splitlines():
        h = _heading_at(raw)
        if h:
            current = h
            out.setdefault(current, [])
        else:
            out[current].append(raw)
    return out


def _split_table_block(lines: list[str]) -> tuple[list[str], list[list[list[str]]]]:
    text: list[str] = []
    tables: list[list[list[str]]] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == _TABLE_OPEN:
            rows: list[list[str]] = []
            i += 1
            while i < len(lines) and lines[i].strip() != _TABLE_CLOSE:
                if lines[i].strip():
                    rows.append([c.strip() for c in lines[i].split(" | ")])
                i += 1
            tables.append(rows)
        else:
            text.append(lines[i])
        i += 1
    return text, tables


def _table_end(lines: list[str], start: int) -> int:
    for j in range(start, len(lines)):
        if lines[j].strip() == _TABLE_CLOSE:
            return j
    return len(lines) - 1


def _paragraphs(lines: list[str]) -> list[str]:
    return [ln.strip() for ln in lines if ln.strip()]


def _result_count(outcome: str) -> int | None:
    """Pull a count from an Outcome/Resultados cell (EN/ES, tolerant of typos)."""
    if not outcome:
        return None
    m = re.search(
        r"(\d[\d.,]*)\s*(?:events?|eventos?|evets?|resultados?|registros?|hits?|rows?|filas?)",
        outcome, re.IGNORECASE,
    )
    if m:
        token = m.group(1)
    elif re.fullmatch(r"\d[\d.,]*", outcome.strip()):
        token = outcome.strip()
    else:
        return None
    try:
        return int(token.replace(",", "").replace(".", ""))
    except ValueError:
        return None


def _query_status(outcome: str, count: int | None) -> str:
    low = (outcome or "").strip().lower()
    if count is None:
        return "pending" if (not low or low in {"ignored", "blank", "-"}) else "unknown"
    return "no_results" if count == 0 else "results"


def _parse_rows(rows: list[list[str]], out: list[dict]) -> None:
    for r in rows[1:]:  # skip the header row
        if len(r) < 2:
            continue
        name = r[0].strip()
        if not name:
            continue
        # The Query cell embeds ` | ` (CSF/YARA-L/SPL pipe syntax) → over-splits;
        # name and outcome never contain a pipe, so take first/last cells.
        if len(r) >= 3:
            outcome, query = r[-1], " | ".join(r[1:-1])
        else:
            outcome, query = "", r[1]
        count = _result_count(outcome)
        out.append({
            "name": name, "query": query, "outcome": outcome,
            "result_count": count, "status": _query_status(outcome, count),
        })


def _parse_queries(lines: list[str]) -> list[dict[str, Any]]:
    """Parse the Queries section: numbered topics, each with >=1 query tables."""
    topics: list[dict[str, Any]] = []
    i, n = 0, len(lines)
    while i < n:
        m = _TOPIC_RE.match(lines[i].strip())
        if not m:
            i += 1
            continue
        topic: dict[str, Any] = {
            "number": int(m.group(1)), "name": m.group(2).strip(),
            "mitre": "", "rows": [],
        }
        i += 1
        while i < n and not _TOPIC_RE.match(lines[i].strip()):
            s = lines[i].strip()
            if s == _TABLE_OPEN:
                end = _table_end(lines, i)
                _, tables = _split_table_block(lines[i:end + 1])
                if tables:
                    _parse_rows(tables[0], topic["rows"])
                i = end + 1
                continue
            mm = _MITRE_RE.search(s) if s else None
            if mm and not topic["mitre"]:
                topic["mitre"] = ", ".join(_TECH_RE.findall(mm.group(1))) or mm.group(1).strip()
            i += 1
        topics.append(topic)
    return topics


def _parse_plan(lines: list[str], topic_names: list[str]) -> dict[str, Any]:
    """Split Plan of Action prose into intro + per-topic indicator bullets."""
    paras = _paragraphs(lines)
    expected = [_tokens(nm) for nm in topic_names]
    topics: list[dict[str, Any]] = []
    intro: list[str] = []
    closing: list[str] = []
    current: dict[str, Any] | None = None
    ptr = 0
    for p in paras:
        is_title = False
        if ptr < len(expected) and len(p) <= 150:
            want = expected[ptr]
            if want and len(_tokens(p) & want) / max(1, len(want)) >= 0.6:
                is_title = True
        if is_title:
            current = {"name": p, "indicators": []}
            topics.append(current)
            ptr += 1
        elif current is None:
            intro.append(p)
        elif ptr >= len(expected) and len(p) > 300:
            closing.append(p)
        else:
            current["indicators"].append(p)
    return {"intro": " ".join(intro).strip(), "topics": topics, "closing": " ".join(closing).strip()}


def _parse_mitre_coverage(lines: list[str], full_text: str) -> list[dict[str, str]]:
    _, tables = _split_table_block(lines)
    if tables and tables[0]:
        return [
            {"technique": r[0], "tactic": r[1]}
            for r in tables[0][1:] if len(r) >= 2
        ]
    # Fallback: the richest "MITRE ATT&CK: T1078.004, T1110.003, ..." line anywhere.
    best: list[str] = []
    for m in _MITRE_RE.finditer(full_text):
        techs = _TECH_RE.findall(m.group(1))
        if len(techs) > len(best):
            best = techs
    return [{"technique": t, "tactic": ""} for t in best]


def parse_methodology(text: str) -> dict[str, Any]:
    """Parse raw methodology text into structured sections. Never raises."""
    if not text or not text.strip():
        return {"available": False}
    try:
        secs = _sections(text)

        mitre_coverage = _parse_mitre_coverage(secs.get("mitre", []), text)

        desc_text, _ = _split_table_block(secs.get("description", []))
        description = "\n\n".join(_paragraphs(desc_text))

        queries = _parse_queries(secs.get("queries", []))
        topic_names = [t["name"] for t in queries]

        poa = _parse_plan(secs.get("plan", []), topic_names)
        for idx, t in enumerate(poa["topics"]):
            if idx < len(queries) and queries[idx].get("mitre"):
                t["mitre"] = queries[idx]["mitre"]

        available = bool(description or poa["topics"] or queries)
        total_queries = sum(len(t["rows"]) for t in queries)
        with_results = sum(
            1 for t in queries for r in t["rows"] if r["status"] == "results"
        )
        return {
            "available": available,
            "mitre_coverage": mitre_coverage,
            "description": description,
            "plan_of_action": poa,
            "queries": queries,
            "stats": {
                "topic_count": len(queries) or len(poa["topics"]),
                "query_count": total_queries,
                "queries_with_results": with_results,
            },
        }
    except Exception:  # noqa: BLE001 — parsing must never break the pipeline
        return {"available": False}
