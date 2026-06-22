"""
Runs dataset analysis as a background job and persists findings.

Designed to be invoked from a FastAPI BackgroundTask. Datasets are processed
one at a time (per the methodology: never overwhelm the model with 35 CSVs at
once). Each call handles a single dataset.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    AnalysisJob, ClientApprovedSoftware, Dataset, Finding, Hunt, KnowledgeDocument,
)
from app.services import (
    categories, config_store, csv_loader, findings_engine, jobs, knowledge,
    methodology, methodology_parser,
)
from app.services import ollama_client as ollama


def ensure_methodology_sections(db: Session, hunt: Hunt) -> dict | None:
    """Lazily compute + cache the deterministic methodology sections."""
    if hunt.methodology_sections:
        return hunt.methodology_sections
    if not (hunt.methodology_text or "").strip():
        return None
    sections = methodology_parser.parse_methodology(hunt.methodology_text)
    hunt.methodology_sections = sections
    db.commit()
    return sections


def _methodology_sections_context(sections: dict | None) -> str:
    """Compact, evidence-grounded summary of the methodology for the analyst."""
    if not sections or not sections.get("available"):
        return ""
    lines = ["[methodology_plan] Hunt topics and their detection focus:"]
    poa = sections.get("plan_of_action", {})
    for t in poa.get("topics", []):
        mitre = f" ({t['mitre']})" if t.get("mitre") else ""
        lines.append(f"- {t['name']}{mitre}")
        for ind in t.get("indicators", [])[:6]:
            lines.append(f"    • {ind}")
    # Which queries already returned results worth prioritising in the data.
    hot = [
        f"{r['name'].split(' Covers:')[0].strip()} ({r['result_count']} events)"
        for tq in sections.get("queries", [])
        for r in tq.get("rows", [])
        if r.get("status") == "results"
    ]
    if hot:
        lines.append(
            "[methodology_queries_with_results] These hunt queries already "
            "returned events — corroborate or refute them in the datasets:\n  - "
            + "\n  - ".join(hot[:40])
        )
    return "\n".join(lines)


def _approved_software_context(db: Session, tenant_id: int) -> str:
    """Render the structured approved-software baseline for the analyst."""
    rows = db.query(ClientApprovedSoftware).filter_by(tenant_id=tenant_id).all()
    if not rows:
        return ""
    approved = [r for r in rows if r.is_approved]
    denied = [r for r in rows if not r.is_approved]

    def _fmt(r: ClientApprovedSoftware) -> str:
        bits = [r.name]
        if r.vendor:
            bits.append(f"({r.vendor})")
        if r.category:
            bits.append(f"[{r.category}]")
        return " ".join(bits)

    out = []
    if approved:
        out.append(
            "[approved_software_baseline] The following software is APPROVED in "
            "this environment — do NOT flag it as a policy violation or treat it as "
            "inherently suspicious:\n- " + "\n- ".join(_fmt(r) for r in approved)
        )
    if denied:
        out.append(
            "[unapproved_software] The following software is explicitly NOT approved "
            "— its presence is a policy violation:\n- "
            + "\n- ".join(_fmt(r) for r in denied)
        )
    return "\n\n".join(out)


def _tenant_context(db: Session, tenant_id: int) -> str:
    parts = []
    for dt in ("approved_software", "report_standard", "previous_report"):
        for doc in db.query(KnowledgeDocument).filter_by(
            tenant_id=tenant_id, doc_type=dt
        ):
            parts.append(f"[{dt}] {doc.title}\n{doc.content}")
    sw = _approved_software_context(db, tenant_id)
    if sw:
        parts.append(sw)
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
        sections = ensure_methodology_sections(db, hunt)

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
            c for c in (
                _tenant_context(db, job.tenant_id),
                _methodology_sections_context(sections),
                knowledge.format_context(retrieved),
            ) if c
        )

        job.current_task = "Running analyst → reviewer → QA"
        job.progress = 50
        db.commit()
        jobs.raise_if_cancelled(db, job.id)

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
                    category=categories.normalize(f.get("category")),
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
    except jobs.JobCancelled:
        db.rollback()
        job = db.get(AnalysisJob, job_id)
        job.status = "cancelled"
        job.current_task = "Cancelled"
        if dataset:
            dataset.status = "uploaded"  # back to a re-runnable state
        db.commit()
    except Exception as exc:  # noqa: BLE001 — record any failure on the job
        db.rollback()
        job.status = "error"
        job.error = str(exc)
        if dataset:
            dataset.status = "error"
        db.commit()
