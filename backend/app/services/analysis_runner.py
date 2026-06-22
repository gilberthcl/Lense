"""
Runs dataset analysis as a background job and persists findings.

Designed to be invoked from a FastAPI BackgroundTask. Datasets are processed
one at a time (per the methodology: never overwhelm the model with 35 CSVs at
once). Each call handles a single dataset.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AnalysisJob, Dataset, Finding, Hunt, KnowledgeDocument
from app.services import config_store, csv_loader, findings_engine, knowledge, methodology
from app.services import ollama_client as ollama


def _tenant_context(db: Session, tenant_id: int) -> str:
    parts = []
    for dt in ("approved_software", "report_standard", "previous_report"):
        for doc in db.query(KnowledgeDocument).filter_by(
            tenant_id=tenant_id, doc_type=dt
        ):
            parts.append(f"[{dt}] {doc.title}\n{doc.content}")
    return "\n\n".join(parts)


def _retrieval_query(hunt: Hunt, dataset: Dataset, evidence: dict) -> str:
    """Build a compact query string to retrieve relevant prior tenant knowledge."""
    bits = [hunt.name or "", dataset.filename or ""]
    brief = hunt.methodology_brief or {}
    if isinstance(brief, dict) and brief.get("hunt_overview"):
        bits.append(str(brief["hunt_overview"]))
    schema = evidence.get("schema") or []
    if schema:
        bits.append("columns: " + ", ".join(map(str, schema[:25])))
    for etype in ("hosts", "users", "processes"):
        vals = (evidence.get("entities") or {}).get(etype) or []
        if vals:
            bits.append(f"{etype}: " + ", ".join(map(str, vals[:10])))
    return "\n".join(b for b in bits if b)[:2000]


def _finding_format(db: Session, tenant_id: int) -> str:
    """Per-tenant override of the finding format, else the global config default."""
    doc = (
        db.query(KnowledgeDocument)
        .filter_by(tenant_id=tenant_id, doc_type="finding_format")
        .order_by(KnowledgeDocument.created_at.desc())
        .first()
    )
    if doc and doc.content:
        return doc.content
    return config_store.get_value(db, "finding_format")


def ensure_methodology_brief(db: Session, hunt: Hunt) -> dict | None:
    """Lazily compute + cache the hunt's methodology brief (comprehension pass)."""
    if hunt.methodology_brief:
        return hunt.methodology_brief
    if not (hunt.methodology_text or "").strip():
        return None
    try:
        brief = methodology.comprehend(
            hunt.methodology_text,
            edr=hunt.edr,
            siem=hunt.siem,
            language=hunt.report_language,
        )
    except ollama.OllamaError:
        return None
    hunt.methodology_brief = brief
    db.commit()
    return brief


def run_dataset_analysis(db: Session, job_id: int) -> None:
    """Execute the analysis pipeline for the dataset referenced by a job."""
    job = db.get(AnalysisJob, job_id)
    if job is None:
        return
    dataset = db.get(Dataset, job.dataset_id)
    hunt = db.get(Hunt, job.hunt_id)
    try:
        job.status = "running"
        job.current_task = "Loading dataset"
        job.progress = 10
        dataset.status = "analyzing"
        db.commit()

        # Phase 1 of the protocol: comprehend the methodology before any data.
        job.current_task = "Comprehending hunt methodology"
        job.progress = 20
        db.commit()
        brief = ensure_methodology_brief(db, hunt)

        df = csv_loader.load_csv(dataset.file_path, settings.max_upload_bytes)
        evidence = csv_loader.build_evidence_package(df)

        # Persist computed schema/stats for the UI.
        dataset.row_count = evidence["stats"]["row_count"]
        dataset.col_count = evidence["stats"]["col_count"]
        dataset.columns = evidence["schema"]
        dataset.stats = evidence["stats"]
        job.current_task = "Retrieving prior knowledge"
        job.progress = 40
        db.commit()
        # RAG: retrieve relevant prior validated findings + baselines (fail-open).
        retrieved = knowledge.retrieve(
            db, job.tenant_id, _retrieval_query(hunt, dataset, evidence)
        )
        tenant_context = "\n\n".join(
            c for c in (_tenant_context(db, job.tenant_id), knowledge.format_context(retrieved)) if c
        )

        job.current_task = "Running analyst → reviewer → QA"
        job.progress = 50
        db.commit()

        result = findings_engine.analyze_dataset(
            dataset_name=dataset.filename,
            evidence_package=evidence,
            methodology=hunt.methodology_text or "No methodology document provided.",
            finding_format=_finding_format(db, job.tenant_id),
            finding_categories=config_store.get_value(db, "finding_categories"),
            analysis_instructions=config_store.get_value(db, "analysis_instructions"),
            methodology_brief=brief,
            hunt_name=hunt.name,
            language=hunt.report_language or "English",
            edr=hunt.edr,
            siem=hunt.siem,
            tenant_context=tenant_context,
        )

        job.current_task = "Persisting findings"
        job.progress = 85
        existing = db.query(Finding).filter_by(hunt_id=hunt.id).count()
        for i, f in enumerate(result["findings"], start=existing + 1):
            db.add(
                Finding(
                    tenant_id=job.tenant_id,
                    hunt_id=hunt.id,
                    dataset_id=dataset.id,
                    finding_ref=f"F-{i:03d}",
                    title=f.get("title", "Untitled finding")[:400],
                    category=f.get("category", "unconfirmed"),
                    severity=f.get("severity"),
                    confidence=f.get("confidence"),
                    summary=f.get("summary"),
                    evidence=f.get("evidence"),
                    mitre=f.get("mitre"),
                    affected_assets=f.get("affected_assets"),
                    affected_users=f.get("affected_users"),
                    recommendations=f.get("recommendations"),
                )
            )

        dataset.status = "analyzed"
        job.status = "done"
        job.progress = 100
        job.current_task = "Complete"
        job.result = {
            "assessment": result["dataset_assessment"],
            "finding_count": len(result["findings"]),
            "trace": result["trace"],
        }
        db.commit()
    except Exception as exc:  # noqa: BLE001 — record any failure on the job
        db.rollback()
        job.status = "error"
        job.error = str(exc)
        if dataset:
            dataset.status = "error"
        db.commit()
