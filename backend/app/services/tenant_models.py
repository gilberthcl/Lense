"""
Per-tenant fine-tuned model registry — Phase 3 (decision-independent scaffolding).

Tracks LoRA-tuned candidate models per tenant and gates which one (if any) the
analysis pipeline routes to. This module is INERT until a trainer registers a
model and an operator promotes it: with no `active` row, `resolve_analyst_model`
returns None and the pipeline uses the global default exactly as before.

Isolation (Critical Rule #1): every query filters by tenant_id; a tenant's
analysis can only ever route to its OWN active model.

Promotion gate: a candidate can only become `active` if its golden-eval did not
regress against the baseline (eval_metrics.compare) — fine-tuning must never
silently degrade recall, precision, or evidence discipline.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import TenantModel
from app.services import eval_metrics

ACTIVE_STATUS = "active"
_PROMOTABLE_FROM = ("validating", "draft", "retired")


def list_models(db: Session, tenant_id: int) -> list[TenantModel]:
    return (
        db.query(TenantModel)
        .filter_by(tenant_id=tenant_id)
        .order_by(TenantModel.version.desc())
        .all()
    )


def get_model(db: Session, tenant_id: int, model_id: int) -> TenantModel | None:
    m = db.get(TenantModel, model_id)
    if m is None or m.tenant_id != tenant_id:
        return None
    return m


def active_model(db: Session, tenant_id: int) -> TenantModel | None:
    return (
        db.query(TenantModel)
        .filter_by(tenant_id=tenant_id, status=ACTIVE_STATUS)
        .order_by(TenantModel.version.desc())
        .first()
    )


def resolve_analyst_model(db: Session, tenant_id: int) -> str | None:
    """The Ollama model name this tenant's analyst stage should use, or None to
    fall back to the global default. This is the single routing decision."""
    m = active_model(db, tenant_id)
    return m.ollama_model_name if m else None


def _next_version(db: Session, tenant_id: int) -> int:
    top = (
        db.query(TenantModel.version)
        .filter_by(tenant_id=tenant_id)
        .order_by(TenantModel.version.desc())
        .first()
    )
    return (top[0] + 1) if top else 1


def register(
    db: Session, tenant_id: int, *, base_model: str, ollama_model_name: str,
    train_metrics: dict | None = None, notes: str | None = None,
) -> TenantModel:
    """Record a freshly trained candidate. Starts as `validating` — never live
    until it passes the eval gate and an operator promotes it."""
    m = TenantModel(
        tenant_id=tenant_id,
        base_model=base_model,
        ollama_model_name=ollama_model_name,
        version=_next_version(db, tenant_id),
        status="validating",
        train_metrics=train_metrics,
        notes=notes,
        trained_at=datetime.now(timezone.utc),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def record_eval(
    db: Session, model: TenantModel, *, candidate_metrics: dict,
    baseline_metrics: dict | None, tolerance: float = 0.02,
) -> TenantModel:
    """Attach a candidate's golden-eval result and compute the regression verdict
    against the baseline. Does NOT activate — that's a separate operator step."""
    model.eval_metrics = candidate_metrics
    model.baseline_metrics = baseline_metrics
    if baseline_metrics:
        model.comparison = eval_metrics.compare(
            baseline_metrics, candidate_metrics, tolerance=tolerance
        )
    else:
        # No baseline to compare against — cannot clear the gate automatically.
        model.comparison = {"deltas": {}, "regressed": None, "tolerance": tolerance}
    db.commit()
    db.refresh(model)
    return model


class PromotionBlocked(RuntimeError):
    pass


def promote(db: Session, model: TenantModel) -> TenantModel:
    """Make a candidate the tenant's active model, demoting any current active to
    retired. Enforces the eval gate: refuse if the model never passed eval or its
    comparison shows a regression."""
    comp = model.comparison or {}
    if not model.eval_metrics or comp.get("regressed") is None:
        raise PromotionBlocked(
            "Model has no completed golden-eval vs. a baseline — run an evaluation first."
        )
    if comp.get("regressed"):
        raise PromotionBlocked(
            "Model regressed against the baseline on golden-eval — not eligible to activate."
        )
    if model.status not in _PROMOTABLE_FROM and model.status != ACTIVE_STATUS:
        raise PromotionBlocked(f"Cannot promote a model in status '{model.status}'.")

    # Demote the current active (one active per tenant).
    current = active_model(db, model.tenant_id)
    if current and current.id != model.id:
        current.status = "retired"
    model.status = ACTIVE_STATUS
    model.activated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(model)
    return model


def set_status(db: Session, model: TenantModel, status: str) -> TenantModel:
    """Operator override for reject/retire/draft transitions (not activation —
    use promote() so the gate is enforced)."""
    if status == ACTIVE_STATUS:
        raise PromotionBlocked("Use promote() to activate a model (the eval gate runs there).")
    model.status = status
    db.commit()
    db.refresh(model)
    return model
