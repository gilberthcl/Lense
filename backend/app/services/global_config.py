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
    }


def platform_defaults() -> dict:
    return {
        "platform_name": "LENS",
        "default_report_language": "English",
        "logo_path": None,
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
    return _read(db, AI_KEY, ai_defaults())


def get_platform(db: Session) -> dict:
    return _read(db, PLATFORM_KEY, platform_defaults())


def _validate_ai(patch: dict) -> dict:
    allowed = ai_defaults()
    out: dict = {}
    for k, v in patch.items():
        if k not in allowed:
            continue
        if k.endswith("_model") and isinstance(v, str) and "-cloud" in v:
            raise ValueError(
                f"Cloud models are not allowed (local-only compliance): {v}"
            )
        out[k] = v
    if "temperature" in out:
        out["temperature"] = max(0.0, min(1.0, float(out["temperature"])))
    if "timeout" in out:
        out["timeout"] = max(30, int(out["timeout"]))
    return out


def update_ai(db: Session, patch: dict) -> dict:
    data = get_ai(db)
    data.update(_validate_ai(patch))
    _write(db, AI_KEY, "AI Engine", data)
    refresh(db)
    return data


def update_platform(db: Session, patch: dict) -> dict:
    data = get_platform(db)
    for k in ("platform_name", "default_report_language"):
        if k in patch and patch[k] is not None:
            data[k] = patch[k]
    _write(db, PLATFORM_KEY, "Platform", data)
    return data


def set_platform_logo(db: Session, path: str) -> dict:
    data = get_platform(db)
    data["logo_path"] = path
    _write(db, PLATFORM_KEY, "Platform", data)
    return data


def refresh(db: Session) -> None:
    """Reload the in-memory AI config cache from the DB."""
    global _ai_cache
    _ai_cache = get_ai(db)


def current_ai() -> dict:
    """Effective AI config for runtime use (falls back to env defaults)."""
    return _ai_cache if _ai_cache is not None else ai_defaults()
