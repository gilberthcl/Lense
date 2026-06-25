"""
SQLAlchemy models for the Threat Hunt Findings Engine.

Isolation rule: every table below (except `tenants`) carries a `tenant_id`.
All queries MUST filter by tenant_id — nothing crosses a tenant boundary.
"""
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Integer, String, Text, DateTime, ForeignKey, JSON, BigInteger, func,
    UniqueConstraint, Boolean,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


# ── Module configuration (global, not tenant-scoped) ───────────────────────
# Editable guides/standards for a LENS module. The "Structured Threat Hunt"
# module stores: analysis_instructions, finding_format, finding_categories.
# Designed generically so future modules can register their own config keys.
class ModuleConfig(Base):
    __tablename__ = "module_config"
    __table_args__ = (UniqueConstraint("module", "key", name="uq_module_config_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    module: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


# ── Tenants (clients) ──────────────────────────────────────────────────────
class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    context_notes: Mapped[str | None] = mapped_column(Text)  # baselines, env notes

    # ── Profile / location ──
    sector: Mapped[str | None] = mapped_column(String(120))
    industries: Mapped[list | None] = mapped_column(JSON)        # up to 3 tags
    country: Mapped[str | None] = mapped_column(String(80))
    city: Mapped[str | None] = mapped_column(String(120))
    is_global: Mapped[bool] = mapped_column(Boolean, default=False)
    internal_domain: Mapped[str | None] = mapped_column(String(300))

    # ── Technology stack ──
    edr_platform: Mapped[str | None] = mapped_column(String(120))
    siem_platform: Mapped[str | None] = mapped_column(String(120))
    xdr_platform: Mapped[str | None] = mapped_column(String(120))
    other_tech: Mapped[str | None] = mapped_column(Text)

    # ── Account management ──
    dpe_name: Mapped[str | None] = mapped_column(String(160))
    dpe_email: Mapped[str | None] = mapped_column(String(200))
    pm_name: Mapped[str | None] = mapped_column(String(160))
    pm_email: Mapped[str | None] = mapped_column(String(200))
    acct_other_name: Mapped[str | None] = mapped_column(String(160))
    acct_other_role: Mapped[str | None] = mapped_column(String(120))
    acct_other_email: Mapped[str | None] = mapped_column(String(200))
    stakeholders: Mapped[list | None] = mapped_column(JSON)       # [{name,title,email}]
    contracted_services: Mapped[list | None] = mapped_column(JSON)
    sla_hours: Mapped[int] = mapped_column(Integer, default=72)
    hunt_maturity: Mapped[int] = mapped_column(Integer, default=3)  # 1-5

    # ── Assets / contract ──
    logo_path: Mapped[str | None] = mapped_column(String(600))
    contract_path: Mapped[str | None] = mapped_column(String(600))
    contract_start: Mapped[str | None] = mapped_column(String(20))  # ISO date
    contract_end: Mapped[str | None] = mapped_column(String(20))

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    hunts: Mapped[list["Hunt"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    contacts: Mapped[list["ClientContact"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    calendar_events: Mapped[list["ClientCalendarEvent"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    approved_software: Mapped[list["ClientApprovedSoftware"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )


# ── Knowledge base (per-tenant constitution + learning) ────────────────────
# doc_type: methodology | finding_categories | finding_format |
#           approved_software | report_standard | previous_report | validated_finding
class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    doc_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class KnowledgeChunk(Base):
    """Chunked + embedded knowledge for retrieval (pgvector). Optional/RAG."""
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    # nomic-embed-text emits 768-dim vectors
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768))


# ── Hunts ──────────────────────────────────────────────────────────────────
# status: created | analyzing | analyzed | reported
class Hunt(Base):
    __tablename__ = "hunts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    objective: Mapped[str | None] = mapped_column(Text)
    methodology_text: Mapped[str | None] = mapped_column(Text)  # snapshot for this hunt
    # Hunt session parameters captured at start.
    report_language: Mapped[str] = mapped_column(String(40), default="English")
    edr: Mapped[str | None] = mapped_column(String(120))   # e.g. CrowdStrike Falcon
    siem: Mapped[str | None] = mapped_column(String(120))  # e.g. IBM QRadar
    # Cached LLM comprehension of the methodology (plan of action, queries, scope).
    methodology_brief: Mapped[dict | None] = mapped_column(JSON)
    # Deterministically-parsed sections: description, plan_of_action, queries.
    methodology_sections: Mapped[dict | None] = mapped_column(JSON)
    # LLM pre-analysis plan (phases/batches/complexity/QA) over dataset metadata.
    analysis_plan: Mapped[dict | None] = mapped_column(JSON)
    # Review/execution state for the plan: {status, feedback, accepted_at}.
    plan_state: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="created")
    # Run the correlation phase automatically when dataset analysis finishes.
    auto_correlate: Mapped[bool] = mapped_column(Boolean, default=False)
    # Run the QA phase automatically when correlation finishes.
    auto_qa: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    tenant: Mapped["Tenant"] = relationship(back_populates="hunts")
    datasets: Mapped[list["Dataset"]] = relationship(
        back_populates="hunt", cascade="all, delete-orphan"
    )
    findings: Mapped[list["Finding"]] = relationship(
        back_populates="hunt", cascade="all, delete-orphan"
    )


# ── Datasets (uploaded CSVs) ───────────────────────────────────────────────
# status: uploaded | analyzing | analyzed | error
class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    hunt_id: Mapped[int] = mapped_column(
        ForeignKey("hunts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    filename: Mapped[str] = mapped_column(String(400), nullable=False)
    file_path: Mapped[str] = mapped_column(String(600), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    col_count: Mapped[int] = mapped_column(Integer, default=0)
    columns: Mapped[dict | None] = mapped_column(JSON)   # [{name, dtype}, ...]
    stats: Mapped[dict | None] = mapped_column(JSON)      # computed statistics
    # Per-dataset entity + behavioral index, persisted at analysis time so the
    # correlation phase can cross-reference entities across datasets cheaply
    # (no LLM re-analysis).
    entity_index: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    hunt: Mapped["Hunt"] = relationship(back_populates="datasets")
    findings: Mapped[list["Finding"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )


# ── Findings ───────────────────────────────────────────────────────────────
# category: malicious | suspicious | risky | policy_violation | unconfirmed | no_finding
# status:   draft | validated | rejected
class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    hunt_id: Mapped[int] = mapped_column(
        ForeignKey("hunts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    dataset_id: Mapped[int | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    finding_ref: Mapped[str] = mapped_column(String(40))   # e.g. F-001
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    severity: Mapped[str | None] = mapped_column(String(20))   # info/low/med/high/crit
    confidence: Mapped[str | None] = mapped_column(String(20))
    summary: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[dict | None] = mapped_column(JSON)        # verbatim rows/values
    mitre: Mapped[dict | None] = mapped_column(JSON)           # techniques
    affected_assets: Mapped[dict | None] = mapped_column(JSON)
    affected_users: Mapped[dict | None] = mapped_column(JSON)
    recommendations: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    reviewer_notes: Mapped[str | None] = mapped_column(Text)  # analyst review notes
    # ── Structured detail for the correlation phase (Phase A) ──
    # Everything needed to correlate a finding WITHOUT re-reading the CSVs.
    entities: Mapped[dict | None] = mapped_column(JSON)            # {users,hosts,ips,domains,hashes,applications}
    time_range: Mapped[dict | None] = mapped_column(JSON)         # observed activity window
    behavioral_context: Mapped[dict | None] = mapped_column(JSON) # fan-out/concentration/TI signals
    evidence_rows: Mapped[list | None] = mapped_column(JSON)      # verbatim rows behind the finding
    source_dataset: Mapped[str | None] = mapped_column(String(400))  # filename it came from
    # ── Correlation-phase outputs (filled in Phases C/D) ──
    enrichment: Mapped[dict | None] = mapped_column(JSON)         # cross-dataset corroboration notes
    chain_id: Mapped[int | None] = mapped_column(Integer, index=True)        # incident/attack-chain grouping
    merged_into_id: Mapped[int | None] = mapped_column(Integer, index=True)  # dedup audit (survivor id)
    # ── QA-phase output ──
    # {score, status(pass|incomplete|critical), gaps:[...], verdict, missing:[...],
    #  suggested_fix, issues:[...]}
    qa: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    hunt: Mapped["Hunt"] = relationship(back_populates="findings")
    dataset: Mapped["Dataset"] = relationship(back_populates="findings")


# ── Incidents (correlation-phase output: an attack-chain over >=2 findings) ──
class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    hunt_id: Mapped[int] = mapped_column(
        ForeignKey("hunts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    narrative: Mapped[str | None] = mapped_column(Text)      # the attack-chain story
    severity: Mapped[str | None] = mapped_column(String(20))
    confidence: Mapped[str | None] = mapped_column(String(20))
    mitre_chain: Mapped[list | None] = mapped_column(JSON)   # ordered [{tactic,technique,finding_ref}]
    timeline: Mapped[list | None] = mapped_column(JSON)      # ordered [{time,event,finding_ref}]
    finding_ids: Mapped[list | None] = mapped_column(JSON)   # member finding ids
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ── QA report (quality-assurance phase: one latest per hunt) ───────────────
# status: passed | needs_attention | critical
class QAReport(Base):
    __tablename__ = "qa_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    hunt_id: Mapped[int] = mapped_column(
        ForeignKey("hunts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), default="needs_attention")
    stage_checks: Mapped[list | None] = mapped_column(JSON)   # [{stage,status,detail,fix}]
    totals: Mapped[dict | None] = mapped_column(JSON)         # counts/scores
    critical_issues: Mapped[list | None] = mapped_column(JSON)  # awaiting user decision
    actions: Mapped[list | None] = mapped_column(JSON)        # auto-actions taken
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ── Per-tenant fine-tuned model registry (LoRA adapters; Phase 3) ──────────
# One row per trained candidate. At most one `active` per tenant (enforced in
# the service). Isolation: a tenant's analysis only ever routes to its OWN
# active model — adapters are never shared (Critical Rule #1).
# status: draft | validating | active | rejected | retired
class TenantModel(Base):
    __tablename__ = "tenant_models"
    __table_args__ = (
        UniqueConstraint("tenant_id", "version", name="uq_tenant_model_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    base_model: Mapped[str] = mapped_column(String(120), nullable=False)
    ollama_model_name: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    train_metrics: Mapped[dict | None] = mapped_column(JSON)   # loss curve, iters, etc.
    eval_metrics: Mapped[dict | None] = mapped_column(JSON)    # candidate's golden-eval metrics
    baseline_metrics: Mapped[dict | None] = mapped_column(JSON)  # what it was compared against
    comparison: Mapped[dict | None] = mapped_column(JSON)      # eval_metrics.compare() output
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    trained_at: Mapped[datetime | None] = mapped_column(DateTime)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime)


# ── Client contacts ────────────────────────────────────────────────────────
class ClientContact(Base):
    __tablename__ = "client_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str | None] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(60))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    tenant: Mapped["Tenant"] = relationship(back_populates="contacts")


# ── Client calendar ────────────────────────────────────────────────────────
# event_type: pre_hunt | hunt | post_hunt | planning | review | other
class ClientCalendarEvent(Base):
    __tablename__ = "client_calendar"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), default="other")
    event_date: Mapped[str | None] = mapped_column(String(20))   # ISO date
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    tenant: Mapped["Tenant"] = relationship(back_populates="calendar_events")


# ── Client approved-software baseline (environment context) ────────────────
# Feeds the analyst: approved entries reduce false positives; non-approved
# entries flag policy violations / unapproved software.
class ClientApprovedSoftware(Base):
    __tablename__ = "client_approved_software"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    tenant: Mapped["Tenant"] = relationship(back_populates="approved_software")


# ── Analysis jobs (async per-dataset work) ─────────────────────────────────
# phase: analysis | correlation | report   status: queued|running|done|error
class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    hunt_id: Mapped[int] = mapped_column(
        ForeignKey("hunts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    dataset_id: Mapped[int | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE")
    )
    phase: Mapped[str] = mapped_column(String(20), default="analysis")
    status: Mapped[str] = mapped_column(String(20), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    current_task: Mapped[str | None] = mapped_column(String(300))
    model: Mapped[str | None] = mapped_column(String(120))  # LLM used for this job
    log: Mapped[list | None] = mapped_column(JSON)          # live progress log lines
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
