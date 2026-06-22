"""Per-tenant knowledge base: the hunt 'constitution' + learning corpus."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_tenant
from app.core.db import get_db
from app.models import KnowledgeDocument, Tenant
from app.schemas import KnowledgeCreate, KnowledgeOut

router = APIRouter(prefix="/api/tenants/{tenant_id}/knowledge", tags=["knowledge"])

VALID_DOC_TYPES = {
    "methodology", "finding_categories", "finding_format", "approved_software",
    "report_standard", "previous_report", "validated_finding",
}


@router.get("", response_model=list[KnowledgeOut])
def list_docs(tenant: Tenant = Depends(get_tenant), db: Session = Depends(get_db)):
    return (
        db.query(KnowledgeDocument)
        .filter_by(tenant_id=tenant.id)
        .order_by(KnowledgeDocument.doc_type, KnowledgeDocument.created_at.desc())
        .all()
    )


@router.post("", response_model=KnowledgeOut, status_code=201)
def add_doc(
    payload: KnowledgeCreate,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    if payload.doc_type not in VALID_DOC_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid doc_type. Allowed: {sorted(VALID_DOC_TYPES)}")
    doc = KnowledgeDocument(tenant_id=tenant.id, **payload.model_dump())
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@router.delete("/{doc_id}", status_code=204)
def delete_doc(
    doc_id: int,
    tenant: Tenant = Depends(get_tenant),
    db: Session = Depends(get_db),
):
    doc = db.get(KnowledgeDocument, doc_id)
    if not doc or doc.tenant_id != tenant.id:  # tenant-scoped guard
        raise HTTPException(status_code=404, detail="Document not found")
    db.delete(doc)
    db.commit()
