"""
Training-data export — Phase 1 of per-tenant LoRA fine-tuning (tenant-scoped).

Lets an operator inspect how much trainable signal a tenant has accumulated and
export it as JSONL. This does NOT train a model — it only produces the dataset a
future offline MLX trainer would consume. See docs/per-tenant-lora-finetuning.md.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_tenant
from app.core.db import get_db
from app.models import Tenant
from app.services import training_export

router = APIRouter(prefix="/api/tenants/{tenant_id}/training", tags=["training"])


@router.get("/stats")
def get_training_stats(
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """How many validated/rejected findings this tenant has, and whether the
    eligible-positive count clears the overfit floor for a LoRA tune."""
    return training_export.training_stats(db, tenant.id)


@router.post("/export")
def export_training_set(
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Write the tenant's SFT + negatives JSONL to disk and return stats + paths.
    Files are git-ignored (client data)."""
    return training_export.export_tenant(db, tenant.id)
