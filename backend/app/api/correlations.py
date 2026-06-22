"""Cross-dataset entity correlation (computed on demand, tenant-scoped)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_tenant
from app.core.db import get_db
from app.models import Dataset, Finding, Hunt, Tenant
from app.services import correlation

router = APIRouter(
    prefix="/api/tenants/{tenant_id}/hunts/{hunt_id}/correlations", tags=["correlations"]
)


def _finding_to_dict(f: Finding) -> dict:
    return {
        "id": f.id,
        "finding_ref": f.finding_ref,
        "title": f.title,
        "category": f.category,
        "dataset_id": f.dataset_id,
        "affected_assets": f.affected_assets,
        "affected_users": f.affected_users,
        "evidence": f.evidence,
    }


@router.get("")
def get_correlations(
    hunt_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    hunt = db.get(Hunt, hunt_id)
    if not hunt or hunt.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Hunt not found")

    findings = (
        db.query(Finding).filter_by(tenant_id=tenant.id, hunt_id=hunt_id).all()
    )
    datasets = db.query(Dataset).filter_by(tenant_id=tenant.id, hunt_id=hunt_id).all()
    dataset_names = {d.id: d.filename for d in datasets}

    result = correlation.compute_correlations(
        (_finding_to_dict(f) for f in findings), dataset_names
    )
    result["hunt_id"] = hunt_id
    return result
