"""
Correlation runner — orchestrates the correlation PHASE and persists its output.

Flow (one AnalysisJob, phase="correlation"):
  1. reset any prior correlation output for the hunt (idempotent re-runs),
  2. load the hunt's findings + per-dataset entity indexes,
  3. build the deterministic correlation package (Phase B),
  4. run the LLM correlation pass (Phase C),
  5. apply the result: merge duplicates, enrich findings, create incidents.

It never re-reads CSVs or re-runs per-dataset analysis — it works entirely over
the findings' Phase-A structured detail.
"""
from __future__ import annotations

import logging
import time

from sqlalchemy.orm import Session

from app.models import AnalysisJob, Dataset, Finding, Hunt, Incident
from app.services import correlation_engine, finding_details, jobs

logger = logging.getLogger("lens.correlation")


def _finding_dict(f: Finding) -> dict:
    # Findings created before Phase A have no structured `entities`; derive them
    # from the raw fields so correlation works on legacy findings too.
    entities = f.entities or finding_details.entities_from_fields(
        f.affected_users, f.affected_assets, f.evidence
    )
    return {
        "id": f.id,
        "finding_ref": f.finding_ref,
        "title": f.title,
        "category": f.category,
        "severity": f.severity,
        "summary": f.summary,
        "entities": entities,
        "time_range": f.time_range,
        "mitre": f.mitre,
        "dataset_id": f.dataset_id,
        "source_dataset": f.source_dataset,
    }


def _reset_correlation(db: Session, hunt_id: int) -> None:
    """Clear prior correlation output so a re-run starts clean."""
    db.query(Incident).filter_by(hunt_id=hunt_id).delete(synchronize_session=False)
    db.query(Finding).filter_by(hunt_id=hunt_id).update(
        {"chain_id": None, "merged_into_id": None, "enrichment": None},
        synchronize_session=False,
    )
    # Un-merge findings a previous run had merged (don't touch human statuses).
    db.query(Finding).filter_by(hunt_id=hunt_id, status="merged").update(
        {"status": "draft"}, synchronize_session=False
    )
    db.commit()


def _apply(
    db: Session, hunt_id: int, tenant_id: int,
    findings: list[Finding], out: dict, dataset_names: dict[int, str],
) -> dict:
    by_ref = {f.finding_ref: f for f in findings}
    summary = {"merges": 0, "enrichments": 0, "incidents": 0}

    # 1. Merges — survivor keeps a record; duplicates point at it and go 'merged'.
    for m in out.get("merges", []) or []:
        primary = by_ref.get(m.get("primary_ref"))
        if not primary:
            continue
        for dref in m.get("duplicate_refs", []) or []:
            dup = by_ref.get(dref)
            if dup and dup.id != primary.id and dup.merged_into_id is None:
                dup.merged_into_id = primary.id
                dup.status = "merged"
                summary["merges"] += 1

    # 2. Enrichments — cross-dataset corroboration notes.
    for e in out.get("enrichments", []) or []:
        f = by_ref.get(e.get("finding_ref"))
        if not f:
            continue
        cds = [d for d in (e.get("corroborating_datasets") or []) if isinstance(d, int)]
        f.enrichment = {
            "note": str(e.get("note") or "")[:2000],
            "corroborating_datasets": [
                {"id": d, "filename": dataset_names.get(d)} for d in cds
            ],
        }
        summary["enrichments"] += 1

    # 3. Incidents — attack-chains over >= 2 real findings.
    for item in out.get("incidents", []) or []:
        refs = [r for r in (item.get("finding_refs") or []) if r in by_ref]
        member_ids = [by_ref[r].id for r in refs]
        if len(member_ids) < 2:
            continue
        incident = Incident(
            tenant_id=tenant_id, hunt_id=hunt_id,
            title=str(item.get("title") or "Correlated incident")[:400],
            narrative=str(item.get("narrative") or "") or None,
            severity=item.get("severity"),
            confidence=item.get("confidence"),
            mitre_chain=item.get("mitre_chain"),
            timeline=item.get("timeline"),
            finding_ids=member_ids,
        )
        db.add(incident)
        db.flush()  # assign incident.id
        for r in refs:
            by_ref[r].chain_id = incident.id
        summary["incidents"] += 1

    db.commit()
    return summary


