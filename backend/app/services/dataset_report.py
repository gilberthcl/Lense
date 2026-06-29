"""
Per-dataset analysis report — a durable, readable record of what the analysis of
a single dataset examined and concluded.

Persisted on `dataset.analysis_notes` after each analysis so it survives the
analysis job. It powers (a) the dataset report view in the UI, and (b) the
"find which dataset" lookup — the report's methodology match + entities let us
locate the source dataset of an offline finding WITHOUT re-analysing every CSV.

Pure assembly from already-computed pieces (no LLM call here).
"""
from __future__ import annotations

from typing import Any


def build(
    *,
    dataset_filename: str,
    analyst_model: str | None,
    dataset_focus: str | None,
    result: dict[str, Any],
    evidence: dict[str, Any],
    findings: list[dict],
    generated_at: str,
) -> dict[str, Any]:
    """Assemble the report dict. `findings` is the persisted-finding summary
    ([{ref,title,category,severity}, ...]); `result`/`evidence` come straight from
    the analysis pipeline."""
    trace = result.get("trace", {}) if isinstance(result, dict) else {}
    stats = evidence.get("stats") or {}
    entities = {k: v for k, v in (evidence.get("entities") or {}).items() if v}
    parse_ok = not trace.get("analyst_parse_error")

    return {
        "generated_at": generated_at,
        "model": analyst_model or "(global default)",
        "dataset": dataset_filename,
        # What the methodology said this dataset is the result of, and what to look
        # for — the same grounding the analyst received (matched PoA point + query
        # + indicators). Empty when no confident methodology match was found.
        "methodology_context": (dataset_focus or "").strip(),
        # The model's narrative read of the dataset.
        "assessment": (result.get("dataset_assessment") or "").strip() if isinstance(result, dict) else "",
        # What was found.
        "findings": findings,
        "found_count": len(findings),
        # Examined, nothing reportable — a clean result is a real outcome, not a
        # failure (distinct from a parse error, which is `parse_ok=False`).
        "clean": parse_ok and len(findings) == 0,
        "data_overview": {
            "rows": stats.get("row_count"),
            "cols": stats.get("col_count"),
            "columns": evidence.get("schema") or [],
            "entities": entities,
        },
        # Pipeline diagnostics — visible proof of what happened under the hood.
        "trace": {
            "parse_ok": parse_ok,
            "extracted": trace.get("analyst_count"),
            "dropped_empty": trace.get("dropped_empty"),
            "dropped_unsupported": trace.get("dropped_unsupported"),
            "analyst_secs": trace.get("analyst_secs"),
            "model_fit_warning": trace.get("model_fit_warning"),
        },
    }


def entity_pool(report: dict | None) -> set[str]:
    """All citable entity strings from a report's data overview, lowercased —
    used to match an offline finding's entities against candidate datasets."""
    if not isinstance(report, dict):
        return set()
    pool: set[str] = set()
    for vals in (report.get("data_overview", {}).get("entities") or {}).values():
        pool.update(str(v).lower() for v in (vals or []))
    return pool
