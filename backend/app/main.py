"""FastAPI application entrypoint for the Threat Hunt Findings Engine."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import correlations, datasets, findings, hunts, knowledge, reports, tenants
from app.core.config import settings
from app.core.db import Base, engine
import app.models  # noqa: F401 — ensure models are registered on Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Dev convenience: enable pgvector + create tables. Set DB_AUTO_CREATE=false to
    # disable and manage the schema with Alembic instead (`alembic upgrade head`).
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    if settings.db_auto_create:
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="LENS — Threat Hunt Findings Engine", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tenants.router)
app.include_router(knowledge.router)
app.include_router(hunts.router)
app.include_router(datasets.router)
app.include_router(findings.router)
app.include_router(correlations.router)
app.include_router(reports.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "lens-thfe"}
