import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import (
    ClientApprovedSoftware, ClientCalendarEvent, ClientContact, Dataset,
    Finding, Hunt, Tenant,
)
from app.schemas import (
    ApprovedSoftwareBulk, ApprovedSoftwareCreate, ApprovedSoftwareOut,
    CalendarCreate, CalendarOut, ContactCreate, ContactOut, TenantCreate,
    TenantOut, TenantUpdate,
)
from app.services.categories import CATEGORIES

router = APIRouter(prefix="/api/tenants", tags=["tenants"])

UPLOAD_ROOT = Path("uploads")

# Category → risk weight for the rolled-up client risk score.
_RISK_WEIGHT = {
    "malicious": 25, "suspicious": 12, "vulnerable_configuration": 8,
    "risky": 6, "policy_violation": 4, "unconfirmed": 2,
    "new_hunting_opportunity": 1, "baseline": 1,
}


def _resolve(db: Session, tenant_id: int) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Client not found")
    return tenant


# ── Core CRUD ──────────────────────────────────────────────────────────────
@router.get("", response_model=list[TenantOut])
def list_tenants(db: Session = Depends(get_db)):
    return db.query(Tenant).order_by(Tenant.name).all()


@router.post("", response_model=TenantOut, status_code=201)
def create_tenant(payload: TenantCreate, db: Session = Depends(get_db)):
    if db.query(Tenant).filter_by(slug=payload.slug).first():
        raise HTTPException(status_code=409, detail="Client slug already exists")
    # exclude_none so omitted fields keep their model defaults (sla_hours, etc.)
    tenant = Tenant(**payload.model_dump(exclude_none=True))
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


@router.get("/{tenant_id}", response_model=TenantOut)
def get_tenant_detail(tenant_id: int, db: Session = Depends(get_db)):
    return _resolve(db, tenant_id)


@router.put("/{tenant_id}", response_model=TenantOut)
def update_tenant(tenant_id: int, payload: TenantUpdate, db: Session = Depends(get_db)):
    tenant = _resolve(db, tenant_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tenant, field, value)
    db.commit()
    db.refresh(tenant)
    return tenant


# ── Logo / contract upload + serve ─────────────────────────────────────────
def _store_asset(tenant_id: int, prefix: str, file: UploadFile, data: bytes) -> str:
    dest_dir = UPLOAD_ROOT / f"tenant_{tenant_id}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", file.filename or prefix)
    dest = dest_dir / f"{prefix}_{safe}"
    dest.write_bytes(data)
    return str(dest)


