"""
Per-tenant fine-tuned model registry API — Phase 3 (tenant-scoped).

List candidates, register a freshly trained one, evaluate it against the golden
baseline, and promote/reject. Promotion runs the eval gate (tenant_models.promote
raises if the candidate regressed). Routing to an active model is handled in the
analysis pipeline; this API only manages the registry.
"""
from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_tenant
from app.core.db import SessionLocal, get_db
from app.models import Tenant, TenantModel
from app.services import eval_runner, tenant_models

router = APIRouter(prefix="/api/tenants/{tenant_id}/models", tags=["models"])


def _serialize(m: TenantModel) -> dict:
    return {
        "id": m.id,
        "tenant_id": m.tenant_id,
        "base_model": m.base_model,
        "ollama_model_name": m.ollama_model_name,
        "version": m.version,
        "status": m.status,
        "train_metrics": m.train_metrics,
        "eval_metrics": m.eval_metrics,
        "baseline_metrics": m.baseline_metrics,
        "comparison": m.comparison,
        "notes": m.notes,
        "created_at": m.created_at,
        "trained_at": m.trained_at,
        "activated_at": m.activated_at,
    }


def _resolve(db: Session, tenant_id: int, model_id: int) -> TenantModel:
    m = tenant_models.get_model(db, tenant_id, model_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return m


@router.get("")
def list_tenant_models(
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """All registered candidate models for this tenant (newest version first)."""
    return {
        "active_model": tenant_models.resolve_analyst_model(db, tenant.id),
        "models": [_serialize(m) for m in tenant_models.list_models(db, tenant.id)],
    }


@router.post("/register", status_code=201)
def register_model(
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
    base_model: str = Body(..., embed=True),
    ollama_model_name: str = Body(..., embed=True),
    notes: str | None = Body(default=None, embed=True),
):
    """Record a freshly trained candidate (the trainer CLI will call this).
    Starts as `validating` — never live until it passes eval and is promoted."""
    m = tenant_models.register(
        db, tenant.id, base_model=base_model,
        ollama_model_name=ollama_model_name, notes=notes,
    )
    return _serialize(m)


@router.post("/{model_id}/evaluate", status_code=202)
def evaluate_model(
    model_id: int,
    background: BackgroundTasks,
    include_holdout: bool = False,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Run the golden eval against this candidate model and record its metrics +
    regression verdict vs. the current baseline. Background (hits the model)."""
    model = _resolve(db, tenant.id, model_id)
    baseline = eval_runner.load_baseline(tenant.id) or {}
    baseline_metrics = baseline.get("metrics")
    if not baseline_metrics:
        raise HTTPException(
            status_code=409,
            detail="No golden baseline yet — run a baseline eval (Model quality baseline) first.",
        )

    tid, mid, mname = tenant.id, model.id, model.ollama_model_name

    def _task(tenant_id: int, model_pk: int, model_name: str, inc: bool) -> None:
        task_db = SessionLocal()
        try:
            report = eval_runner.execute_eval(
                task_db, tenant_id, include_holdout=inc, analyst_model=model_name
            )
            m = task_db.get(TenantModel, model_pk)
            if m is not None:
                tenant_models.record_eval(
                    task_db, m, candidate_metrics=report["metrics"],
                    baseline_metrics=baseline_metrics,
                )
        finally:
            task_db.close()

    background.add_task(_task, tid, mid, mname, include_holdout)
    return {"status": "started", "model_id": mid}


@router.post("/{model_id}/promote")
def promote_model(
    model_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Activate a candidate (demotes any current active). Enforces the eval gate."""
    model = _resolve(db, tenant.id, model_id)
    try:
        tenant_models.promote(db, model)
    except tenant_models.PromotionBlocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _serialize(model)


@router.post("/{model_id}/reject")
def reject_model(
    model_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    model = _resolve(db, tenant.id, model_id)
    return _serialize(tenant_models.set_status(db, model, "rejected"))


@router.post("/{model_id}/retire")
def retire_model(
    model_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    model = _resolve(db, tenant.id, model_id)
    return _serialize(tenant_models.set_status(db, model, "retired"))
