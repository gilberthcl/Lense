"""
Pre-analysis planner.

Given a hunt's methodology and *metadata* about its uploaded CSV datasets
(filename, size, row/column counts, column names — never the contents), the
planner asks the analyst model to lay out an analysis plan: per-dataset
complexity, phases/batches, ordering rationale, and the QA approach. This runs
BEFORE the per-dataset analysis so the operator can review the plan first.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import Dataset, Hunt
from app.services import global_config
from app.services import ollama_client as ollama
from app.services import prompts


def planner_model() -> str:
    return global_config.current_ai()["analyst_model"]


def dataset_meta(db: Session, hunt_id: int, tenant_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(Dataset)
        .filter_by(hunt_id=hunt_id, tenant_id=tenant_id)
        .order_by(Dataset.created_at)
        .all()
    )
    out = []
    for d in rows:
        cols = d.columns or []
        # columns may be [{name,dtype}] or [str]; normalise to names
        names = [c.get("name") if isinstance(c, dict) else c for c in cols]
        out.append({
            "filename": d.filename,
            "size_bytes": d.file_size or 0,
            "rows": d.row_count or None,
            "cols": d.col_count or (len(names) or None),
            "columns": names,
        })
    return out


def _methodology_summary(hunt: Hunt) -> str:
    sections = hunt.methodology_sections or {}
    parts: list[str] = []
    if isinstance(sections, dict) and sections.get("available"):
        for t in sections.get("plan_of_action", {}).get("topics", []):
            mitre = f" ({t['mitre']})" if t.get("mitre") else ""
            parts.append(f"- {t['name']}{mitre}")
    if not parts and hunt.methodology_brief:
        for t in (hunt.methodology_brief or {}).get("topics", []):
            parts.append(f"- {t.get('name', '')}")
    return "\n".join(parts)


def _build_prompt(
    hunt: Hunt,
    metas: list[dict],
    *,
    feedback: str | None = None,
    previous: dict | None = None,
) -> tuple[str, str]:
    ds_lines = []
    for m in metas:
        size_kb = round((m["size_bytes"] or 0) / 1024, 1)
        cols = ", ".join(map(str, (m["columns"] or [])[:20]))
        ds_lines.append(
            f"- {m['filename']} | {size_kb} KB | "
            f"rows={m['rows'] if m['rows'] is not None else 'unknown'} | "
            f"cols={m['cols'] if m['cols'] is not None else 'unknown'} | "
            f"columns: {cols or 'unknown'}"
        )
    user = prompts.ANALYSIS_PLAN_PROMPT.format(
        hunt_name=hunt.name or "",
        methodology=_methodology_summary(hunt) or "No methodology summary available.",
        datasets="\n".join(ds_lines) or "No datasets uploaded.",
        count=len(metas),
    )
    if feedback:
        prev = json.dumps(previous)[:3000] if previous else "(none)"
        user += (
            "\n\nREVISION REQUEST — the analyst reviewed a previous plan and wants "
            "changes. Produce a revised plan that addresses the feedback while still "
            "covering every dataset.\nPrevious plan (JSON): "
            f"{prev}\nAnalyst feedback: {feedback}\n"
        )
    return prompts.ANALYSIS_PLAN_SYSTEM, user


def plan_stream(
    hunt: Hunt,
    metas: list[dict],
    *,
    on_chunk=None,
    feedback: str | None = None,
    previous: dict | None = None,
) -> dict[str, Any]:
    sys, user = _build_prompt(hunt, metas, feedback=feedback, previous=previous)
    raw = ollama.generate_stream(planner_model(), sys, user, on_chunk=on_chunk, json_mode=True)
    parsed = ollama.parse_json_response(raw)
    if not isinstance(parsed, dict):
        return {"summary": str(parsed)[:2000], "phases": [], "complexity": []}
    return parsed
