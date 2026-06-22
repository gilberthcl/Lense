"""Pydantic request/response schemas."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Tenants (Clients) ──────────────────────────────────────────────────────
class ClientProfile(BaseModel):
    """Shared optional client fields (create + update)."""
    context_notes: str | None = None
    sector: str | None = None
    industries: list[str] | None = None
    country: str | None = None
    city: str | None = None
    is_global: bool | None = None
    internal_domain: str | None = None
    edr_platform: str | None = None
    siem_platform: str | None = None
    xdr_platform: str | None = None
    other_tech: str | None = None
    dpe_name: str | None = None
    dpe_email: str | None = None
    pm_name: str | None = None
    pm_email: str | None = None
    acct_other_name: str | None = None
    acct_other_role: str | None = None
    acct_other_email: str | None = None
    stakeholders: list[dict] | None = None
    contracted_services: list[str] | None = None
    sla_hours: int | None = None
    hunt_maturity: int | None = None
    contract_start: str | None = None
    contract_end: str | None = None


class TenantCreate(ClientProfile):
    name: str
    slug: str


class TenantUpdate(ClientProfile):
    name: str | None = None


class TenantOut(ORMModel):
    id: int
    name: str
    slug: str
    context_notes: str | None
    sector: str | None
    industries: list | None
    country: str | None
    city: str | None
    is_global: bool
    internal_domain: str | None
    edr_platform: str | None
    siem_platform: str | None
    xdr_platform: str | None
    other_tech: str | None
    dpe_name: str | None
    dpe_email: str | None
    pm_name: str | None
    pm_email: str | None
    acct_other_name: str | None
    acct_other_role: str | None
    acct_other_email: str | None
    stakeholders: list | None
    contracted_services: list | None
    sla_hours: int
    hunt_maturity: int
    logo_path: str | None
    contract_path: str | None
    contract_start: str | None
    contract_end: str | None
    created_at: datetime


# ── Contacts ───────────────────────────────────────────────────────────────
class ContactCreate(BaseModel):
    name: str
    title: str | None = None
    email: str | None = None
    phone: str | None = None
    is_primary: bool = False


class ContactOut(ORMModel):
    id: int
    tenant_id: int
    name: str
    title: str | None
    email: str | None
    phone: str | None
    is_primary: bool
    created_at: datetime


# ── Calendar ───────────────────────────────────────────────────────────────
class CalendarCreate(BaseModel):
    title: str
    event_type: str = "other"
    event_date: str | None = None
    notes: str | None = None


class CalendarOut(ORMModel):
    id: int
    tenant_id: int
    title: str
    event_type: str
    event_date: str | None
    notes: str | None
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


# ── Module configuration (global) ──────────────────────────────────────────
class ConfigOut(ORMModel):
    id: int
    module: str
    key: str
    title: str
    content: str
    updated_at: datetime


class ConfigUpdate(BaseModel):
    content: str


# ── Hunts ──────────────────────────────────────────────────────────────────
class HuntCreate(BaseModel):
    name: str
    objective: str | None = None
    methodology_text: str | None = None
    report_language: str = "English"
    edr: str | None = None
    siem: str | None = None


class HuntOut(ORMModel):
    id: int
    tenant_id: int
    name: str
    objective: str | None
    report_language: str
    edr: str | None
    siem: str | None
    methodology_text: str | None
    methodology_brief: dict | None
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
    reviewer_notes: str | None
    created_at: datetime


class FindingStatusUpdate(BaseModel):
    status: str | None = None  # validated | rejected | draft
    reviewer_notes: str | None = None


class FindingBulkUpdate(BaseModel):
    finding_ids: list[int]
    status: str  # validated | rejected | draft


# ── Approved software ──────────────────────────────────────────────────────
class ApprovedSoftwareCreate(BaseModel):
    name: str
    vendor: str | None = None
    category: str | None = None
    notes: str | None = None
    is_approved: bool = True


class ApprovedSoftwareBulk(BaseModel):
    names: list[str]
    is_approved: bool = True


class ApprovedSoftwareOut(ORMModel):
    id: int
    tenant_id: int
    name: str
    vendor: str | None
    category: str | None
    notes: str | None
    is_approved: bool
    created_at: datetime


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