def run_correlation(db: Session, job_id: int) -> None:
    job = db.get(AnalysisJob, job_id)
    if job is None:
        return
    t0 = time.monotonic()

    def stage(msg: str, pct: int) -> None:
        if jobs.is_cancelled(db, job_id):
            raise jobs.JobCancelled()
        job.current_task = msg
        job.progress = pct
        job.log = (job.log or []) + [{"at": round(time.monotonic() - t0, 1), "msg": msg}]
        db.commit()

    try:
        hunt = db.get(Hunt, job.hunt_id)
        job.status = "running"
        job.log = []
        stage("Clearing previous correlation output", 10)
        _reset_correlation(db, hunt.id)

        findings = (
            db.query(Finding)
            .filter_by(hunt_id=hunt.id, tenant_id=job.tenant_id)
            .filter(Finding.merged_into_id.is_(None))
            .order_by(Finding.id)
            .all()
        )
        stage(f"Loaded {len(findings)} finding(s)", 20)
        if len(findings) < 2:
            job.status = "done"
            job.progress = 100
            job.current_task = "Nothing to correlate"
            job.result = {"incidents": 0, "merges": 0, "enrichments": 0,
                          "note": "fewer than 2 findings"}
            db.commit()
            return

        datasets = db.query(Dataset).filter_by(
            hunt_id=hunt.id, tenant_id=job.tenant_id
        ).all()
        dataset_index = {d.id: (d.entity_index or {}) for d in datasets}
        dataset_names = {d.id: d.filename for d in datasets}

        fdicts = [_finding_dict(f) for f in findings]
        package = correlation_engine.build_correlation_package(fdicts, dataset_index)
        stage(
            f"Graph built — {len(package['links'])} entity link(s), "
            f"{len(package['clusters'])} candidate chain(s)",
            35,
        )

        stage("Correlating findings with the analyst model…", 55)
        out = correlation_engine.run_llm_correlation(fdicts, package)
        stage(
            f"Model proposed {len(out.get('incidents', []))} incident(s), "
            f"{len(out.get('merges', []))} merge(s), {len(out.get('enrichments', []))} enrichment(s)",
            80,
        )

        stage("Applying correlation results", 90)
        summary = _apply(db, hunt.id, job.tenant_id, findings, out, dataset_names)
        stage(
            f"Done — {summary['incidents']} incident(s), {summary['merges']} merged, "
            f"{summary['enrichments']} enriched",
            100,
        )

        job.status = "done"
        job.progress = 100
        job.current_task = "Complete"
        job.result = {
            **summary,
            "trace": {
                "parse_error": bool(out.get("parse_error")),
                "links": len(package["links"]),
                "clusters": len(package["clusters"]),
            },
        }
        db.commit()
        # Auto-run QA after correlation if the hunt opted in.
        try:
            if getattr(hunt, "auto_qa", False):
                from app.services import qa_runner  # lazy: avoid import cycle
                qa_job = AnalysisJob(tenant_id=job.tenant_id, hunt_id=hunt.id,
                                     phase="qa", status="queued")
                db.add(qa_job); db.commit(); db.refresh(qa_job)
                qa_runner.run_qa(db, qa_job.id)
        except Exception:  # noqa: BLE001 — QA must never break correlation
            logger.exception("auto-QA after correlation failed (hunt=%s)", hunt.id)
    except jobs.JobCancelled:
        db.rollback()
        job = db.get(AnalysisJob, job_id)
        job.status = "cancelled"
        job.current_task = "Cancelled"
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Correlation failed (job=%s): %s", job_id, exc)
        db.rollback()
        job = db.get(AnalysisJob, job_id)
        job.status = "error"
        job.error = str(exc)
        db.commit()
