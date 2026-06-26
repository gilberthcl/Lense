"""
Training-hunt batch finding import (W3 slice 2).

Structures one or more already-reported findings (pasted free text, e.g. from a
historic report) into the canonical shape, grounded in a dataset's evidence —
making it practical to load dozens of historic hunts. `structure_findings` is the
model call; `parse_findings` is pure and tested.
"""
from __future__ import annotations

import json
from typing import Any

from app.services import ollama_client as ollama
from app.services import prompts


def structure_findings(dataset_name: str, evidence_package: dict, text: str,
                       model: str | None = None) -> dict:
    """Run the batch-structuring model call. Raises OllamaError on transport
    failure; returns {} if the response isn't a JSON object/array. `model` pins it
    to the tenant's configured model (None → global default)."""
    sys = prompts.TRAINING_IMPORT_SYSTEM.format(guardrails=prompts.GUARDRAILS)
    user = prompts.TRAINING_IMPORT_PROMPT.format(
        dataset_name=dataset_name,
        evidence_json=json.dumps(evidence_package, ensure_ascii=False, default=str)[:7000],
        text=(text or "").strip()[:6000],
    )
    out = ollama.parse_json_response(ollama.analyst(sys, user, model=model))
    if isinstance(out, (dict, list)):
        return {"findings": parse_findings(out)}
    return {"findings": []}


def parse_findings(out: Any) -> list[dict]:
    """Extract the list of finding dicts from a model response, tolerating both
    {"findings": [...]} and a bare [...]. Drops anything without a title."""
    if isinstance(out, dict):
        items = out.get("findings")
    elif isinstance(out, list):
        items = out
    else:
        items = None
    return [f for f in (items or []) if isinstance(f, dict) and f.get("title")]
