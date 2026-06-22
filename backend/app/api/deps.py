"""Shared API dependencies — primarily tenant scoping."""
from fastapi import Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Tenant


def get_tenant(
    tenant_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
) -> Tenant:
    """Resolve and verify a tenant. Every tenant-scoped route depends on this."""
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant
