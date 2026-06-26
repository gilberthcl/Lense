"""Analyst tools (global, not tenant-scoped). Tool 1: Data Sanitizer."""
from fastapi import APIRouter, Body, HTTPException

from app.services import sanitizer
from app.services import ollama_client as ollama

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.post("/sanitize")
def sanitize_text(text: str = Body(..., embed=True)):
    """Anonymize internal/proprietary entities and redact secrets in arbitrary
    text. Public IPs and external domains are preserved."""
    if not (text or "").strip():
        raise HTTPException(status_code=422, detail="Provide some text to sanitize.")
    try:
        return sanitizer.sanitize(text)
    except ollama.OllamaError as exc:
        raise HTTPException(status_code=502, detail=f"Sanitization failed: {exc}") from exc
