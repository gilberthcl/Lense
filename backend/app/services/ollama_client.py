"""
Ollama client + multi-agent orchestration.

All calls go to a LOCAL Ollama instance. No data leaves the box, which is what
keeps tenant isolation intact. Models are Western-origin only (see config).

Agent roles (two-stage pipeline + optional reviewer):
  - Analyst/Extractor (gemma3:27b)  : reads evidence, extracts every finding
  - Reviewer          (gpt-oss:20b) : optional — challenges findings, cuts FPs
  - Writer/QA         (gpt-oss:20b) : rewrites findings in the approved format

In single_model_pipeline mode every role reuses the analyst model so Ollama
never swaps a multi-GB model between stages.
"""
from __future__ import annotations

import json
import logging
import time

import httpx

from app.services import global_config

logger = logging.getLogger("lens.ollama")


class OllamaError(RuntimeError):
    # retryable: a transient transport failure (connection refused/reset, the
    # model still loading) worth retrying. Timeouts are NOT retryable — the model
    # is genuinely too slow for the configured budget, so retrying just multiplies
    # the wait; the operator should raise the timeout or shrink the dataset.
    retryable: bool = True


def _retries() -> int:
    try:
        return max(0, int(global_config.current_ai().get("request_retries", 2)))
    except Exception:  # noqa: BLE001 — config unavailable, use a safe default
        return 2


def _with_retries(label: str, fn):
    """Run an Ollama call, retrying transient transport failures with backoff.

    This is the difference between "the analysis randomly failed" and a stable
    pipeline: a local Ollama under memory pressure or mid-model-load will reset
    or refuse a connection, and the next attempt a couple seconds later succeeds.
    """
    attempts = _retries() + 1
    last: OllamaError | None = None
    for i in range(attempts):
        try:
            return fn()
        except OllamaError as exc:
            last = exc
            if not getattr(exc, "retryable", True) or i + 1 >= attempts:
                raise
            delay = 1.5 * (2**i)
            logger.warning(
                "Ollama %s failed (attempt %d/%d): %s — retrying in %.1fs",
                label, i + 1, attempts, exc, delay,
            )
            time.sleep(delay)
    raise last  # pragma: no cover — loop always returns or raises above


def _post(path: str, payload: dict) -> dict:
    cfg = global_config.current_ai()
    url = f"{cfg['base_url']}{path}"
    try:
        with httpx.Client(timeout=cfg["timeout"]) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException as exc:
        err = OllamaError(
            f"Ollama timed out after {cfg['timeout']}s ({path}). The model is too "
            "slow for this prompt — raise the timeout in Config, or the dataset is "
            "very wide/large. Not retried."
        )
        err.retryable = False
        raise err from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404 and payload.get("model"):
            err = OllamaError(
                f"Model '{payload['model']}' is not installed in Ollama. Install it "
                "(Config → Models) or pick another model for this client (Settings)."
            )
            err.retryable = False
            raise err from exc
        raise OllamaError(f"Ollama call failed ({path}): {exc}") from exc
    except httpx.HTTPError as exc:  # connection refused/reset, non-2xx
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
    data = _with_retries(f"generate({model})", lambda: _post("/api/generate", payload))
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

    def _attempt() -> str:
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
        except httpx.TimeoutException as exc:
            err = OllamaError(f"Ollama stream timed out after {cfg['timeout']}s.")
            err.retryable = False
            raise err from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                err = OllamaError(
                    f"Model '{model}' is not installed in Ollama. Install it "
                    "(Config → Models) or pick another model for this client "
                    "(its Settings → Analyst model)."
                )
                err.retryable = False
                raise err from exc
            raise OllamaError(f"Ollama stream failed (/api/generate): {exc}") from exc
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama stream failed (/api/generate): {exc}") from exc
        return "".join(parts)

    return _with_retries(f"stream({model})", _attempt)


def list_models() -> list[dict]:
    """Installed Ollama models with name + size (bytes). [] if unreachable."""
    cfg = global_config.current_ai()
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(f"{cfg['base_url']}/api/tags")
            resp.raise_for_status()
            return [
                {"name": m.get("name", ""), "size": m.get("size", 0)}
                for m in resp.json().get("models", []) if m.get("name")
            ]
    except httpx.HTTPError:
        return []


def pull_model(name: str, on_progress=None) -> None:
    """Pull a model (Ollama name or `hf.co/<repo>` GGUF ref), streaming progress.
    Calls on_progress(status_str, pct_or_None) as it goes. Raises OllamaError on
    failure. GGUF-only by nature — Ollama never executes model-side code."""
    cfg = global_config.current_ai()
    try:
        with httpx.Client(timeout=None) as client:
            with client.stream("POST", f"{cfg['base_url']}/api/pull",
                               json={"name": name, "stream": True}) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if ev.get("error"):
                        raise OllamaError(f"Pull failed: {ev['error']}")
                    pct = None
                    if ev.get("total"):
                        pct = round(100 * ev.get("completed", 0) / ev["total"], 1)
                    if on_progress:
                        on_progress(ev.get("status", "pulling"), pct)
    except httpx.HTTPError as exc:
        raise OllamaError(f"Pull failed for {name}: {exc}") from exc


