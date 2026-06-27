"""
Configuration API.

- Per-module config (Structured Threat Hunt): editable guides + categories.
- Global config: AI engine (Ollama models/params) + platform settings.

None of this is tenant-scoped — these are platform/service-wide standards.
"""
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import AnalysisJob
from app.schemas import ConfigOut, ConfigUpdate
from app.services import categories, config_store, db_health, global_config, jobs

router = APIRouter(prefix="/api/config", tags=["config"])

UPLOAD_ROOT = Path("uploads")


# ── Ollama runtime health + recovery ───────────────────────────────────────
@router.get("/ollama-status")
def ollama_status(db: Session = Depends(get_db)):
    """Reachability + models currently loaded in memory (Ollama /api/ps)."""
    import httpx

    base = global_config.get_ai(db)["base_url"]
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(f"{base}/api/ps")
            resp.raise_for_status()
            data = resp.json()
        models = [
            {"name": m.get("name"), "size_vram": m.get("size_vram", 0), "size": m.get("size", 0)}
            for m in data.get("models", [])
        ]
        return {"reachable": True, "base_url": base, "models": models}
    except Exception:  # noqa: BLE001
        return {"reachable": False, "base_url": base, "models": []}


@router.post("/ollama-unload")
def ollama_unload(db: Session = Depends(get_db)):
    """Free memory: unload all loaded models and cancel active analysis jobs.

    (The backend talks to Ollama over HTTP, so it can unload models and stop
    LENS jobs — for a full server restart use `lense ollama restart`.)
    """
    import httpx

    base = global_config.get_ai(db)["base_url"]
    unloaded: list[str] = []
    try:
        with httpx.Client(timeout=15) as client:
            loaded = client.get(f"{base}/api/ps").json().get("models", [])
            for m in loaded:
                name = m.get("name")
                if not name:
                    continue
                try:
                    # keep_alive=0 evicts the model from memory immediately.
                    client.post(
                        f"{base}/api/generate",
                        json={"model": name, "prompt": "", "keep_alive": 0, "stream": False},
                    )
                    unloaded.append(name)
                except Exception:  # noqa: BLE001
                    pass
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Ollama not reachable: {exc}")

    cancelled = (
        db.query(AnalysisJob)
        .filter(AnalysisJob.status.in_(jobs.ACTIVE))
        .update({"status": "cancelled", "error": "stopped via Ollama reset"}, synchronize_session=False)
    )
    db.commit()
    return {"unloaded": unloaded, "cancelled_jobs": cancelled}



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


# ── Available Ollama models (for the model dropdowns) ──────────────────────
@router.get("/ollama-models")
def list_ollama_models(db: Session = Depends(get_db)):
    """Names of models installed in the local Ollama (best-effort)."""
    import httpx

    base = global_config.get_ai(db)["base_url"]
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(f"{base}/api/tags")
            resp.raise_for_status()
            data = resp.json()
        names = sorted(
            m.get("name", "") for m in data.get("models", []) if m.get("name")
        )
        return {"models": names, "reachable": True}
    except Exception:  # noqa: BLE001 — Ollama may be down; UI falls back to text
        return {"models": [], "reachable": False}


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


# ── Database / storage maintenance ─────────────────────────────────────────
@router.get("/db-health")
def db_health_scan(db: Session = Depends(get_db)):
    """Read-only scan for orphaned files, missing dataset files, and stuck jobs."""
    return db_health.scan(db)


@router.post("/db-health/clean")
def db_health_clean(db: Session = Depends(get_db)):
    """Delete orphaned files, clear stuck jobs, prune empty dirs."""
    return db_health.clean(db)


# ── Platform logo ──────────────────────────────────────────────────────────
@router.post("/platform/logo")
async def upload_platform_logo(file: UploadFile = File(...), db: Session = Depends(get_db)):
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Logo exceeds 5 MB")
    dest_dir = UPLOAD_ROOT / "platform"
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", file.filename or "logo")
    dest = dest_dir / f"logo_{safe}"
    dest.write_bytes(data)
    return global_config.set_platform_logo(db, str(dest))


@router.get("/platform/logo")
def get_platform_logo(db: Session = Depends(get_db)):
    path = global_config.get_platform(db).get("logo_path")
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="No platform logo")
    return FileResponse(path)


# ── Sable assistant icon ────────────────────────────────────────────────────
@router.post("/platform/sable-icon")
async def upload_sable_icon(file: UploadFile = File(...), db: Session = Depends(get_db)):
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Icon exceeds 5 MB")
    dest_dir = UPLOAD_ROOT / "platform"
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", file.filename or "icon")
    dest = dest_dir / f"sable_{safe}"
    dest.write_bytes(data)
    return global_config.set_assistant_icon(db, str(dest))


@router.get("/platform/sable-icon")
def get_sable_icon(db: Session = Depends(get_db)):
    path = global_config.get_platform(db).get("assistant_icon_path")
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="No assistant icon")
    return FileResponse(path)
