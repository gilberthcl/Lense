from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_tenant
from app.core.db import get_db
from app.models import Hunt, KnowledgeDocument, Tenant
from app.schemas import HuntCreate, HuntOut

router = APIRouter(prefix="/api/tenants/{tenant_id}/hunts", tags=["hunts"])


@router.get("", response_model=list[HuntOut])
def list_hunts(tenant: Tenant = Depends(get_tenant), db: Session = Depends(get_db)):
    return (
        db.query(Hunt)
        .filter_by(tenant_id=tenant.id)
        .order_by(Hunt.created_at.desc())
        .all()
    )


@router.post("", response_model=HuntOut, status_code=201)
def create_hunt(
    payload: HuntCreate,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    methodology = payload.methodology_text
    # Default to the tenant's methodology doc if none supplied for this hunt.
    if not methodology:
        doc = (
            db.query(KnowledgeDocument)
            .filter_by(tenant_id=tenant.id, doc_type="methodology")
            .order_by(KnowledgeDocument.created_at.desc())
            .first()
        )
        methodology = doc.content if doc else None
    hunt = Hunt(
        tenant_id=tenant.id,
        name=payload.name,
        objective=payload.objective,
        methodology_text=methodology,
    )
    db.add(hunt)
    db.commit()
    db.refresh(hunt)
    return hunt


@router.get("/{hunt_id}", response_model=HuntOut)
def get_hunt(
    hunt_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    hunt = db.get(Hunt, hunt_id)
    if not hunt or hunt.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Hunt not found")
    return hunt
