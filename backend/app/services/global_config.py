"""
Global platform configuration — AI engine + platform settings.

Editable, DB-backed settings that apply across modules (not tenant-scoped).
The AI-engine block (Ollama base URL, per-role models, temperature, timeout) is
read by the ollama client at call time via an in-memory cache that is refreshed
on startup and whenever the settings are saved — so model choices can be changed
from the UI without restarting the backend.

Compliance: model names containing a `-cloud` suffix are rejected — they break
the local-only / tenant-isolation guarantee (see CLAUDE.md).
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ModuleConfig

MODULE = "global"
AI_KEY = "ai_engine"
PLATFORM_KEY = "platform"

_ai_cache: dict | None = None  # effective AI config (None until first load)


def ai_defaults() -> dict:
    return {
        "base_url": settings.ollama_base_url,
        "analyst_model": settings.ollama_analyst_model,
        "reviewer_model": settings.ollama_reviewer_model,
        "qa_model": settings.ollama_qa_model,
        "embed_model": settings.ollama_embed_model,
        "temperature": 0.2,
        "timeout": settings.ollama_timeout,
        # On 32 GB, two large models can't co-reside, so Ollama reloads a 17 GB
        # model every call. single_model_pipeline runs reviewer+QA on the analyst
        # model (one resident model, no swapping) — far faster.
        "single_model_pipeline": True,
        # Output cap. 2048 was truncating multi-finding JSON mid-structure on
        # all but the smallest datasets (→ parse failures → zero findings); a
        # single dataset's findings can run several thousand tokens.
        "num_predict": 4096,
        # Context window. Must hold the trimmed extractor prompt (~5-6k tokens)
        # PLUS the generated findings (num_predict). 8192 left no room for the
        # output, so the JSON got cut off; 12288 fits prompt + findings with
        # margin. Larger contexts cost KV-cache RAM on the 27B model, so this is
        # a deliberate middle ground, not a max.
        "num_ctx": 12288,
        "keep_alive": "30m",    # keep the model warm between datasets
        # Transient transport failures (connection reset/refused while Ollama is
        # under memory pressure or loading the model) are retried this many times
        # with backoff before the job is marked failed. Timeouts are never
        # retried — see ollama_client. This is the main analysis-stability knob.
        "request_retries": 2,
        # Each stage is a separate generation. On a slow box, turning Reviewer/QA
        # off runs a single analyst pass (≈3× faster) at some FP-reduction cost.
        "enable_reviewer": True,
        "enable_qa": True,
        # Anonymise training examples on export (W5): replace concrete entities
        # with placeholders so the model learns patterns, not specific hostnames.
        # Off by default — per-client isolation already covers safety.
        "anonymize_training": False,
    }


def platform_defaults() -> dict:
    return {
        "platform_name": "LENS",
        "default_report_language": "English",
        "logo_path": None,
        # Sable assistant identity (configurable). Model lives in the AI config
        # as `assistant_model`; name + icon are branding and live here.
        "assistant_name": "Sable",
        "assistant_icon_path": None,
    }


def _read(db: Session, key: str, defaults: dict) -> dict:
    row = db.query(ModuleConfig).filter_by(module=MODULE, key=key).first()
    data = dict(defaults)
    if row and row.content:
        try:
            saved = json.loads(row.content)
            data.update({k: v for k, v in saved.items() if k in defaults})
        except json.JSONDecodeError:
            pass
    return data


def _write(db: Session, key: str, title: str, data: dict) -> None:
    row = db.query(ModuleConfig).filter_by(module=MODULE, key=key).first()
    content = json.dumps(data)
    if row is None:
        db.add(ModuleConfig(module=MODULE, key=key, title=title, content=content))
    else:
        row.content = content
    db.commit()


def get_ai(db: Session) -> dict:
    data = _read(db, AI_KEY, ai_defaults())
    # Floor num_ctx only if a saved config is implausibly small (would truncate
    # the trimmed prompt). We do NOT force it up to a large value anymore — a
    # 16k context on a 27B model is exactly what was crashing 32 GB machines, so
    # the operator is free to keep num_ctx at the leaner default.
    # Floor the output/context limits so a stale saved config can't reintroduce
    # the truncation that produced zero findings. These are minimums, not caps.
    if int(data.get("num_predict", 0)) < 4096:
        data["num_predict"] = ai_defaults()["num_predict"]
    if int(data.get("num_ctx", 0)) < 12288:
        data["num_ctx"] = ai_defaults()["num_ctx"]
    return data


def get_platform(db: Session) -> dict:
    return _read(db, PLATFORM_KEY, platform_defaults())


def _validate_ai(patch: dict) -> dict:
    allowed = ai_defaults()
    gen_roles = ("analyst_model", "reviewer_model", "qa_model")
    out: dict = {}
    for k, v in patch.items():
        if k not in allowed:
            continue
        if k.endswith("_model") and isinstance(v, str) and "-cloud" in v:
            raise ValueError(
                f"Cloud models are not allowed (local-only compliance): {v}"
            )
        # Embedding models can't generate text → /api/generate returns 400.
        if k in gen_roles and isinstance(v, str) and "embed" in v.lower():
            raise ValueError(
                f"'{v}' looks like an embedding model — it can't be used for the "
                f"{k.replace('_model', '')} role (it only produces vectors)."
            )
        out[k] = v
    if "temperature" in out:
        out["temperature"] = max(0.0, min(1.0, float(out["temperature"])))
    if "timeout" in out:
        out["timeout"] = max(30, int(out["timeout"]))
    if "num_predict" in out:
        out["num_predict"] = max(256, min(int(out["num_predict"]), 16384))
    if "num_ctx" in out:
        out["num_ctx"] = max(2048, min(int(out["num_ctx"]), 32768))
    if "single_model_pipeline" in out:
        out["single_model_pipeline"] = bool(out["single_model_pipeline"])
    for k in ("enable_reviewer", "enable_qa", "anonymize_training"):
        if k in out:
            out[k] = bool(out[k])
    return out


def update_ai(db: Session, patch: dict) -> dict:
    data = get_ai(db)
    data.update(_validate_ai(patch))
    _write(db, AI_KEY, "AI Engine", data)
    refresh(db)
    return data


def update_platform(db: Session, patch: dict) -> dict:
    data = get_platform(db)
    for k in ("platform_name", "default_report_language", "assistant_name"):
        if k in patch and patch[k] is not None:
            data[k] = patch[k]
    _write(db, PLATFORM_KEY, "Platform", data)
    return data


def set_platform_logo(db: Session, path: str) -> dict:
    data = get_platform(db)
    data["logo_path"] = path
    _write(db, PLATFORM_KEY, "Platform", data)
    return data


def set_assistant_icon(db: Session, path: str) -> dict:
    data = get_platform(db)
    data["assistant_icon_path"] = path
    _write(db, PLATFORM_KEY, "Platform", data)
    return data


def refresh(db: Session) -> None:
    """Reload the in-memory AI config cache from the DB."""
    global _ai_cache
    _ai_cache = get_ai(db)


def current_ai() -> dict:
    """Effective AI config for runtime use (falls back to env defaults)."""
    return _ai_cache if _ai_cache is not None else ai_defaults()
