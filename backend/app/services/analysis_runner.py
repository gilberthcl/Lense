"""
Runs dataset analysis as a background job and persists findings.

Designed to be invoked from a FastAPI BackgroundTask. Datasets are processed
one at a time (per the methodology: never overwhelm the model with 35 CSVs at
once). Each call handles a single dataset.
"""
from __future__ import annotations

import logging
import re
import time

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    AnalysisJob, ClientApprovedSoftware, Dataset, Finding, Hunt, KnowledgeDocument,
)
from app.services import (
    categories, config_store, csv_loader, findings_engine, global_config, jobs,
    knowledge, methodology, methodology_parser,
)
from app.services import ollama_client as ollama

logger = logging.getLogger("lens.analysis")


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
    """Compact methodology summary for the analyst (kept small to stay fast)."""
    if not sections or not sections.get("available"):
        return ""
    lines = ["[methodology_plan] Hunt topics (with up to 2 key indicators each):"]
    poa = sections.get("plan_of_action", {})
    for t in poa.get("topics", []):
        mitre = f" ({t['mitre']})" if t.get("mitre") else ""
        lines.append(f"- {t['name']}{mitre}")
        for ind in t.get("indicators", [])[:2]:
            lines.append(f"    • {ind[:160]}")
    # Queries that already returned events — worth corroborating in the data.
    hot = [
        f"{r['name'].split(' Covers:')[0].strip()[:80]} ({r['result_count']})"
        for tq in sections.get("queries", [])
        for r in tq.get("rows", [])
        if r.get("status") == "results"
    ]
    if hot:
        lines.append("[queries_with_results]: " + "; ".join(hot[:12]))
    return "\n".join(lines)[:2000]


def _brief_topic_for(brief: dict | None, name: str) -> dict | None:
    """Best-matching comprehension-brief topic for a parsed query topic name."""
    if not isinstance(brief, dict):
        return None
    nt = methodology_parser._tokens(name)
    if not nt:
        return None
    best: tuple[float, dict] | None = None
    for t in brief.get("topics", []) or []:
        tt = methodology_parser._tokens(t.get("name", ""))
        if not tt:
            continue
        score = len(nt & tt) / max(1, len(nt | tt))
        if best is None or score > best[0]:
            best = (score, t)
    return best[1] if best and best[0] >= 0.3 else None