def create_model(name: str, modelfile: str) -> None:
    """Create (or overwrite) a named Ollama model from a Modelfile string. Used to
    provision per-client model variants — a variant FROM a base shares the base's
    weight blob (content-addressed dedup), so this costs ~no extra disk. Raises
    OllamaError on failure."""
    _with_retries(
        f"create({name})",
        lambda: _post("/api/create", {"name": name, "modelfile": modelfile, "stream": False}),
    )


def delete_model(name: str) -> None:
    """Remove a named Ollama model (its manifest). Shared weight blobs survive if
    another model still references them. Best-effort — never raises."""
    cfg = global_config.current_ai()
    try:
        with httpx.Client(timeout=cfg["timeout"]) as client:
            client.request("DELETE", f"{cfg['base_url']}/api/delete", json={"name": name})
    except httpx.HTTPError:
        pass


def embed(text: str) -> list[float]:
    """Embed a single string with the configured embedding model."""
    model = global_config.current_ai()["embed_model"]
    data = _with_retries(
        f"embed({model})", lambda: _post("/api/embeddings", {"model": model, "prompt": text})
    )
    vec = data.get("embedding")
    if not vec:
        raise OllamaError("Ollama returned no embedding")
    return vec


def _balanced_spans(text: str, opener: str, closer: str):
    """Yield each top-level balanced `opener…closer` span in `text`, string-aware
    (braces inside quoted strings don't count). Lets us recover a JSON object even
    when a reasoning model emits a 'thinking' preamble that itself contains braces
    — the first-{ to last-} heuristic fails on that, this doesn't."""
    depth = 0
    start = None
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == opener:
            if depth == 0:
                start = i
            depth += 1
        elif ch == closer and depth:
            depth -= 1
            if depth == 0 and start is not None:
                yield text[start : i + 1]
                start = None


def _salvage_truncated_json(text: str) -> dict | list | None:
    """
    Recover findings from a response that was cut off mid-JSON (the model hit its
    output-token limit). Cut to the last COMPLETE element and append the closing
    brackets needed to balance it — a truncated findings array still yields all
    the findings that finished. String-aware so braces inside string values don't
    confuse the bracket accounting.
    """
    last_complete = None
    in_str = esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "}]":
            last_complete = i + 1
    if last_complete is None:
        return None
    prefix = text[:last_complete]
    stack: list[str] = []
    in_str = esc = False
    for ch in prefix:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch == "}" and stack and stack[-1] == "{":
            stack.pop()
        elif ch == "]" and stack and stack[-1] == "[":
            stack.pop()
    candidate = prefix + "".join("}" if c == "{" else "]" for c in reversed(stack))
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def parse_json_response(text: str) -> dict | list:
    """
    Best-effort JSON extraction. Local models sometimes wrap JSON in prose or
    fenced code blocks; recover the first balanced JSON object/array. As a last
    resort, salvage a response truncated by the output-token limit so its
    completed findings are not lost.
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
    # fall back: scan for a balanced, string-aware JSON span. Handles reasoning
    # models (gpt-oss / CyberPal) that prepend a 'thinking' preamble containing
    # braces, which the first-{/last-} heuristic above mis-spans. Prefer the
    # LARGEST object/array (the real payload, not a stray {} in the preamble).
    candidates = [
        s
        for opener, closer in (("{", "}"), ("[", "]"))
        for s in _balanced_spans(text, opener, closer)
    ]
    for span in sorted(candidates, key=len, reverse=True):
        try:
            return json.loads(span)
        except json.JSONDecodeError:
            continue
    # last resort: the response was cut off mid-JSON — recover what completed.
    salvaged = _salvage_truncated_json(text)
    if salvaged is not None:
        return salvaged
    raise OllamaError("Could not parse JSON from model response")


# Convenience wrappers per agent role -----------------------------------------
def analyst(system: str, prompt: str, *, json_mode: bool = True, model: str | None = None) -> str:
    # `model` lets a tenant route its extractor stage to its own fine-tuned model
    # (Phase 3). None → the global default, unchanged.
    return generate(model or global_config.current_ai()["analyst_model"], system, prompt, json_mode=json_mode)


def reviewer(system: str, prompt: str, *, json_mode: bool = True, model: str | None = None) -> str:
    # `model` lets a tenant pin every pipeline role to its own configured model.
    # None → the role's global default, unchanged.
    return generate(model or _role_model("reviewer"), system, prompt, json_mode=json_mode)


def qa(system: str, prompt: str, *, json_mode: bool = True, model: str | None = None) -> str:
    return generate(model or _role_model("qa"), system, prompt, json_mode=json_mode)
