# LENS (THFE) — Build Handoff Brief

**Read this first, then `CLAUDE.md`.** This document tells a fresh Claude Code
session what this project is, what already exists, and exactly what to build
next. This codebase was extracted from the LENS module of a larger platform
("CROSSBOW") and rebuilt as a standalone app. It has **no dependency on
CROSSBOW** — treat it as its own repository.

---

## 1. The goal (in one paragraph)

Build a **local, multi-tenant Threat Hunt Findings Engine**. A threat hunter has
already planned a hunt, written queries, and executed them against an EDR/SIEM.
The output is **25–35 CSV result sets** (500 KB–5 MB each, 20 MB max). This app
ingests those CSVs per hunt, plus the hunt's **methodology**, **finding
categories**, and **finding format** documents, and then — acting as a senior
threat hunter — analyzes each dataset to produce **evidence-only findings**
(Malicious / Suspicious / Risky / Policy Violation / Unconfirmed), correlates
entities across datasets, and generates a professional **DOCX report**.
Everything is **strictly isolated per client/tenant** and runs **fully local**
(Ollama), using **Western-origin models only** for compliance.

## 2. Non-negotiable rules

See `CLAUDE.md` → CRITICAL RULES. The big three:
1. **Tenant isolation is absolute** (`tenant_id` everywhere, always filtered).
2. **Evidence only** — never fabricate hosts/users/IPs/commands/hashes/stats;
   keep the code-level validation gate.
3. **"No Finding" is a valid outcome** — never manufacture findings.

## 3. Stack

FastAPI + PostgreSQL/pgvector + SQLAlchemy 2.x (backend); React + Vite +
TypeScript + Tailwind (frontend); Ollama local multi-agent (Analyst → Reviewer
→ QA); python-docx for reports. Models: `gemma3:27b` (analyst),
`gpt-oss:20b` (reviewer/QA), `nomic-embed-text` (embeddings).

## 4. What ALREADY EXISTS (Phase 1 — built and syntax-verified)

### Backend (`backend/app/`) — complete and `py_compile`-clean
- `core/config.py` — env-driven settings (DB, CORS, Ollama models, 20 MB cap).
- `core/db.py` — engine, session, declarative `Base`, `get_db` dependency.
- `models/__init__.py` — Tenant, KnowledgeDocument, KnowledgeChunk(pgvector),
  Hunt, Dataset, Finding, AnalysisJob. Every model is tenant-scoped.
- `schemas/__init__.py` — pydantic request/response models.
- `api/` — routers:
  - `tenants.py`   : list/create/get tenants
  - `knowledge.py` : per-tenant KB CRUD (methodology/finding_categories/
    finding_format/approved_software/report_standard/previous_report/
    validated_finding)
  - `hunts.py`     : list/create/get hunts (inherits tenant methodology)
  - `datasets.py`  : CSV upload (20 MB cap), list, trigger analyze (background
    job), poll job status
  - `findings.py`  : list findings, PATCH status (validate→writes back to KB)
  - `deps.py`      : `get_tenant` scoping dependency
- `services/`
  - `csv_loader.py`      : load CSV → deterministic **evidence package**
    (schema, statistics, entity extraction, sample rows). Anti-hallucination
    backbone.
  - `ollama_client.py`   : local Ollama calls + per-role wrappers + robust JSON
    parsing.
  - `prompts.py`         : Analyst/Reviewer/QA prompt scaffolds with guardrails.
    **These are faithful-in-spirit DEFAULTS** — replace with the operator's real
    methodology/finding-format text (see §6).
  - `findings_engine.py` : Analyst → Reviewer → QA pipeline + **code-level
    evidence validation gate** that drops unsupported findings.
  - `analysis_runner.py` : runs one dataset's analysis as a background job and
    persists findings; updates job progress.
- `main.py` — FastAPI app, CORS, routers, dev startup (enables pgvector +
  `create_all`). Health at `GET /api/health`.

### Frontend (`frontend/`) — React + Vite + TS + Tailwind
Tenants list/create → Tenant dashboard (knowledge base + hunts) → Hunt view
(CSV upload, per-dataset Analyze with live job-progress polling, findings table
with validate/reject and an expandable evidence drawer). Typed API client in
`src/lib/api.ts`. (If any page is incomplete, finish it per the API contract in
§7.)

## 5. What to BUILD NEXT (roadmap)

