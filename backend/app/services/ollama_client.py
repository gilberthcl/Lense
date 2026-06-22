"""
Ollama client + multi-agent orchestration.

All calls go to a LOCAL Ollama instance. No data leaves the box, which is what
keeps tenant isolation intact. Models are Western-origin only (see config).

Agent roles:
  - Analyst  (gemma3:27b)  : reads evidence, proposes findings
  - Reviewer (gpt-oss:20b) : challenges findings, reduces false positives
  - QA       (gpt-oss:20b) : checks format/consistency against the finding spec
"""
from __future__ import annotations

import json

import httpx

from app.core.config import settings


class OllamaError(RuntimeError):
    pass


def _post(path: str, payload: dict) -> dict:
    url = f"{settings.ollama_base_url}{path}"
    try:
        with httpx.Client(timeout=settings.ollama_timeout) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:  # network, timeout, non-2xx
        raise OllamaError(f"Ollama call failed ({path}): {exc}") from exc


def generate(model: str, system: str, prompt: str, *, json_mode: bool = False) -> str:
    """Single non-streaming generation. Returns the raw text response."""
    payload: dict = {
        "model": model,
        "system": system,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2},  # low temp — analytical, deterministic-ish
    }
    if json_mode:
        payload["format"] = "json"
    data = _post("/api/generate", payload)
    return data.get("response", "")


def embed(text: str) -> list[float]:
    """Embed a single string with the configured embedding model."""
    data = _post("/api/embeddings", {"model": settings.ollama_embed_model, "prompt": text})
    vec = data.get("embedding")
    if not vec:
        raise OllamaError("Ollama returned no embedding")
    return vec


def parse_json_response(text: str) -> dict | list:
    """
    Best-effort JSON extraction. Local models sometimes wrap JSON in prose or
    fenced code blocks; recover the first balanced JSON object/array.
    """
    text = text.strip()
    if text.startswith("```"):
        # strip ```json ... ``` fences
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip().rstrip("`").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # fall back: locate first { or [ and matching close
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise OllamaError("Could not parse JSON from model response")


# Convenience wrappers per agent role -----------------------------------------
def analyst(system: str, prompt: str, *, json_mode: bool = True) -> str:
    return generate(settings.ollama_analyst_model, system, prompt, json_mode=json_mode)


def reviewer(system: str, prompt: str, *, json_mode: bool = True) -> str:
    return generate(settings.ollama_reviewer_model, system, prompt, json_mode=json_mode)


def qa(system: str, prompt: str, *, json_mode: bool = True) -> str:
    return generate(settings.ollama_qa_model, system, prompt, json_mode=json_mode)
