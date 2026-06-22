"""
Deterministic methodology parser.

Threat-hunt methodologies follow a fixed structure:

    THREAT HUNT METHODOLOGY  <title>
    MITRE ATT&CK Coverage    -> table: Technique | Tactic
    Methodology              -> description prose
    Plan of Action           -> intro + N hunt topics (title + indicator bullets)
    Definitions              -> per-topic deep-dive prose
    Queries                  -> per topic: "Topic N - name", "MITRE ATT&CK: ...",
                                table: Query Name / Purpose | Query | Outcome
    Hallazgos / Findings     -> example findings (optional)

This module splits that text (as produced by `doc_loader`, which emits tables as
`[TABLE] ... [/TABLE]` blocks with ` | `-separated cells) into structured
sections WITHOUT an LLM — so the three methodology sub-tabs (Description, Plan of
Action, Queries) are always faithful to the source document. The LLM layer adds
an "understanding" narrative on top; it never invents the queries or topics.
"""
from __future__ import annotations

import re
from typing import Any

# Section headings, in document order. Matching is case-insensitive on a
# stripped line that equals (or starts with) the heading.
_HEADINGS = [
    "mitre att&ck coverage",
    "methodology",
    "plan of action",
    "definitions",
    "queries",
    "hallazgos",
    "findings",
]

_TABLE_OPEN = "[TABLE]"
_TABLE_CLOSE = "[/TABLE]"


def _normalize(s: str) -> str:
    """Loose key for matching topic titles across sections ('&' vs 'and', spacing)."""
    s = s.lower().replace("&", "and")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


def _split_table_block(lines: list[str]) -> tuple[list[str], list[list[list[str]]]]:
    """Separate plain text lines from `[TABLE]` blocks. Returns (text_lines, tables)."""
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


def _heading_at(line: str) -> str | None:
    norm = line.strip().lower()
    for h in _HEADINGS:
        if norm == h:
            return h
    return None


def _sections(text: str) -> dict[str, list[str]]:
    """Slice the document into {heading: [lines]} by the known headings."""
    out: dict[str, list[str]] = {"_preamble": []}
    current = "_preamble"
    for raw in text.splitlines():
        h = _heading_at(raw)
        if h:
            current = h
            out.setdefault(current, [])
        else:
            out[current].append(raw)
    return out


def _paragraphs(lines: list[str]) -> list[str]:
    return [ln.strip() for ln in lines if ln.strip()]


def _result_count(outcome: str) -> int | None:
    """Pull the event count from an Outcome cell (tolerant of typos like 'evets')."""
    if not outcome:
        return None
    m = re.search(r"(\d[\d.,]*)\s*ev", outcome, re.IGNORECASE)
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", "").replace(".", ""))
    except ValueError:
        return None


def _query_status(outcome: str, count: int | None) -> str:
    low = (outcome or "").strip().lower()
    if count is None:
        if not low or low in {"ignored", "blank"}:
            return "pending"
        return "unknown"
    return "no_results" if count == 0 else "results"


def _parse_mitre_coverage(tables: list[list[list[str]]]) -> list[dict[str, str]]:
    if not tables:
        return []
    rows = tables[0]
    out = []
    for r in rows[1:]:  # skip header
        if len(r) >= 2:
            out.append({"technique": r[0], "tactic": r[1]})
    return out


