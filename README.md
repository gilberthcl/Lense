# LENS — Threat Hunt Findings Engine (THFE)

A **local, multi-tenant** AI-assisted Threat Hunting platform that consumes hunt
result datasets (CSV), executes analyst methodology, generates **evidence-only**
findings, correlates entities across datasets, and produces report-ready output.

> Seeded from the LENS module of CROSSBOW and rebuilt as a standalone app.
> This folder is self-contained — copy it into its own repository as-is.

---

## What it does

This engine operates **after** hunt planning, scoping, query development, and
query execution. It starts where the CSV results land:

```
CSV results obtained  →  Findings analysis  →  Correlation  →  Report (DOCX)
```

Per hunt it ingests:

- **Methodology** — the hunt's investigation logic & false-positive guidance
- **Finding categories** — Malicious / Suspicious / Risky / Policy Violation / Unconfirmed
- **Finding format** — the standardized finding structure the output must match
- **25–35 CSV datasets** — 500 KB–5 MB typical, 20 MB max
- **Client/tenant context** — baselines, approved software, reporting standards

## Hard rules (from the threat-hunting methodology)

1. **Strict tenant isolation** — no knowledge, findings, reports, or datasets
   ever cross tenants. Every record is scoped to a `tenant_id`.
2. **Evidence-only findings** — never invent hosts, users, IPs, commands,
   hashes, or statistics. `No Finding` is a valid, expected outcome.
3. Every finding carries **MITRE mapping, confidence, severity, evidence**.
4. **Learning without retraining** — validated findings feed a per-tenant
   knowledge base that improves future hunts. Models are never fine-tuned.
5. **Local-only / compliant models** — Western-origin Ollama models only; no
   cloud-offload models (they break tenant isolation).

## Stack

| Layer     | Choice |
|-----------|--------|
| Frontend  | React + Vite + Tailwind |
| Backend   | Python 3.11 + FastAPI |
| Database  | PostgreSQL 16 + pgvector |
| LLM       | Ollama (local) — multi-agent: Analyst → Reviewer → QA |
| Reports   | python-docx |

### Model roles (compliant, Western-origin)

| Role            | Model              | Origin     |
|-----------------|--------------------|------------|
| Primary Analyst | `gemma3:27b`       | Google     |
| Senior Reviewer | `gpt-oss:20b`      | OpenAI     |
| Report QA       | `gpt-oss:20b`      | OpenAI     |
| Embeddings      | `nomic-embed-text` | Nomic (US) |

> On 32 GB RAM, `gemma3:27b` (~17 GB) + `gpt-oss:20b` (~13 GB) is the practical
> stack. `nemotron` (42 GB) / `llama3.3:70b` (~40 GB) need more RAM — swap them
> into the config once available. Never use `*-cloud` models for client data.

## Quick start (dev)

```bash
cp .env.example .env            # adjust if needed
docker compose up -d db         # Postgres + pgvector
# backend
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# Tables + pgvector are auto-created on first startup (dev). Alembic comes in P2.
uvicorn app.main:app --reload --port 8000
# frontend (separate shell)
cd frontend && npm install && npm run dev
```

Ollama runs on the host (`http://localhost:11434`). Pull the models:

```bash
ollama pull gemma3:27b
ollama pull gpt-oss:20b
ollama pull nomic-embed-text
```

## Database migrations (Alembic)

Dev auto-creates tables on startup (`DB_AUTO_CREATE=true`). For production, set
`DB_AUTO_CREATE=false` and manage the schema with Alembic:

```bash
cd backend
alembic upgrade head          # apply migrations
alembic revision --autogenerate -m "describe change"   # after model changes
```

## Roadmap

- **Phase 1 (MVP)** ✅ — tenant mgmt, knowledge base upload, CSV upload,
  single-dataset analysis, finding generation.
- **Phase 2** ✅ — cross-dataset correlation, DOCX reports (EN/ES), IOC tables,
  MITRE mapping, Alembic migrations.
- **Phase 3** — multi-agent validation, finding approval workflow, KB RAG
  (`nomic-embed-text` → pgvector).
- **Phase 4** — hypothesis generation, query generation, threat-intel.
