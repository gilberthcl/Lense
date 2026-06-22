from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Dataset, Finding, Hunt, Tenant
from app.schemas import TenantCreate, TenantOut
from app.services.categories import CATEGORIES

router = APIRouter(prefix="/api/tenants", tags=["tenants"])

# Category → risk weight for the rolled-up client risk score.
_RISK_WEIGHT = {
    "malicious": 25, "suspicious": 12, "vulnerable_configuration": 8,
    "risky": 6, "policy_violation": 4, "unconfirmed": 2,
    "new_hunting_opportunity": 1, "baseline": 1,
}


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


@router.get("/{tenant_id}/overview")
def client_overview(tenant_id: int, db: Session = Depends(get_db)):
    """Aggregated portal data for a client (counts, risk, recent activity)."""
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Client not found")

    hunts_count = db.query(func.count(Hunt.id)).filter_by(tenant_id=tenant_id).scalar() or 0
    datasets_count = db.query(func.count(Dataset.id)).filter_by(tenant_id=tenant_id).scalar() or 0

    real = (Finding.tenant_id == tenant_id, Finding.category != "no_finding")
    by_category = dict(
        db.query(Finding.category, func.count(Finding.id))
        .filter(*real)
        .group_by(Finding.category)
        .all()
    )
    by_status = dict(
        db.query(Finding.status, func.count(Finding.id))
        .filter(*real)
        .group_by(Finding.status)
        .all()
    )
    findings_total = sum(by_category.values())
    risk_raw = sum(_RISK_WEIGHT.get(cat, 1) * n for cat, n in by_category.items())
    risk_score = min(100, risk_raw)
    risk_label = (
        "Critical" if risk_score >= 75 else "High" if risk_score >= 50
        else "Medium" if risk_score >= 25 else "Low" if risk_score > 0 else "None"
    )

    recent_hunts = (
        db.query(Hunt).filter_by(tenant_id=tenant_id).order_by(desc(Hunt.created_at)).limit(5).all()
    )
    recent_findings = (
        db.query(Finding)
        .filter(*real)
        .order_by(desc(Finding.created_at))
        .limit(6)
        .all()
    )

    # Order category counts by canonical severity for display.
    ordered_categories = [
        {"key": c["key"], "label": c["label_en"], "count": by_category[c["key"]]}
        for c in CATEGORIES
        if by_category.get(c["key"])
    ]

    return {
        "client": {"id": tenant.id, "name": tenant.name, "slug": tenant.slug,
                   "edr": None, "siem": None},
        "counts": {
            "hunts": hunts_count,
            "datasets": datasets_count,
            "findings": findings_total,
            "validated": by_status.get("validated", 0),
        },
        "risk": {"score": risk_score, "label": risk_label},
        "by_category": ordered_categories,
        "by_status": by_status,
        "recent_hunts": [
            {"id": h.id, "name": h.name, "status": h.status,
             "report_language": h.report_language, "edr": h.edr, "siem": h.siem,
             "created_at": h.created_at.isoformat() if h.created_at else None}
            for h in recent_hunts
        ],
        "recent_findings": [
            {"id": f.id, "finding_ref": f.finding_ref, "title": f.title,
             "category": f.category, "severity": f.severity, "status": f.status,
             "hunt_id": f.hunt_id,
             "created_at": f.created_at.isoformat() if f.created_at else None}
            for f in recent_findings
        ],
    }