### Phase 2 — Reporting & correlation ✅ (built)
- `services/correlation.py`: cross-dataset entity correlation, computed on
  demand. Groups hosts/users (from `affected_assets`/`affected_users`) and
  IP/hash/domain IOCs (classified from finding `evidence`) and surfaces
  entities spanning ≥2 datasets as "campaign" candidates. Exposed via
  `GET /api/tenants/{tid}/hunts/{hid}/correlations`. Pure functions, unit-tested.
- `services/report_docx.py`: python-docx report — title block, executive
  summary (deterministic counts), per-dataset assessments, findings table +
  detail blocks, IOC table, MITRE ATT&CK mapping, correlations table.
  Bilingual (EN/ES) via a label catalogue. Endpoint
  `GET /api/tenants/{tid}/hunts/{hid}/report?lang=en|es` returns the .docx.
- Frontend: hunt-level "Generate Report (.docx)" with EN/ES selector +
  `CorrelationsPanel` (expandable per-entity occurrences).
- **Alembic** wired (`backend/alembic/`, initial migration `0001`). Dev still
  auto-creates via `DB_AUTO_CREATE=true`; set false in prod and run
  `alembic upgrade head`.

### Phase 3 — Validation workflow & learning
- Finding approval workflow UI (bulk validate/reject, reviewer notes).
- Implement `services/knowledge.py`: chunk + embed KB docs (`nomic-embed-text`)
  into `knowledge_chunks` (pgvector) and retrieve relevant context during
  analysis (RAG) — e.g. inject prior validated findings + approved-software
  baselines into the Analyst prompt. Keep retrieval tenant-scoped.

### Phase 4 — Future agents (separate from this engine)
Hypothesis generator; multi-platform query generator (CrowdStrike/Splunk/
QRadar/Sentinel/Vision One/Sigma); hunt recommendation; report writer.

## 6. IMPORTANT: get the real "constitution" documents

The operator has real **methodology**, **finding-categories**, and
**finding-format** documents that define how findings must be produced and
formatted. They were NOT available at extraction time, so `services/prompts.py`
ships sensible DEFAULTS. **Ask the operator for these documents** and either:
(a) seed them as a tenant's knowledge base entries (preferred — the app already
injects tenant methodology/finding_format into prompts), and/or
(b) refine the default scaffolds in `prompts.py` to match the required finding
structure exactly.

## 7. API contract (for finishing/extending the frontend)

```
GET    /api/health
GET    /api/tenants
POST   /api/tenants                         {name, slug, context_notes?}
GET    /api/tenants/{tid}
GET    /api/tenants/{tid}/knowledge
POST   /api/tenants/{tid}/knowledge         {doc_type, title, content}
DELETE /api/tenants/{tid}/knowledge/{docId}
GET    /api/tenants/{tid}/hunts
POST   /api/tenants/{tid}/hunts             {name, objective?, methodology_text?}
GET    /api/tenants/{tid}/hunts/{hid}
GET    /api/tenants/{tid}/hunts/{hid}/datasets
POST   /api/tenants/{tid}/hunts/{hid}/datasets            (multipart: file=*.csv)
POST   /api/tenants/{tid}/hunts/{hid}/datasets/{did}/analyze   -> job (202)
GET    /api/tenants/{tid}/hunts/{hid}/jobs/{jobId}            (poll progress)
GET    /api/tenants/{tid}/hunts/{hid}/findings
PATCH  /api/tenants/{tid}/hunts/{hid}/findings/{fid}     {status}
```
doc_type ∈ {methodology, finding_categories, finding_format, approved_software,
report_standard, previous_report, validated_finding}.
finding category ∈ {malicious, suspicious, risky, policy_violation, unconfirmed,
no_finding}. finding status ∈ {draft, validated, rejected}.

## 8. How to run (dev)

```bash
cp .env.example .env
docker compose up -d db                  # Postgres + pgvector
ollama pull gemma3:27b && ollama pull gpt-oss:20b && ollama pull nomic-embed-text
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000     # tables auto-create on startup
# new shell:
cd frontend && npm install && npm run dev      # http://localhost:5173
```
Ollama must be running on the host (`http://localhost:11434`).

## 9. First tasks for the new session (suggested order)

1. `pip install -r backend/requirements.txt`, bring up Postgres, run the
   backend, hit `GET /api/health`, create a tenant, a hunt, upload a sample
   CSV, and run an analysis end-to-end. Fix anything that doesn't run.
2. Get the operator's real methodology/finding-format docs (§6) and wire them
   in.
3. Build Phase 2 (DOCX report + correlation), then Alembic.
4. Keep every change tenant-scoped and evidence-only.
