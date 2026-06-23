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

from app.services import global_config


class OllamaError(RuntimeError):
    pass


def _post(path: str, payload: dict) -> dict:
    cfg = global_config.current_ai()
    url = f"{cfg['base_url']}{path}"
    try:
        with httpx.Client(timeout=cfg["timeout"]) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:  # network, timeout, non-2xx
        raise OllamaError(f"Ollama call failed ({path}): {exc}") from exc


def _gen_options(cfg: dict) -> dict:
    return {
        "temperature": cfg["temperature"],
        # Cap output so a json_mode generation can't run to the context limit
        # (which truncates the JSON and breaks parsing).
        "num_predict": int(cfg.get("num_predict", 2048)),
        # Set the context window explicitly. Ollama's default (2048) would
        # silently truncate our prompt; sizing it to the trimmed prompt keeps
        # the whole thing in context without paying for a giant KV cache.
        "num_ctx": int(cfg.get("num_ctx", 8192)),
    }


def generate(model: str, system: str, prompt: str, *, json_mode: bool = False) -> str:
    """Single non-streaming generation. Returns the raw text response."""
    cfg = global_config.current_ai()
    payload: dict = {
        "model": model,
        "system": system,
        "prompt": prompt,
        "stream": False,
        "keep_alive": cfg.get("keep_alive", "30m"),  # keep the model warm
        "options": _gen_options(cfg),
    }
    if json_mode:
        payload["format"] = "json"
    data = _post("/api/generate", payload)
    return data.get("response", "")


def _role_model(role: str) -> str:
    """Model for a pipeline role. In single-model mode, reviewer/QA reuse the
    analyst model so Ollama never swaps a multi-GB model between calls."""
    cfg = global_config.current_ai()
    if cfg.get("single_model_pipeline", True):
        return cfg["analyst_model"]
    return cfg[f"{role}_model"]


def generate_stream(
    model: str,
    system: str,
    prompt: str,
    *,
    on_chunk=None,
    json_mode: bool = False,
) -> str:
    """
    Streaming generation. Calls `on_chunk(token)` as tokens arrive (for live
    progress/log feedback) and returns the full concatenated response text.
    """
    cfg = global_config.current_ai()
    url = f"{cfg['base_url']}/api/generate"
    payload: dict = {
        "model": model,
        "system": system,
        "prompt": prompt,
        "stream": True,
        "keep_alive": cfg.get("keep_alive", "30m"),
        "options": _gen_options(cfg),
    }
    if json_mode:
        payload["format"] = "json"
    parts: list[str] = []
    try:
        with httpx.Client(timeout=cfg["timeout"]) as client:
            with client.stream("POST", url, json=payload) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    tok = obj.get("response", "")
                    if tok:
                        parts.append(tok)
                        if on_chunk:
                            on_chunk(tok)
                    if obj.get("done"):
                        break
    except httpx.HTTPError as exc:
        raise OllamaError(f"Ollama stream failed (/api/generate): {exc}") from exc
    return "".join(parts)


def embed(text: str) -> list[float]:
    """Embed a single string with the configured embedding model."""
    model = global_config.current_ai()["embed_model"]
    data = _post("/api/embeddings", {"model": model, "prompt": text})
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
    return generate(global_config.current_ai()["analyst_model"], system, prompt, json_mode=json_mode)


def reviewer(system: str, prompt: str, *, json_mode: bool = True) -> str:
    return generate(_role_model("reviewer"), system, prompt, json_mode=json_mode)


def qa(system: str, prompt: str, *, json_mode: bool = True) -> str:
    return generate(_role_model("qa"), system, prompt, json_mode=json_mode)
