"""
Findings export — render a hunt's findings to downloadable formats:

  • CSV       — one row per finding (spreadsheet / Excel).
  • Markdown  — each finding as its own clearly-divided section (readable report).
  • JSON      — the full structured record, every field (nothing dropped).

Pure functions over plain dicts so they're unit-testable without the ORM. Tenant
isolation is the caller's responsibility (the endpoint scopes by tenant + hunt).
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any

# All persisted fields, in a sensible order. JSON export dumps every one of these;
# CSV/Markdown pick the human-facing subset below.
_FULL_FIELDS = (
    "finding_ref", "title", "category", "severity", "confidence", "status",
    "disposition", "score", "source_dataset", "summary", "mitre",
    "affected_assets", "affected_users", "recommendations", "reviewer_notes",
    "evidence", "entities", "time_range", "behavioral_context", "evidence_rows",
    "enrichment", "chain_id", "qa", "created_at",
)

# (key, header) for the flat CSV — the columns an analyst actually reads.
_CSV_COLUMNS = (
    ("finding_ref", "Ref"),
    ("title", "Title"),
    ("category", "Category"),
    ("severity", "Severity"),
    ("confidence", "Confidence"),
    ("status", "Status"),
    ("disposition", "Disposition"),
    ("score", "Score"),
    ("source_dataset", "Source dataset"),
    ("summary", "Summary"),
    ("mitre", "MITRE ATT&CK"),
    ("affected_assets", "Affected assets"),
    ("affected_users", "Affected users"),
    ("recommendations", "Recommendations"),
)


def flatten(v: Any) -> str:
    """Render a possibly-nested JSON value to a compact, human-readable string.
    Handles the common shapes our findings use (lists of strings, lists of MITRE
    dicts, {key: value} maps) so CSV/Markdown cells stay readable."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        parts = []
        for k, val in v.items():
            fv = flatten(val)
            if fv:
                parts.append(fv if isinstance(val, (list, dict)) else f"{k}: {fv}")
        return "; ".join(parts)
    if isinstance(v, (list, tuple)):
        items = []
        for x in v:
            if isinstance(x, dict):
                tid = x.get("id") or x.get("technique") or x.get("technique_id")
                nm = x.get("name") or x.get("title")
                if tid and nm:
                    items.append(f"{tid} ({nm})")
                elif tid or nm:
                    items.append(str(tid or nm))
                else:
                    val = x.get("value")
                    items.append(flatten(val) if val is not None else flatten(x))
            else:
                fx = flatten(x)
                if fx:
                    items.append(fx)
        return "; ".join(i for i in items if i)
    return str(v)


def to_csv(findings: list[dict]) -> str:
    """Flat CSV — one row per finding, headers from _CSV_COLUMNS."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([h for _, h in _CSV_COLUMNS])
    for f in findings:
        w.writerow([flatten(f.get(k)) for k, _ in _CSV_COLUMNS])
    return buf.getvalue()


def to_markdown(hunt_name: str, findings: list[dict]) -> str:
    """Readable report — each finding its own section, clearly divided."""
    out = [f"# Findings — {hunt_name}", "", f"_{len(findings)} finding(s)._", ""]
    for f in findings:
        out.append("---")
        out.append(f"## {f.get('finding_ref') or '?'}: {f.get('title') or 'Untitled finding'}")
        out.append("")
        meta = []
        for key, label in (("category", "Category"), ("severity", "Severity"),
                           ("confidence", "Confidence"), ("status", "Status"),
                           ("disposition", "Disposition"), ("score", "Score"),
                           ("source_dataset", "Source dataset")):
            val = flatten(f.get(key))
            if val:
                meta.append(f"**{label}:** {val}")
        if meta:
            out.append("  •  ".join(meta))
            out.append("")
        for key, label in (("summary", "Summary"), ("mitre", "MITRE ATT&CK"),
                           ("affected_assets", "Affected assets"),
                           ("affected_users", "Affected users"),
                           ("evidence", "Evidence"),
                           ("recommendations", "Recommendations"),
                           ("reviewer_notes", "Analyst notes")):
            val = flatten(f.get(key))
            if val:
                out.append(f"### {label}")
                out.append(val)
                out.append("")
    return "\n".join(out).rstrip() + "\n"


def to_json(meta: dict, findings: list[dict]) -> str:
    """Full structured export — every field, nothing dropped."""
    return json.dumps(
        {**meta, "findings": findings}, ensure_ascii=False, indent=2, default=str
    )


def serialize_finding(f: Any) -> dict:
    """ORM Finding (or any object with these attrs) → a full plain dict."""
    return {k: getattr(f, k, None) for k in _FULL_FIELDS}
