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
    """Rich methodology context for the planner — the comprehension brief plus
    the deterministically-parsed topics, so the planner understands what each
    dataset is for (not just a bare list of topic names)."""
    parts: list[str] = []
    brief = hunt.methodology_brief if isinstance(hunt.methodology_brief, dict) else {}
    if brief:
        if brief.get("hunt_overview"):
            parts.append(f"Overview: {brief['hunt_overview']}")
        if brief.get("scope"):
            parts.append(f"Scope: {brief['scope']}")
        topics = brief.get("topics") or []
        if topics:
            parts.append("Topics (what the hunt looks for):")
            for t in topics:
                mitre = t.get("mitre")
                mitre_s = ", ".join(mitre) if isinstance(mitre, list) else (mitre or "")
                head = f"- {t.get('name', '')}"
                if mitre_s:
                    head += f" [{mitre_s}]"
                if t.get("objective"):
                    head += f": {t['objective']}"
                parts.append(head)
                if t.get("expected_benign"):
                    parts.append(f"    expected-benign: {t['expected_benign']}")
        if brief.get("what_to_expect"):
            parts.append(f"What to expect in the data: {brief['what_to_expect']}")
        kfp = brief.get("known_false_positives") or []
        if kfp:
            parts.append("Known false positives: " + "; ".join(map(str, kfp)))

    # Fall back to (or supplement with) the deterministic plan-of-action topics.
    if not parts:
        sections = hunt.methodology_sections or {}
        if isinstance(sections, dict) and sections.get("available"):
            for t in sections.get("plan_of_action", {}).get("topics", []):
                mitre = f" ({t['mitre']})" if t.get("mitre") else ""
                parts.append(f"- {t['name']}{mitre}")
    return "\n".join(parts)[:4500]


def _dataset_block(metas: list[dict]) -> str:
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
    return "\n".join(ds_lines) or "No datasets uploaded."


def _build_prompt(
    hunt: Hunt,
    metas: list[dict],
    *,
    feedback: str | None = None,
    previous: dict | None = None,
    reasoning: str | None = None,
) -> tuple[str, str]:
    user = prompts.ANALYSIS_PLAN_PROMPT.format(
        hunt_name=hunt.name or "",
        methodology=_methodology_summary(hunt) or "No methodology summary available.",
        datasets=_dataset_block(metas),
        count=len(metas),
    )
    if reasoning:
        user += (
            "\n\nYOUR REASONING (you already worked this out step by step — convert "
            "it FAITHFULLY into the JSON schema above; do not contradict it):\n"
            f"{reasoning[:6000]}\n"
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
    on_reason_chunk=None,
    on_struct_chunk=None,
    on_phase=None,
    feedback: str | None = None,
    previous: dict | None = None,
) -> dict[str, Any]:
    """
    Two-pass plan generation:
      1. Reason out loud (plain text) about each dataset's role, complexity, and
         the workload batching — streamed to the caller for the live job log.
      2. Convert that reasoning into the strict plan JSON.
    """
    model = planner_model()
    methodology = _methodology_summary(hunt) or "No methodology summary available."

    # ── Pass 1: step-by-step reasoning (visible in the log) ───────────────
    if on_phase:
        on_phase("Reasoning through each dataset's role, complexity & batching")
    r_user = prompts.ANALYSIS_REASONING_PROMPT.format(
        hunt_name=hunt.name or "",
        methodology=methodology,
        datasets=_dataset_block(metas),
        count=len(metas),
    )
    if feedback:
        r_user += (
            "\n\nThe operator reviewed the previous plan and asked for changes. "
            f"Take this into account while reasoning. Feedback: {feedback}\n"
        )
    reasoning = ollama.generate_stream(
        model, prompts.ANALYSIS_REASONING_SYSTEM, r_user,
        on_chunk=on_reason_chunk, json_mode=False,
    )

    # ── Pass 2: structure the reasoning into the plan JSON ────────────────
    if on_phase:
        on_phase("Writing the structured plan")
    sys, user = _build_prompt(
        hunt, metas, feedback=feedback, previous=previous, reasoning=reasoning
    )
    raw = ollama.generate_stream(
        model, sys, user, on_chunk=on_struct_chunk, json_mode=True
    )
    parsed = ollama.parse_json_response(raw)
    if not isinstance(parsed, dict):
        return {"summary": str(parsed)[:2000], "phases": [], "complexity": []}
    return parsed
