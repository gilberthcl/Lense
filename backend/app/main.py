"""FastAPI application entrypoint for the Threat Hunt Findings Engine."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import (
    auth as auth_api, config, correlations, datasets, eval as eval_api, findings,
    hunts, jobs as jobs_api, knowledge, models as models_api, qa, reports,
    tenants, training,
)
from app.core.config import settings
from app.core.db import Base, SessionLocal, engine
import app.models  # noqa: F401 — ensure models are registered on Base
from app.services import auth, config_store, global_config, jobs


# Additive columns introduced after a DB may already exist. create_all() only
# creates missing TABLES, never alters existing ones, and the dev DB predates
# Alembic stamping — so we add new columns idempotently here. Safe on fresh DBs
# (create_all already made them) and on populated ones (no data touched).
_COLUMN_ADDITIONS = (
    "ALTER TABLE findings ADD COLUMN IF NOT EXISTS entities JSON",
    "ALTER TABLE findings ADD COLUMN IF NOT EXISTS time_range JSON",
    "ALTER TABLE findings ADD COLUMN IF NOT EXISTS behavioral_context JSON",
    "ALTER TABLE findings ADD COLUMN IF NOT EXISTS evidence_rows JSON",
    "ALTER TABLE findings ADD COLUMN IF NOT EXISTS source_dataset VARCHAR(400)",
    "ALTER TABLE findings ADD COLUMN IF NOT EXISTS enrichment JSON",
    "ALTER TABLE findings ADD COLUMN IF NOT EXISTS chain_id INTEGER",
    "ALTER TABLE findings ADD COLUMN IF NOT EXISTS merged_into_id INTEGER",
    "ALTER TABLE findings ADD COLUMN IF NOT EXISTS qa JSON",
    "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS entity_index JSON",
    "ALTER TABLE hunts ADD COLUMN IF NOT EXISTS auto_correlate BOOLEAN DEFAULT FALSE",
    "ALTER TABLE hunts ADD COLUMN IF NOT EXISTS auto_qa BOOLEAN DEFAULT FALSE",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Dev convenience: enable pgvector + create tables. Set DB_AUTO_CREATE=false to
    # disable and manage the schema with Alembic instead (`alembic upgrade head`).
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    if settings.db_auto_create:
        Base.metadata.create_all(bind=engine)
        with engine.begin() as conn:
            for stmt in _COLUMN_ADDITIONS:
                conn.execute(text(stmt))
    # Seed the Structured Threat Hunt module config from version-controlled defaults.
    db = SessionLocal()
    try:
        config_store.seed_defaults(db)
        global_config.refresh(db)  # load editable AI-engine config into cache
        auth.refresh(db)           # load cached access-PIN hash
        jobs.cleanup_stale(db)     # fail jobs orphaned by a previous process
    finally:
        db.close()
    yield


app = FastAPI(title="LENS — Threat Hunt Findings Engine", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _auth_exempt(path: str, method: str) -> bool:
    """Endpoints reachable without the access PIN."""
    if method == "OPTIONS":  # CORS preflight
        return True
    if not path.startswith("/api"):
        return True
    if path == "/api/health" or path.startswith("/api/auth"):
        return True
    # Images are loaded via <img src> which can't send the auth header.
    if method == "GET" and (path.endswith("/logo") or path.endswith("/contract")):
        return True
    return False


@app.middleware("http")
async def access_pin_guard(request: Request, call_next):
    if auth.configured() and not _auth_exempt(request.url.path, request.method):
        token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not auth.check(token):
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


app.include_router(auth_api.router)
app.include_router(jobs_api.router)
app.include_router(config.router)
app.include_router(tenants.router)
app.include_router(knowledge.router)
app.include_router(hunts.router)
app.include_router(datasets.router)
app.include_router(findings.router)
app.include_router(correlations.router)
app.include_router(qa.router)
app.include_router(reports.router)
app.include_router(training.router)
app.include_router(eval_api.router)
app.include_router(models_api.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "lens-thfe", "build": "2026-06-23-rich-evidence"}
