"""
Missed-finding analysis (W2) — false-negative capture.

The analyst pastes a finding they found manually that the automated pass missed,
plus the dataset it came from. The model reconstructs the structured finding
(grounded in that dataset's evidence), diagnoses why it was missed, and distils
lessons. Those lessons are mirrored into RAG (so the next hunt benefits) and the
finding joins the training corpus as a positive the model originally missed.

`analyze` is the one model-backed call; `parse_result` is pure and tested.
"""
from __future__ import annotations

import json
from typing import Any

from app.services import ollama_client as ollama
from app.services import prompts


def analyze(dataset_name: str, evidence_package: dict, description: str,
            model: str | None = None) -> dict:
    """Run the missed-finding reconstruction. Raises OllamaError on transport
    failure; returns {} if the response isn't a JSON object. `model` pins it to
    the tenant's configured model (None → global default)."""
    sys = prompts.MISSED_FINDING_SYSTEM.format(guardrails=prompts.GUARDRAILS)
    user = prompts.MISSED_FINDING_PROMPT.format(
        dataset_name=dataset_name,
        evidence_json=json.dumps(evidence_package, ensure_ascii=False, default=str)[:7000],
        description=(description or "").strip()[:2000],
    )
    out = ollama.parse_json_response(ollama.analyst(sys, user, model=model))
    return out if isinstance(out, dict) else {}


def learn_logic(dataset_name: str, evidence_package: dict, description: str,
                model: str | None = None) -> tuple[str | None, str | None]:
    """Learn the DETECTION LOGIC behind a confirmed historical finding by analyzing
    it against its dataset. Returns (detection_logic, lesson). Tolerant: pulls the
    logic/lesson from whatever JSON the model returns. Raises OllamaError only on a
    transport failure."""
    sys = prompts.LEARN_LOGIC_SYSTEM.format(guardrails=prompts.GUARDRAILS)
    user = prompts.LEARN_LOGIC_PROMPT.format(
        dataset_name=dataset_name,
        evidence_json=json.dumps(evidence_package, ensure_ascii=False, default=str)[:7000],
        description=(description or "").strip()[:2000],
    )
    out = ollama.parse_json_response(ollama.analyst(sys, user, model=model))
    if not isinstance(out, dict):
        return None, None
    logic = out.get("detection_logic") or out.get("logic") or out.get("how") or None
    lesson = out.get("lesson") or out.get("lessons") or None
    return (str(logic).strip() if logic else None), (str(lesson).strip() if lesson else None)


def parse_result(out: Any) -> tuple[dict, str | None, str | None]:
    """Extract (finding_dict, why_missed, lessons) from a model response,
    tolerating missing keys / wrong shapes."""
    if not isinstance(out, dict):
        return {}, None, None
    finding = out.get("finding")
    finding = finding if isinstance(finding, dict) else {}
    why = out.get("why_missed")
    lessons = out.get("lessons")
    return finding, (why or None), (lessons or None)


def lessons_summary(why_missed: str | None, lessons: str | None) -> str:
    """Combine the why-missed + lessons into the LearningEvent summary that gets
    mirrored to RAG (empty when there's nothing to teach)."""
    parts = []
    if why_missed:
        parts.append(f"Why missed: {why_missed.strip()}")
    if lessons:
        parts.append(f"Lessons: {lessons.strip()}")
    return "\n".join(parts)