def _parse_queries(lines: list[str]) -> list[dict[str, Any]]:
    """Parse the Queries section: 'Topic N - name' + 'MITRE: ...' + a table."""
    topics: list[dict[str, Any]] = []
    i = 0
    topic_re = re.compile(r"^topic\s+(\d+)\s*[–\-:]\s*(.+)$", re.IGNORECASE)
    mitre_re = re.compile(r"^mitre att&ck:\s*(.+)$", re.IGNORECASE)
    while i < len(lines):
        m = topic_re.match(lines[i].strip())
        if not m:
            i += 1
            continue
        topic = {
            "number": int(m.group(1)),
            "name": m.group(2).strip(),
            "mitre": "",
            "rows": [],
        }
        i += 1
        # optional MITRE line, then a table
        while i < len(lines) and lines[i].strip() != _TABLE_OPEN:
            mm = mitre_re.match(lines[i].strip())
            if mm:
                topic["mitre"] = mm.group(1).strip()
            if topic_re.match(lines[i].strip()):  # next topic with no table
                break
            i += 1
        if i < len(lines) and lines[i].strip() == _TABLE_OPEN:
            block, tables = _split_table_block(lines[i:_table_end(lines, i) + 1])
            rows = tables[0] if tables else []
            for r in rows[1:]:  # skip header row
                if len(r) >= 2:
                    # The Query cell embeds ` | ` (CrowdStrike pipe syntax), so it
                    # over-splits. Name and Outcome never contain a pipe → take
                    # the first and last cells; rejoin the middle as the query.
                    name = r[0]
                    if len(r) >= 3:
                        outcome = r[-1]
                        query = " | ".join(r[1:-1])
                    else:
                        outcome, query = "", r[1]
                    count = _result_count(outcome)
                    topic["rows"].append({
                        "name": name,
                        "query": query,
                        "outcome": outcome,
                        "result_count": count,
                        "status": _query_status(outcome, count),
                    })
            i = _table_end(lines, i) + 1
        topics.append(topic)
    return topics


def _table_end(lines: list[str], start: int) -> int:
    for j in range(start, len(lines)):
        if lines[j].strip() == _TABLE_CLOSE:
            return j
    return len(lines) - 1


def _tokens(s: str) -> set[str]:
    return set(_normalize(s).split())


def _parse_plan_of_action(lines: list[str], topic_names: list[str]) -> dict[str, Any]:
    """
    Split the Plan of Action prose into intro + per-topic indicator bullets.

    Topics appear in the same order as in the Queries section but their titles
    may carry suffixes (e.g. '(T1021.006)') or '&'/'and' variants. We therefore
    match the *next expected* topic by token overlap on short title lines, which
    is robust to those differences and to false positives in long indicators.
    """
    paras = _paragraphs(lines)
    expected = [_tokens(n) for n in topic_names]
    topics: list[dict[str, Any]] = []
    intro: list[str] = []
    closing: list[str] = []
    current: dict[str, Any] | None = None
    ptr = 0
    for p in paras:
        is_title = False
        if ptr < len(expected) and len(p) <= 140:
            want = expected[ptr]
            overlap = len(_tokens(p) & want) / max(1, len(want))
            if overlap >= 0.7:
                is_title = True
        if is_title:
            current = {"name": p, "indicators": []}
            topics.append(current)
            ptr += 1
        elif current is None:
            intro.append(p)
        elif ptr >= len(expected) and len(p) > 400:
            closing.append(p)  # trailing summary paragraph
        else:
            current["indicators"].append(p)
    return {
        "intro": " ".join(intro).strip(),
        "topics": topics,
        "closing": " ".join(closing).strip(),
    }


def parse_methodology(text: str) -> dict[str, Any]:
    """Parse raw methodology text into structured sections. Never raises."""
    if not text or not text.strip():
        return {"available": False}
    try:
        secs = _sections(text)

        cov_text, cov_tables = _split_table_block(secs.get("mitre att&ck coverage", []))
        mitre_coverage = _parse_mitre_coverage(cov_tables)

        desc_text, _ = _split_table_block(secs.get("methodology", []))
        description = "\n\n".join(_paragraphs(desc_text))

        queries = _parse_queries(secs.get("queries", []))
        topic_names = [t["name"] for t in queries]

        poa = _parse_plan_of_action(secs.get("plan of action", []), topic_names)
        # Attach MITRE from the matching query topic (same order) for display.
        for idx, t in enumerate(poa["topics"]):
            if idx < len(queries):
                t["mitre"] = queries[idx].get("mitre", "")

        total_queries = sum(len(t["rows"]) for t in queries)
        with_results = sum(
            1 for t in queries for r in t["rows"] if r["status"] == "results"
        )
        return {
            "available": True,
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
