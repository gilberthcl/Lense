"""
Methodology comprehension — Phase 1 of the investigation protocol.

Before any dataset is touched, the engine reads the hunt methodology end to end
(plan of action, per-topic detection logic, MITRE mappings, and the executed
queries / which returned results) and distills a structured "hunt brief". That
brief is cached on the hunt and injected into every dataset analysis so the
Analyst knows what the hunt is about, what was covered, and what to expect.
"""
from __future__ import annotations

from typing import Any

from app.services import global_config
from app.services import ollama_client as ollama
from app.services import prompts


def analyst_model() -> str:
    return global_config.current_ai()["analyst_model"]


# A long methodology (this one is ~90k chars) blows past the model's context
# window, which truncates the doc and yields malformed JSON. Cap the input so it
# fits with room for the output. The DETERMINISTIC parse (topics/queries) is not
# affected — it runs separately and uses the full document.
_MAX_METHODOLOGY_CHARS = 24000

_DEGRADED_BRIEF = {
    "hunt_overview": "", "topics": [], "executed_queries": [], "what_to_expect": "",
    "note": ("AI comprehension of the methodology could not be parsed (likely too "
             "long for the model context). The deterministic methodology parse — "
             "plan of action and executed queries — is still used for analysis."),
    "degraded": True,
}


def _parse_brief(raw: str) -> dict[str, Any]:
    """Parse the comprehension response, degrading gracefully on failure so a
    long/odd methodology never hard-fails the hunt."""
    try:
        parsed = ollama.parse_json_response(raw)
    except ollama.OllamaError:
        return dict(_DEGRADED_BRIEF)
    if not isinstance(parsed, dict):
        return {**_DEGRADED_BRIEF, "raw": str(parsed)[:2000]}
    return parsed


def _feedback_block(feedback: str | None) -> str:
    """An appended instruction to correct a prior comprehension. Empty when none."""
    fb = (feedback or "").strip()
    if not fb:
        return ""
    return (
        "\n\nREVIEWER FEEDBACK — the previous comprehension was not quite right. "
        "Incorporate this correction in your revised understanding:\n"
        f"{fb[:1500]}\n"
        'Also add a top-level "revision_note" field (1-2 sentences) stating exactly '
        "what you changed in response to this feedback.\n"
    )


def comprehend_stream(
    methodology_text: str,
    *,
    edr: str | None = None,
    siem: str | None = None,
    language: str = "English",
    feedback: str | None = None,
    model: str | None = None,
    on_chunk=None,
) -> dict[str, Any]:
    """Streaming comprehension pass (for live progress). Returns the brief dict.
    `model` pins the call to the tenant's configured model (None → global default).
    When `feedback` is given, the model revises its prior understanding to address
    it (the regenerate-with-feedback loop)."""
    if not methodology_text or not methodology_text.strip():
        return {"hunt_overview": "", "topics": [], "executed_queries": [],
                "note": "No methodology document was provided for this hunt."}
    sys = prompts.METHODOLOGY_SYSTEM
    user = prompts.METHODOLOGY_PROMPT.format(
        edr=edr or "unspecified", siem=siem or "unspecified",
        language=language or "English",
        methodology=methodology_text[:_MAX_METHODOLOGY_CHARS],
    ) + _feedback_block(feedback)
    raw = ollama.generate_stream(
        model or analyst_model(), sys, user, on_chunk=on_chunk, json_mode=True,
    )
    return _parse_brief(raw)


def comprehend(
    methodology_text: str,
    *,
    edr: str | None = None,
    siem: str | None = None,
    language: str = "English",
    model: str | None = None,
) -> dict[str, Any]:
    """Run the LLM comprehension pass over the methodology. Returns the brief dict.
    `model` pins it to the tenant's configured model (None → global default)."""
    if not methodology_text or not methodology_text.strip():
        return {
            "hunt_overview": "",
            "scope": "",
            "topics": [],
            "executed_queries": [],
            "known_false_positives": [],
            "what_to_expect": "",
            "note": "No methodology document was provided for this hunt.",
        }

    sys = prompts.METHODOLOGY_SYSTEM
    user = prompts.METHODOLOGY_PROMPT.format(
        edr=edr or "unspecified",
        siem=siem or "unspecified",
        language=language or "English",
        methodology=methodology_text[:_MAX_METHODOLOGY_CHARS],
    )
    try:
        raw = ollama.analyst(sys, user, model=model)  # tenant's analyst model
    except ollama.OllamaError:
        return dict(_DEGRADED_BRIEF)
    return _parse_brief(raw)
