"""
Training-hunt review (W3) — "what I learned" from a historic hunt.

A training hunt carries confirmed findings (ground truth) plus the datasets they
came from. This pass asks the analyst model to articulate the DETECTION LOGIC it
learned — the patterns, their signals, and the false-positive lessons — so the
analyst can confirm/correct it before it informs future hunts. The accepted
review is recorded as a learning signal (RAG), like every other learning event.

Pure parsing (`parse_review`) is unit-tested; `summarize_learning` is the one
model-backed call.
"""
from __future__ import annotations

import json
from typing import Any

from app.services import global_config
from app.services import ollama_client as ollama
from app.services import prompts


def analyst_model() -> str:
    return global_config.current_ai()["analyst_model"]


def _compact_finding(f: dict) -> dict:
    """Just enough for the model to learn the logic — title, category, the
    grounded summary, and the entities/evidence it hinges on."""
    return {
        "finding_ref": f.get("finding_ref"),
        "title": f.get("title"),
        "category": f.get("category"),
        "severity": f.get("severity"),
        "summary": (f.get("summary") or "")[:600],
        "affected_assets": f.get("affected_assets"),
        "affected_users": f.get("affected_users"),
        "mitre": f.get("mitre"),
    }


def _feedback_block(feedback: str | None) -> str:
    fb = (feedback or "").strip()
    if not fb:
        return ""
    return (
        "\n\nREVIEWER FEEDBACK — your previous review was not quite right. Revise "
        "your understanding to address this:\n"
        f"{fb[:1500]}\n"
    )


def parse_review(out: Any) -> dict:
    """Normalise the model's review into a stable shape. Never raises."""
    if not isinstance(out, dict):
        return {"overview": "", "patterns": [], "false_positive_lessons": [], "takeaways": []}
    patterns = []
    for p in out.get("patterns") or []:
        if isinstance(p, dict) and str(p.get("name", "")).strip():
            patterns.append({
                "name": str(p["name"]).strip(),
                "signal": str(p.get("signal") or "").strip(),
                "category": str(p.get("category") or "").strip(),
                "rationale": str(p.get("rationale") or "").strip(),
            })

    def _strlist(key: str) -> list[str]:
        return [str(x).strip() for x in (out.get(key) or []) if str(x).strip()]

    return {
        "overview": str(out.get("overview") or "").strip(),
        "patterns": patterns,
        "false_positive_lessons": _strlist("false_positive_lessons"),
        "takeaways": _strlist("takeaways"),
    }


def summarize_learning(
    findings: list[dict], datasets: list[dict], feedback: str | None = None
) -> dict:
    """Run the review pass over a training hunt's findings + datasets. Returns the
    parsed review. Raises OllamaError on transport failure."""
    compact = [_compact_finding(f) for f in findings]
    sys = prompts.TRAINING_REVIEW_SYSTEM
    user = prompts.TRAINING_REVIEW_PROMPT.format(
        findings_json=json.dumps(compact, ensure_ascii=False, default=str)[:9000],
        datasets_json=json.dumps(datasets, ensure_ascii=False, default=str)[:4000],
    ) + _feedback_block(feedback)
    out = ollama.parse_json_response(ollama.analyst(sys, user))
    return parse_review(out)


def review_as_note(review: dict) -> str:
    """Render an accepted review as a retrievable learning note for RAG."""
    bits = []
    if review.get("overview"):
        bits.append(f"Detection logic learned: {review['overview']}")
    for p in review.get("patterns") or []:
        line = f"- {p['name']}"
        if p.get("signal"):
            line += f" — signal: {p['signal']}"
        if p.get("category"):
            line += f" (category: {p['category']})"
        bits.append(line)
    for fp in review.get("false_positive_lessons") or []:
        bits.append(f"Benign look-alike: {fp}")
    for t in review.get("takeaways") or []:
        bits.append(f"Takeaway: {t}")
    return "\n".join(bits)
