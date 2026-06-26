"""
Sable — the in-app cybersecurity assistant (GLOBAL, isolated from client data).

Sable is a general threat-hunting / detection-engineering advisor. It is
DELIBERATELY walled off from the hunt pipeline: it never receives a tenant's
findings, datasets, knowledge base, or reports. That isolation is what lets it
run on a non-Western local model without breaking the local-only / no-client-
data compliance rule.

Learning without retraining: answers rated highly (1–10) are embedded and
retrieved as context to sharpen future replies — a single global corpus, since
there is no client data involved. A later fine-tune is a separate, deferred step.

Pure helpers (`cosine`, `build_prompt`, `rank`) are unit-tested; `answer` and
`rate` are the model/DB-backed calls.
"""
from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session

from app.models import AssistantExchange
from app.services import global_config
from app.services import ollama_client as ollama

DEFAULT_MODEL = "qwen2.5:7b"
# Only answers the analyst liked become retrievable teaching examples.
MIN_TEACHING_SCORE = 7
_MAX_HISTORY = 6
_MAX_Q = 4000

SYSTEM = """\
You are Sable, an expert cybersecurity assistant embedded in LENS, a threat-hunt
findings platform. You help analysts with: MITRE ATT&CK, detection engineering,
EDR/SIEM query languages (KQL, SPL, CrowdStrike), threat-hunting methodology,
malware/TTP explanations, and incident-response guidance.

Rules:
- You provide GENERAL cybersecurity knowledge and reasoning only.
- You do NOT have access to any client's hunt data, datasets, findings, or
  reports — that lives in the isolated hunt pipeline, not with you. If asked
  about a specific client's data, say you can't see it and suggest the relevant
  part of LENS instead.
- Be concrete and practical. Use examples and, where useful, sample queries.
- If you are unsure, say so rather than inventing specifics.
"""


def assistant_model() -> str:
    """The model powering Sable. Swappable via global config; defaults to a fast
    local model. Sable sees no client data, so model provenance is not gated."""
    try:
        cfg = global_config.current_ai()
    except Exception:  # noqa: BLE001 — config unavailable: fall back to default
        return DEFAULT_MODEL
    return cfg.get("assistant_model") or DEFAULT_MODEL


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity; 0.0 for empty/zero or mismatched-length vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def rank(query_vec: list[float], rows: list[Any], k: int = 3) -> list[Any]:
    """Top-k rows by cosine similarity of their .embedding to query_vec."""
    scored = [
        (cosine(query_vec, r.embedding or []), r)
        for r in rows
        if getattr(r, "embedding", None)
    ]
    scored.sort(key=lambda t: t[0], reverse=True)
    return [r for sim, r in scored[:k] if sim > 0.3]


def _history_block(history: list[dict] | None) -> str:
    if not history:
        return ""
    turns = [h for h in history if isinstance(h, dict) and h.get("content")][-_MAX_HISTORY:]
    lines = []
    for h in turns:
        who = "Analyst" if h.get("role") == "user" else "Sable"
        lines.append(f"{who}: {str(h['content']).strip()[:800]}")
    return "Conversation so far:\n" + "\n".join(lines) + "\n\n" if lines else ""


def _context_block(examples: list[AssistantExchange]) -> str:
    if not examples:
        return ""
    blocks = [
        f"Q: {e.question.strip()[:500]}\nA: {e.answer.strip()[:900]}"
        for e in examples
    ]
    return (
        "Highly-rated past answers for reference (reuse what's relevant, "
        "improve where you can):\n" + "\n---\n".join(blocks) + "\n\n"
    )


def build_prompt(question: str, history: list[dict] | None, examples: list) -> str:
    return (
        _context_block(examples)
        + _history_block(history)
        + f"Analyst's question:\n{question.strip()[:_MAX_Q]}"
    )


def _retrieve(db: Session, question: str, k: int = 3) -> list[AssistantExchange]:
    """Embed the question and return the top-k highly-rated past exchanges.
    Fail-soft: any embedding error yields no context (Sable still answers)."""
    try:
        qvec = ollama.embed(question)
    except ollama.OllamaError:
        return []
    rows = (
        db.query(AssistantExchange)
        .filter(AssistantExchange.score >= MIN_TEACHING_SCORE)
        .filter(AssistantExchange.embedding.isnot(None))
        .order_by(AssistantExchange.id.desc())
        .limit(200)
        .all()
    )
    return rank(qvec, rows, k=k)


def answer(db: Session, question: str, history: list[dict] | None = None) -> AssistantExchange:
    """Answer a question (with RAG context from highly-rated past answers) and
    persist the exchange. Raises OllamaError on transport failure."""
    examples = _retrieve(db, question)
    prompt = build_prompt(question, history, examples)
    model = assistant_model()
    reply = ollama.generate(model, SYSTEM, prompt, json_mode=False).strip()
    ex = AssistantExchange(question=question.strip()[:_MAX_Q], answer=reply, model=model)
    db.add(ex)
    db.commit()
    db.refresh(ex)
    return ex


def rate(db: Session, exchange: AssistantExchange, score: int, feedback: str | None) -> AssistantExchange:
    """Record a 1–10 rating. A high rating embeds the exchange so it becomes a
    retrievable teaching example (learning without retraining)."""
    exchange.score = int(score)
    if feedback is not None:
        exchange.feedback = feedback.strip() or None
    if exchange.score >= MIN_TEACHING_SCORE and not exchange.embedding:
        try:
            exchange.embedding = ollama.embed(f"{exchange.question}\n{exchange.answer}")
        except ollama.OllamaError:
            pass  # fail-soft — it just won't be retrievable until re-rated
    db.commit()
    db.refresh(exchange)
    return exchange
