"""
Per-tenant knowledge retrieval (RAG) — "learning without retraining".

Validated findings and tenant baselines (approved software, previous reports)
are chunked, embedded with `nomic-embed-text`, and stored in `knowledge_chunks`
(pgvector). During analysis we retrieve the most relevant chunks for the current
dataset and inject them into the Analyst's tenant context — so each hunt benefits
from what was learned on previous hunts, without ever fine-tuning a model.

Strictly tenant-scoped: every read and write filters by `tenant_id`. Embedding
calls are fail-open — if Ollama is unavailable, indexing/retrieval degrade to
no-ops rather than breaking the pipeline.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import KnowledgeChunk, KnowledgeDocument
from app.services import ollama_client as ollama

# Doc types worth retrieving as analysis context (the "learning" corpus +
# tenant baselines). Constitution docs (methodology/format/categories) are
# injected wholesale elsewhere, so they are intentionally excluded here.
RETRIEVABLE_DOC_TYPES = (
    "validated_finding",
    "approved_software",
    "previous_report",
    "report_standard",
)

_CHUNK_SIZE = 1200      # ~chars per chunk
_CHUNK_OVERLAP = 150    # chars of overlap to preserve context across boundaries


def chunk_text(text: str, size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks on paragraph boundaries where possible."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        if len(para) > size:
            # Hard-split an oversized paragraph by character window.
            if buf:
                chunks.append(buf)
                buf = ""
            start = 0
            while start < len(para):
                chunks.append(para[start : start + size])
                start += size - overlap
            continue
        if len(buf) + len(para) + 2 <= size:
            buf = f"{buf}\n\n{para}" if buf else para
        else:
            chunks.append(buf)
            # Carry overlap from the tail of the previous buffer.
            tail = buf[-overlap:] if overlap else ""
            buf = f"{tail}\n\n{para}" if tail else para
    if buf:
        chunks.append(buf)
    return chunks


def index_document(db: Session, document: KnowledgeDocument) -> int:
    """
    (Re)embed a knowledge document into tenant-scoped chunks.

    Returns the number of chunks written. Fail-open: returns 0 if embeddings
    are unavailable. Existing chunks for the document are replaced.
    """
    db.query(KnowledgeChunk).filter_by(document_id=document.id).delete()
    pieces = chunk_text(document.content)
    written = 0
    for piece in pieces:
        try:
            vector = ollama.embed(piece)
        except ollama.OllamaError:
            db.rollback()
            return 0  # fail-open: leave the doc unindexed rather than break
        db.add(
            KnowledgeChunk(
                tenant_id=document.tenant_id,
                document_id=document.id,
                chunk_text=piece,
                embedding=vector,
            )
        )
        written += 1
    db.commit()
    return written


def index_document_by_id(db: Session, document_id: int) -> int:
    doc = db.get(KnowledgeDocument, document_id)
    if doc is None:
        return 0
    return index_document(db, doc)


def retrieve(
    db: Session,
    tenant_id: int,
    query: str,
    *,
    k: int = 6,
    doc_types: tuple[str, ...] = RETRIEVABLE_DOC_TYPES,
) -> list[dict]:
    """
    Return up to k tenant-scoped chunks most relevant to `query`.

    Fail-open: returns [] if the query cannot be embedded. ALWAYS filters by
    tenant_id — knowledge never crosses a tenant boundary.
    """
    if not (query or "").strip():
        return []
    try:
        qvec = ollama.embed(query)
    except ollama.OllamaError:
        return []

    rows = (
        db.query(
            KnowledgeChunk.chunk_text,
            KnowledgeDocument.doc_type,
            KnowledgeDocument.title,
            KnowledgeChunk.embedding.cosine_distance(qvec).label("distance"),
        )
        .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
        .filter(
            KnowledgeChunk.tenant_id == tenant_id,
            KnowledgeChunk.embedding.isnot(None),
            KnowledgeDocument.doc_type.in_(doc_types),
        )
        .order_by("distance")
        .limit(k)
        .all()
    )
    return [
        {"doc_type": r.doc_type, "title": r.title, "text": r.chunk_text, "distance": float(r.distance)}
        for r in rows
    ]


def format_context(chunks: list[dict]) -> str:
    """Render retrieved chunks as injectable analyst context."""
    if not chunks:
        return ""
    parts = ["RELEVANT PRIOR KNOWLEDGE (retrieved from this client's knowledge base):"]
    for c in chunks:
        parts.append(f"[{c['doc_type']}] {c.get('title', '')}\n{c['text']}")
    return "\n\n".join(parts)
