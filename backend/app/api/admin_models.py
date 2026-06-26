"""
In-app model manager (GLOBAL, operator-level).

Install (from the vetted catalog or a custom GGUF ref), remove, and inspect the
local Ollama models — no CLI. Safe-handling controls: a curated catalog, the
compliance allowlist, GGUF-only pulls (no executable model code), and delete
guards (never remove embeddings or a model a client still uses).
"""
from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Tenant
from app.services import global_config, model_catalog, model_compliance
from app.services import ollama_client as ollama

router = APIRouter(prefix="/api/models", tags=["model-manager"])

# Live pull progress, keyed by model ref. Polled by the UI (pulls are long).
_PULL_STATUS: dict[str, dict] = {}


def _assignments(db: Session) -> dict[str, str]:
    """name → client using it as their analyst model (so we don't delete it)."""
    return {
        t.analyst_model: t.name
        for t in db.query(Tenant).filter(Tenant.analyst_model.isnot(None)).all()
    }


@router.get("/catalog")
def catalog():
    """The curated, vetted models the operator can one-click install."""
    return {"models": model_catalog.CATALOG}


@router.get("/installed")
def installed(db: Session = Depends(get_db)):
    """Installed Ollama models with size, compliance, catalog match, assignment."""
    ai = global_config.current_ai()
    defaults = {ai.get("analyst_model"), ai.get("embed_model"), ai.get("reviewer_model")}
    assigned = _assignments(db)
    out = []
    for m in ollama.list_models():
        name = m["name"]
        allowed, reason = model_compliance.classify(name)
        cat = model_catalog.by_ref(name)
        out.append({
            "name": name, "size": m["size"],
            "allowed": allowed, "reason": reason,
            "catalog": cat["name"] if cat else None,
            "kind": cat["kind"] if cat else None,
            "protected": model_catalog.is_protected(name),
            "assigned_to": assigned.get(name),
            "is_default": name in defaults,
        })
    return {"models": out}


@router.get("/pull-status")
def pull_status():
    """Progress of in-flight / recent pulls (the UI polls this)."""
    return {"pulls": _PULL_STATUS}


@router.post("/pull", status_code=202)
def pull(
    background: BackgroundTasks,
    ref: str = Body(..., embed=True),
):
    """Install a model by catalog ref or custom GGUF ref. Compliance-gated; the
    pull runs in the background with progress in /pull-status."""
    ref = (ref or "").strip()
    if not ref:
        raise HTTPException(status_code=422, detail="Provide a model ref to install.")
    allowed, reason = model_compliance.classify(ref)
    if not allowed:
        raise HTTPException(status_code=422, detail=f"Model not allowed — {reason}.")

    _PULL_STATUS[ref] = {"status": "queued", "pct": 0, "done": False, "error": None}

    def _task(model_ref: str):
        def on_progress(status: str, pct):
            _PULL_STATUS[model_ref] = {
                "status": status, "pct": pct if pct is not None else _PULL_STATUS[model_ref].get("pct", 0),
                "done": False, "error": None,
            }
        try:
            ollama.pull_model(model_ref, on_progress=on_progress)
            _PULL_STATUS[model_ref] = {"status": "complete", "pct": 100, "done": True, "error": None}
        except ollama.OllamaError as exc:
            _PULL_STATUS[model_ref] = {"status": "error", "pct": 0, "done": True, "error": str(exc)}

    background.add_task(_task, ref)
    return {"status": "started", "ref": ref}


@router.delete("/{name:path}")
def remove(name: str, db: Session = Depends(get_db)):
    """Remove an installed model. Guards: never the embeddings/required models,
    never a model a client still uses, never the global default."""
    if model_catalog.is_protected(name):
        raise HTTPException(status_code=409, detail="That model is required (embeddings) and can't be removed.")
    ai = global_config.current_ai()
    if name in {ai.get("analyst_model"), ai.get("embed_model")}:
        raise HTTPException(status_code=409, detail="That's the global default model — change the default first.")
    owner = _assignments(db).get(name)
    if owner:
        raise HTTPException(status_code=409, detail=f"In use by client '{owner}' — reassign that client first.")
    ollama.delete_model(name)
    _PULL_STATUS.pop(name, None)
    return {"ok": True, "removed": name}
