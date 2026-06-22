"""
Global module configuration (Structured Threat Hunt).

Editable guides/standards — Investigation Protocol, Finding Format, Finding
Categorization — that drive the analysis engine. NOT tenant-scoped: these are
the threat-hunt service's own standards, shared across every client.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas import ConfigOut, ConfigUpdate
from app.services import categories, config_store

router = APIRouter(prefix="/api/config/structured-threat-hunt", tags=["config"])


@router.get("", response_model=list[ConfigOut])
def list_config(db: Session = Depends(get_db)):
    return config_store.list_configs(db)


@router.get("/categories")
def list_categories():
    """Canonical finding categories (the machine-usable contract)."""
    return {"categories": categories.CATEGORIES}


@router.put("/{key}", response_model=ConfigOut)
def update_config(key: str, payload: ConfigUpdate, db: Session = Depends(get_db)):
    if key not in config_store.CONFIG_KEYS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown config key. Allowed: {sorted(config_store.CONFIG_KEYS)}",
        )
    return config_store.upsert(db, key, payload.content)
