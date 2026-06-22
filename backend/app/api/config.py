"""
Configuration API.

- Per-module config (Structured Threat Hunt): editable guides + categories.
- Global config: AI engine (Ollama models/params) + platform settings.

None of this is tenant-scoped — these are platform/service-wide standards.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas import ConfigOut, ConfigUpdate
from app.services import categories, config_store, global_config

router = APIRouter(prefix="/api/config", tags=["config"])


# ── Structured Threat Hunt module config ───────────────────────────────────
@router.get("/structured-threat-hunt", response_model=list[ConfigOut])
def list_sth_config(db: Session = Depends(get_db)):
    return config_store.list_configs(db)


@router.get("/structured-threat-hunt/categories")
def list_categories():
    """Canonical finding categories (the machine-usable contract)."""
    return {"categories": categories.CATEGORIES}


@router.put("/structured-threat-hunt/{key}", response_model=ConfigOut)
def update_sth_config(key: str, payload: ConfigUpdate, db: Session = Depends(get_db)):
    if key not in config_store.CONFIG_KEYS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown config key. Allowed: {sorted(config_store.CONFIG_KEYS)}",
        )
    return config_store.upsert(db, key, payload.content)


# ── Global config (platform + AI engine) ───────────────────────────────────
@router.get("/global")
def get_global(db: Session = Depends(get_db)):
    return {
        "ai_engine": global_config.get_ai(db),
        "ai_defaults": global_config.ai_defaults(),
        "platform": global_config.get_platform(db),
    }


@router.put("/global/ai-engine")
def update_ai_engine(payload: dict, db: Session = Depends(get_db)):
    try:
        return global_config.update_ai(db, payload)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.put("/global/platform")
def update_platform(payload: dict, db: Session = Depends(get_db)):
    return global_config.update_platform(db, payload)
