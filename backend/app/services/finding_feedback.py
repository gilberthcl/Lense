"""
Finding disposition + revision helpers (W1).

The rich feedback loop on findings:
  • accept   → validated  (feedback optional)
  • reject   → rejected   (feedback required)
  • partial  → draft      (feedback required; triggers a model revision)

Pure helpers (validation, action→status mapping, snapshot, apply) are unit-tested
without a model; `revise()` is the one model-backed call (runs on the box).
"""
from __future__ import annotations

import json
from typing import Any

from app.services import ollama_client as ollama
from app.services import prompts

ACTIONS = ("accept", "reject", "partial")

# action → (finding.disposition, finding.status)
_ACTION_MAP = {
    "accept": ("accepted", "validated"),
    "reject": ("rejected", "rejected"),
    "partial": ("partial", "draft"),
}

# Fields the revision pass may rewrite. Evidence is deliberately excluded — it is
# ground truth and must never be model-rewritten.
REVISABLE_FIELDS = (
    "title", "category", "severity", "confidence", "summary",
    "mitre", "affected_assets", "affected_users", "recommendations",
)
# What we snapshot into a FindingRevision / send to the model for grounding.
_SNAPSHOT_FIELDS = REVISABLE_FIELDS + ("evidence", "evidence_rows", "entities")


def map_action(action: str) -> tuple[str, str]:
    """(disposition, status) for an action. Caller must validate() first."""
    return _ACTION_MAP[action]


def validate(action: str, feedback: str | None, score: int | None) -> str | None:
    """Return an error message if the disposition is invalid, else None."""
    if action not in ACTIONS:
        return f"Invalid action '{action}'. Use one of: {', '.join(ACTIONS)}."
    if action in ("reject", "partial") and not (feedback or "").strip():
        return f"'{action}' requires feedback explaining why."
    if score is not None and not (1 <= int(score) <= 10):
        return "Score must be between 1 and 10."
    return None


def snapshot(finding: Any) -> dict:
    """Serialise the revisable + grounding fields of a finding (for revisions and
    the revise prompt)."""
    return {f: getattr(finding, f, None) for f in _SNAPSHOT_FIELDS}


def apply_revised_fields(finding: Any, revised: dict) -> dict:
    """Apply a model revision onto a finding. Returns the fields actually changed.
    Ignores empty values and anything outside REVISABLE_FIELDS."""
    applied: dict = {}
    if not isinstance(revised, dict):
        return applied
    for field in REVISABLE_FIELDS:
        val = revised.get(field)
        if val in (None, "", [], {}):
            continue
        setattr(finding, field, val)
        applied[field] = val
    return applied


def diff_changes(before: dict, finding: Any) -> list[dict]:
    """Per-field before→after for the revisable fields that actually changed.
    `before` is a snapshot() taken prior to applying the revision."""
    changes: list[dict] = []
    for field in REVISABLE_FIELDS:
        old = before.get(field)
        new = getattr(finding, field, None)
        if old != new:
            changes.append({"field": field, "before": old, "after": new})
    return changes


def revision_meta(revised: dict) -> dict:
    """Pull the model's self-explanation out of a revise() response. Defensive:
    the model may omit or malform these. Never raises."""
    if not isinstance(revised, dict):
        return {"reasoning": None, "addressed": []}
    reasoning = revised.get("reasoning")
    addressed = []
    for item in revised.get("addressed") or []:
        if isinstance(item, dict) and str(item.get("point", "")).strip():
            addressed.append({
                "point": str(item["point"]).strip(),
                "addressed": bool(item.get("addressed", False)),
                "how": str(item.get("how") or "").strip() or None,
            })
    return {
        "reasoning": str(reasoning).strip() if reasoning else None,
        "addressed": addressed,
    }


def revise(finding_payload: dict, feedback: str) -> dict:
    """Ask the analyst model to rewrite a finding to satisfy feedback. Raises
    OllamaError on transport failure; returns {} if the response isn't an object."""
    sys = prompts.FINDING_REVISE_SYSTEM.format(guardrails=prompts.GUARDRAILS)
    user = prompts.FINDING_REVISE_PROMPT.format(
        finding_json=json.dumps(finding_payload, ensure_ascii=False, default=str)[:6000],
        feedback=(feedback or "").strip()[:1500],
    )
    out = ollama.parse_json_response(ollama.analyst(sys, user))
    return out if isinstance(out, dict) else {}
