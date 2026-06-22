from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Tenant
from app.schemas import TenantCreate, TenantOut

router = APIRouter(prefix="/api/tenants", tags=["tenants"])


@router.get("", response_model=list[TenantOut])
def list_tenants(db: Session = Depends(get_db)):
    return db.query(Tenant).order_by(Tenant.name).all()


@router.post("", response_model=TenantOut, status_code=201)
def create_tenant(payload: TenantCreate, db: Session = Depends(get_db)):
    if db.query(Tenant).filter_by(slug=payload.slug).first():
        raise HTTPException(status_code=409, detail="Tenant slug already exists")
    tenant = Tenant(**payload.model_dump())
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


@router.get("/{tenant_id}", response_model=TenantOut)
def get_tenant_detail(tenant_id: int, db: Session = Depends(get_db)):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant
