"""
Sable assistant API (GLOBAL — no tenant scope, by design).

A general cybersecurity Q&A assistant. It NEVER receives client/tenant data, so
these routes take no tenant_id and never query the hunt pipeline. Rated answers
build a global learning corpus retrieved to sharpen future replies.
"""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import AssistantExchange
from app.services import assistant, global_config
from app.services import ollama_client as ollama

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.get("/identity")
def identity(db: Session = Depends(get_db)):
    """The assistant's display name + whether a custom icon is set (for the
    floating widget)."""
    plat = global_config.get_platform(db)
    return {
        "name": plat.get("assistant_name") or "Sable",
        "has_icon": bool(plat.get("assistant_icon_path")),
        "model": assistant.assistant_model(),
        "web": bool(plat.get("assistant_web")),
    }


@router.post("/chat")
def chat(
    question: str = Body(..., embed=True),
    history: list[dict] = Body(default=[], embed=True),
    web: bool | None = Body(default=None, embed=True),
    db: Session = Depends(get_db),
):
    """Ask Sable. Returns the answer + the exchange id (to rate it). History is
    the recent turns from the client; no client/tenant data is accepted here.
    `web` enriches this single answer with live web results (overriding the global
    default); only the typed question is sent out, never client data."""
    if not (question or "").strip():
        raise HTTPException(status_code=422, detail="Ask a question.")
    try:
        ex = assistant.answer(db, question, history, web=web)
    except ollama.OllamaError as exc:
        raise HTTPException(status_code=502, detail=f"Sable is unavailable: {exc}") from exc
    return {"id": ex.id, "answer": ex.answer, "model": ex.model}


@router.post("/exchanges/{exchange_id}/rate")
def rate(
    exchange_id: int,
    score: int = Body(..., embed=True),
    feedback: str | None = Body(default=None, embed=True),
    db: Session = Depends(get_db),
):
    """Rate an answer 1–10. A high rating turns it into a teaching example that
    Sable retrieves to improve future answers (learning without retraining)."""
    if not 1 <= int(score) <= 10:
        raise HTTPException(status_code=422, detail="Score must be between 1 and 10.")
    ex = db.get(AssistantExchange, exchange_id)
    if ex is None:
        raise HTTPException(status_code=404, detail="Exchange not found.")
    assistant.rate(db, ex, score, feedback)
    return {"ok": True, "id": ex.id, "score": ex.score}