def _dataset_methodology_focus(
    sections: dict | None, brief: dict | None, filename: str
) -> str:
    """
    Look up — in the ALREADY-PARSED methodology (cached `methodology_sections`)
    and the cached comprehension `brief` — the specific executed query this
    dataset is the result of, plus that query's objective and indicators.

    This does NOT re-parse the methodology document; it only matches the dataset
    filename against the query entries that were parsed once and cached.
    """
    if not sections or not sections.get("available"):
        return ""
    base = re.sub(r"^\s*\d+\s*[-_.)]\s*", "", filename.rsplit(".", 1)[0])  # drop "N-" + ext
    ft = methodology_parser._tokens(base)
    if not ft:
        return ""

    queries = sections.get("queries", []) or []
    poa_topics = sections.get("plan_of_action", {}).get("topics", []) or []

    # Find the best-matching TOPIC by filename token overlap (a topic scores by the
    # best of its own name and any of its query rows). We then render that topic's
    # executed query row(s) — the dataset is the result set of that query.
    best: tuple[float, int, dict, dict | None] | None = None
    for ti, topic in enumerate(queries):
        tt = methodology_parser._tokens(topic.get("name", ""))
        score = len(ft & tt) / max(1, len(ft)) if tt else 0.0
        best_row: dict | None = None
        for row in topic.get("rows", []) or []:
            rt = methodology_parser._tokens(row.get("name", "")) | methodology_parser._tokens(
                row.get("query", "")
            )
            if not rt:
                continue
            rscore = len(ft & rt) / max(1, len(ft))
            if rscore > score:
                score, best_row = rscore, row
            elif best_row is None:
                best_row = row  # remember a row to show even if the name matched best
        if best is None or score > best[0]:
            best = (score, ti, topic, best_row)

    if not best or best[0] < 0.15:  # no confident match — full methodology still in prompt
        return ""

    _, ti, topic, matched_row = best
    lines = [
        "This dataset is the result set of the following executed hunt query "
        "(matched from the parsed methodology):",
        f"- Topic {topic.get('number', '?')}: {topic.get('name', '')}"
        + (f"  [MITRE: {topic['mitre']}]" if topic.get("mitre") else ""),
    ]
    # Render the matched query row, else the topic's rows (up to 2).
    rows_to_show = [matched_row] if matched_row else (topic.get("rows", []) or [])[:2]
    for row in rows_to_show:
        if not row:
            continue
        lines.append(f"- Executed query: {row.get('name', '')}")
        if row.get("query"):
            lines.append(f"    query logic: {str(row['query'])[:400]}")
        if row.get("outcome"):
            lines.append(
                f"    recorded outcome: {str(row['outcome'])[:160]} "
                f"(status={row.get('status')}, count={row.get('result_count')})"
            )
    if ti < len(poa_topics):
        inds = poa_topics[ti].get("indicators", []) or []
        if inds:
            lines.append("- Plan-of-action — what to look for in this data:")
            for ind in inds[:4]:
                lines.append(f"    • {str(ind)[:200]}")
    bt = _brief_topic_for(brief, topic.get("name", ""))
    if bt:
        if bt.get("objective"):
            lines.append(f"- Query objective: {str(bt['objective'])[:300]}")
        if bt.get("expected_benign"):
            lines.append(f"- Expected-benign / false positives: {str(bt['expected_benign'])[:300]}")
        if bt.get("malicious_indicators"):
            lines.append(f"- Malicious indicators: {str(bt['malicious_indicators'])[:300]}")
    return "\n".join(lines)[:2200]


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
    # Only the report standard + approved-software baseline are useful per-dataset;
    # previous reports are large and would bloat every prompt. Each is capped.
    for dt in ("approved_software", "report_standard"):
        for doc in db.query(KnowledgeDocument).filter_by(
            tenant_id=tenant_id, doc_type=dt
        ):
            parts.append(f"[{dt}] {doc.title}\n{(doc.content or '')[:600]}")
    sw = _approved_software_context(db, tenant_id)
    if sw:
        parts.append(sw[:800])
    return "\n\n".join(parts)[:2000]


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
    t0 = time.monotonic()
    try:
        job.status = "running"
        job.current_task = "Loading dataset"
        job.progress = 10
        job.log = []
        dataset.status = "analyzing"
        db.commit()

        # Phase 1 of the protocol: comprehend the methodology before any data.
        job.current_task = "Comprehending hunt methodology"
        job.progress = 20
        db.commit()
        brief = ensure_methodology_brief(db, hunt)
        sections = ensure_methodology_sections(db, hunt)

        df = csv_loader.load_csv(dataset.file_path, settings.max_upload_bytes)
        # Bounded sample keeps the prompt manageable while still giving the
        # extractor concrete rows to cite. The evidence_json is capped downstream
        # in findings_engine for very wide datasets.
        evidence = csv_loader.build_evidence_package(df, sample_rows=12)

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

        def _stage(name: str, pct: int) -> None:
            jobs.raise_if_cancelled(db, job.id)
            job.current_task = name
            job.progress = pct
            job.log = (job.log or []) + [{"at": round(time.monotonic() - t0, 1), "msg": name}]
            db.commit()

        # Consult the already-parsed methodology (cached) for the specific query
        # this dataset came from — no re-parsing of the document.
        dataset_focus = _dataset_methodology_focus(sections, brief, dataset.filename)
        if dataset_focus:
            _stage("Matched dataset to its methodology query", 50)

        ai = global_config.current_ai()
        result = findings_engine.analyze_dataset(
            on_stage=_stage,
            run_reviewer=ai.get("enable_reviewer", True),
            run_qa=ai.get("enable_qa", True),
            dataset_name=dataset.filename,
            evidence_package=evidence,
            methodology=hunt.methodology_text or "No methodology document provided.",
            finding_format=_finding_format(db, job.tenant_id),
            finding_categories=config_store.get_value(db, "finding_categories"),
            analysis_instructions=config_store.get_value(db, "analysis_instructions"),
            methodology_brief=brief,
            dataset_focus=dataset_focus,
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
        # Make the failure visible: it was previously only stored on the job
        # record, so `lense logs backend` showed nothing and the cause was a
        # mystery. Log the full traceback here.
        logger.exception(
            "Dataset analysis failed (job=%s dataset=%s): %s",
            job_id, getattr(dataset, "filename", "?"), exc,
        )
        db.rollback()
        job.status = "error"
        job.error = str(exc)
        if dataset:
            dataset.status = "error"
        db.commit()
