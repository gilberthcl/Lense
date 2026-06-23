"""Findings listing + validation workflow (validated findings feed learning)."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_tenant
from app.core.db import SessionLocal, get_db
from app.models import Finding, KnowledgeDocument, Tenant
from app.schemas import FindingBulkUpdate, FindingOut, FindingStatusUpdate
from app.services import knowledge

router = APIRouter(prefix="/api/tenants/{tenant_id}/hunts/{hunt_id}/findings", tags=["findings"])

VALID_STATUSES = {"draft", "validated", "rejected"}


def _index_doc_async(document_id: int) -> None:
    """Embed a knowledge document into the tenant KB (own session, fail-open)."""
    db = SessionLocal()
    try:
        knowledge.index_document_by_id(db, document_id)
    finally:
        db.close()


def _promote_to_knowledge(db: Session, finding: Finding) -> int | None:
    """Create a validated_finding KB document. Returns its id (to index)."""
    doc = KnowledgeDocument(
        tenant_id=finding.tenant_id,
        doc_type="validated_finding",
        title=f"{finding.finding_ref}: {finding.title}",
        content="\n\n".join(
            p for p in (finding.summary, finding.recommendations, finding.reviewer_notes) if p
        ),
    )
    db.add(doc)
    db.flush()  # assign id without ending the transaction
    return doc.id


@router.delete("/{finding_id}", status_code=204)
def delete_finding(
    hunt_id: int,
    finding_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Hard-delete a finding everywhere — including any KB doc it was promoted to."""
    finding = db.get(Finding, finding_id)
    if not finding or finding.tenant_id != tenant.id or finding.hunt_id != hunt_id:
        raise HTTPException(status_code=404, detail="Finding not found")
    if finding.finding_ref:
        db.query(KnowledgeDocument).filter(
            KnowledgeDocument.tenant_id == tenant.id,
            KnowledgeDocument.doc_type == "validated_finding",
            KnowledgeDocument.title.like(f"{finding.finding_ref}:%"),
        ).delete(synchronize_session=False)
    db.delete(finding)
    db.commit()


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
def update_finding(
    hunt_id: int,
    finding_id: int,
    payload: FindingStatusUpdate,
    background: BackgroundTasks,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    if payload.status is not None and payload.status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid status")
    finding = db.get(Finding, finding_id)
    if not finding or finding.tenant_id != tenant.id or finding.hunt_id != hunt_id:
        raise HTTPException(status_code=404, detail="Finding not found")

    if payload.reviewer_notes is not None:
        finding.reviewer_notes = payload.reviewer_notes

    doc_id: int | None = None
    if payload.status is not None:
        becoming_validated = payload.status == "validated" and finding.status != "validated"
        finding.status = payload.status
        # Learning loop: a validated finding becomes tenant knowledge (+ embedded).
        if becoming_validated:
            doc_id = _promote_to_knowledge(db, finding)

    db.commit()
    db.refresh(finding)
    if doc_id is not None:
        background.add_task(_index_doc_async, doc_id)
    return finding


@router.patch("", response_model=list[FindingOut])
def bulk_update_findings(
    hunt_id: int,
    payload: FindingBulkUpdate,
    background: BackgroundTasks,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    """Bulk validate/reject. Validated findings are promoted to the KB."""
    if payload.status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid status")
    findings = (
        db.query(Finding)
        .filter(
            Finding.id.in_(payload.finding_ids),
            Finding.tenant_id == tenant.id,
            Finding.hunt_id == hunt_id,
        )
        .all()
    )
    doc_ids: list[int] = []
    for finding in findings:
        becoming_validated = payload.status == "validated" and finding.status != "validated"
        finding.status = payload.status
        if becoming_validated:
            doc_ids.append(_promote_to_knowledge(db, finding))
    db.commit()
    for doc_id in doc_ids:
        background.add_task(_index_doc_async, doc_id)
    return findings
