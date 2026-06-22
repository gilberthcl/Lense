"""Findings listing + validation workflow (validated findings feed learning)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_tenant
from app.core.db import get_db
from app.models import Finding, KnowledgeDocument, Tenant
from app.schemas import FindingOut, FindingStatusUpdate

router = APIRouter(prefix="/api/tenants/{tenant_id}/hunts/{hunt_id}/findings", tags=["findings"])


@router.get("", response_model=list[FindingOut])
def list_findings(
    hunt_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    return (
        db.query(Finding)
        .filter_by(hunt_id=hunt_id, tenant_id=tenant.id)
        .order_by(Finding.finding_ref)
        .all()
    )


@router.patch("/{finding_id}", response_model=FindingOut)
def update_finding_status(
    hunt_id: int,
    finding_id: int,
    payload: FindingStatusUpdate,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    if payload.status not in {"draft", "validated", "rejected"}:
        raise HTTPException(status_code=422, detail="Invalid status")
    finding = db.get(Finding, finding_id)
    if not finding or finding.tenant_id != tenant.id or finding.hunt_id != hunt_id:
        raise HTTPException(status_code=404, detail="Finding not found")

    finding.status = payload.status
    # Learning loop: a validated finding becomes tenant knowledge for future hunts.
    if payload.status == "validated":
        db.add(
            KnowledgeDocument(
                tenant_id=tenant.id,
                doc_type="validated_finding",
                title=f"{finding.finding_ref}: {finding.title}",
                content=(finding.summary or "") + "\n\n" + (finding.recommendations or ""),
            )
        )
    db.commit()
    db.refresh(finding)
    return finding
