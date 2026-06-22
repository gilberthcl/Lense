"""Pydantic request/response schemas."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Tenants ────────────────────────────────────────────────────────────────
class TenantCreate(BaseModel):
    name: str
    slug: str
    context_notes: str | None = None


class TenantOut(ORMModel):
    id: int
    name: str
    slug: str
    context_notes: str | None
    created_at: datetime


# ── Knowledge ──────────────────────────────────────────────────────────────
class KnowledgeCreate(BaseModel):
    doc_type: str
    title: str
    content: str


class KnowledgeOut(ORMModel):
    id: int
    tenant_id: int
    doc_type: str
    title: str
    created_at: datetime


# ── Hunts ──────────────────────────────────────────────────────────────────
class HuntCreate(BaseModel):
    name: str
    objective: str | None = None
    methodology_text: str | None = None


class HuntOut(ORMModel):
    id: int
    tenant_id: int
    name: str
    objective: str | None
    status: str
    created_at: datetime


# ── Datasets ───────────────────────────────────────────────────────────────
class DatasetOut(ORMModel):
    id: int
    tenant_id: int
    hunt_id: int
    filename: str
    file_size: int
    row_count: int
    col_count: int
    status: str
    created_at: datetime


# ── Findings ───────────────────────────────────────────────────────────────
class FindingOut(ORMModel):
    id: int
    tenant_id: int
    hunt_id: int
    dataset_id: int | None
    finding_ref: str
    title: str
    category: str
    severity: str | None
    confidence: str | None
    summary: str | None
    evidence: dict | None
    mitre: dict | list | None
    affected_assets: dict | list | None
    affected_users: dict | list | None
    recommendations: str | None
    status: str
    created_at: datetime


class FindingStatusUpdate(BaseModel):
    status: str  # validated | rejected | draft


# ── Jobs ───────────────────────────────────────────────────────────────────
class JobOut(ORMModel):
    id: int
    hunt_id: int
    dataset_id: int | None
    phase: str
    status: str
    progress: int
    current_task: str | None
    error: str | None
    created_at: datetime
