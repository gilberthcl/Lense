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


def comprehend_stream(
    methodology_text: str,
    *,
    edr: str | None = None,
    siem: str | None = None,
    language: str = "English",
    on_chunk=None,
) -> dict[str, Any]:
    """Streaming comprehension pass (for live progress). Returns the brief dict."""
    if not methodology_text or not methodology_text.strip():
        return {"hunt_overview": "", "topics": [], "executed_queries": [],
                "note": "No methodology document was provided for this hunt."}
    sys = prompts.METHODOLOGY_SYSTEM
    user = prompts.METHODOLOGY_PROMPT.format(
        edr=edr or "unspecified", siem=siem or "unspecified",
        language=language or "English", methodology=methodology_text,
    )
    raw = ollama.generate_stream(
        analyst_model(), sys, user, on_chunk=on_chunk, json_mode=True,
    )
    parsed = ollama.parse_json_response(raw)
    if not isinstance(parsed, dict):
        return {"hunt_overview": "", "topics": [], "executed_queries": [],
                "note": "Comprehension returned an unexpected shape.",
                "raw": str(parsed)[:4000]}
    return parsed


def comprehend(
    methodology_text: str,
    *,
    edr: str | None = None,
    siem: str | None = None,
    language: str = "English",
) -> dict[str, Any]:
    """Run the LLM comprehension pass over the methodology. Returns the brief dict."""
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
        methodology=methodology_text,
    )
    raw = ollama.analyst(sys, user)  # primary analyst model handles comprehension
    parsed = ollama.parse_json_response(raw)
    if not isinstance(parsed, dict):
        return {
            "hunt_overview": "",
            "topics": [],
            "executed_queries": [],
            "what_to_expect": "",
            "note": "Comprehension returned an unexpected shape; using raw text.",
            "raw": str(parsed)[:4000],
        }
    return parsed