@router.post("/{tenant_id}/logo", response_model=TenantOut)
async def upload_logo(tenant_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    tenant = _resolve(db, tenant_id)
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Logo exceeds 5 MB")
    tenant.logo_path = _store_asset(tenant_id, "logo", file, data)
    db.commit()
    db.refresh(tenant)
    return tenant


@router.get("/{tenant_id}/logo")
def get_logo(tenant_id: int, db: Session = Depends(get_db)):
    tenant = _resolve(db, tenant_id)
    if not tenant.logo_path or not Path(tenant.logo_path).exists():
        raise HTTPException(status_code=404, detail="No logo")
    return FileResponse(tenant.logo_path)


@router.post("/{tenant_id}/contract", response_model=TenantOut)
async def upload_contract(tenant_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    tenant = _resolve(db, tenant_id)
    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Contract exceeds 25 MB")
    tenant.contract_path = _store_asset(tenant_id, "contract", file, data)
    db.commit()
    db.refresh(tenant)
    return tenant


@router.get("/{tenant_id}/contract")
def get_contract(tenant_id: int, db: Session = Depends(get_db)):
    tenant = _resolve(db, tenant_id)
    if not tenant.contract_path or not Path(tenant.contract_path).exists():
        raise HTTPException(status_code=404, detail="No contract")
    return FileResponse(tenant.contract_path, filename=Path(tenant.contract_path).name)


# ── Contacts ───────────────────────────────────────────────────────────────
@router.get("/{tenant_id}/contacts", response_model=list[ContactOut])
def list_contacts(tenant_id: int, db: Session = Depends(get_db)):
    _resolve(db, tenant_id)
    return (
        db.query(ClientContact)
        .filter_by(tenant_id=tenant_id)
        .order_by(desc(ClientContact.is_primary), ClientContact.name)
        .all()
    )


@router.post("/{tenant_id}/contacts", response_model=ContactOut, status_code=201)
def create_contact(tenant_id: int, payload: ContactCreate, db: Session = Depends(get_db)):
    _resolve(db, tenant_id)
    contact = ClientContact(tenant_id=tenant_id, **payload.model_dump())
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


@router.delete("/{tenant_id}/contacts/{contact_id}", status_code=204)
def delete_contact(tenant_id: int, contact_id: int, db: Session = Depends(get_db)):
    contact = db.get(ClientContact, contact_id)
    if not contact or contact.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Contact not found")
    db.delete(contact)
    db.commit()


# ── Calendar ───────────────────────────────────────────────────────────────
@router.get("/{tenant_id}/calendar", response_model=list[CalendarOut])
def list_calendar(tenant_id: int, db: Session = Depends(get_db)):
    _resolve(db, tenant_id)
    return (
        db.query(ClientCalendarEvent)
        .filter_by(tenant_id=tenant_id)
        .order_by(ClientCalendarEvent.event_date)
        .all()
    )


@router.post("/{tenant_id}/calendar", response_model=CalendarOut, status_code=201)
def create_event(tenant_id: int, payload: CalendarCreate, db: Session = Depends(get_db)):
    _resolve(db, tenant_id)
    event = ClientCalendarEvent(tenant_id=tenant_id, **payload.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.delete("/{tenant_id}/calendar/{event_id}", status_code=204)
def delete_event(tenant_id: int, event_id: int, db: Session = Depends(get_db)):
    event = db.get(ClientCalendarEvent, event_id)
    if not event or event.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Event not found")
    db.delete(event)
    db.commit()


# ── Approved software (environment baseline) ───────────────────────────────
@router.get("/{tenant_id}/approved-software", response_model=list[ApprovedSoftwareOut])
def list_approved_software(tenant_id: int, db: Session = Depends(get_db)):
    _resolve(db, tenant_id)
    return (
        db.query(ClientApprovedSoftware)
        .filter_by(tenant_id=tenant_id)
        .order_by(desc(ClientApprovedSoftware.is_approved), ClientApprovedSoftware.name)
        .all()
    )


@router.post("/{tenant_id}/approved-software", response_model=ApprovedSoftwareOut, status_code=201)
def create_approved_software(tenant_id: int, payload: ApprovedSoftwareCreate, db: Session = Depends(get_db)):
    _resolve(db, tenant_id)
    sw = ClientApprovedSoftware(tenant_id=tenant_id, **payload.model_dump())
    db.add(sw)
    db.commit()
    db.refresh(sw)
    return sw


@router.post("/{tenant_id}/approved-software/bulk", response_model=list[ApprovedSoftwareOut], status_code=201)
def bulk_approved_software(tenant_id: int, payload: ApprovedSoftwareBulk, db: Session = Depends(get_db)):
    _resolve(db, tenant_id)
    created = []
    for raw in payload.names:
        name = raw.strip()
        if not name:
            continue
        sw = ClientApprovedSoftware(tenant_id=tenant_id, name=name, is_approved=payload.is_approved)
        db.add(sw)
        created.append(sw)
    db.commit()
    for sw in created:
        db.refresh(sw)
    return created


@router.delete("/{tenant_id}/approved-software/{sw_id}", status_code=204)
def delete_approved_software(tenant_id: int, sw_id: int, db: Session = Depends(get_db)):
    sw = db.get(ClientApprovedSoftware, sw_id)
    if not sw or sw.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Entry not found")
    db.delete(sw)
    db.commit()


# ── Portal overview ────────────────────────────────────────────────────────
@router.get("/{tenant_id}/overview")
def client_overview(tenant_id: int, db: Session = Depends(get_db)):
    """Aggregated portal data for a client (counts, risk, recent activity)."""
    tenant = _resolve(db, tenant_id)

    hunts_count = db.query(func.count(Hunt.id)).filter_by(tenant_id=tenant_id).scalar() or 0
    datasets_count = db.query(func.count(Dataset.id)).filter_by(tenant_id=tenant_id).scalar() or 0

    real = (Finding.tenant_id == tenant_id, Finding.category != "no_finding")
    by_category = dict(
        db.query(Finding.category, func.count(Finding.id))
        .filter(*real).group_by(Finding.category).all()
    )
    by_status = dict(
        db.query(Finding.status, func.count(Finding.id))
        .filter(*real).group_by(Finding.status).all()
    )
    findings_total = sum(by_category.values())
    risk_score = min(100, sum(_RISK_WEIGHT.get(cat, 1) * n for cat, n in by_category.items()))
    risk_label = (
        "Critical" if risk_score >= 75 else "High" if risk_score >= 50
        else "Medium" if risk_score >= 25 else "Low" if risk_score > 0 else "None"
    )

    recent_hunts = (
        db.query(Hunt).filter_by(tenant_id=tenant_id).order_by(desc(Hunt.created_at)).limit(5).all()
    )
    recent_findings = (
        db.query(Finding).filter(*real).order_by(desc(Finding.created_at)).limit(6).all()
    )
    ordered_categories = [
        {"key": c["key"], "label": c["label_en"], "count": by_category[c["key"]]}
        for c in CATEGORIES if by_category.get(c["key"])
    ]

    return {
        "client": {
            "id": tenant.id, "name": tenant.name, "slug": tenant.slug,
            "edr": tenant.edr_platform, "siem": tenant.siem_platform,
            "xdr": tenant.xdr_platform, "sector": tenant.sector,
            "country": tenant.country, "city": tenant.city,
            "hunt_maturity": tenant.hunt_maturity, "sla_hours": tenant.sla_hours,
            "contract_end": tenant.contract_end,
            "has_logo": bool(tenant.logo_path),
        },
        "counts": {
            "hunts": hunts_count, "datasets": datasets_count,
            "findings": findings_total, "validated": by_status.get("validated", 0),
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
