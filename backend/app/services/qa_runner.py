"""
QA runner — orchestrates the quality-assurance phase and persists its output.

One AnalysisJob (phase="qa"):
  1. gather hunt state (datasets, findings, correlation status, parse errors),
  2. run deterministic process + per-finding completeness/grounding checks,
  3. run the LLM judge per finding,
  4. REMEDIATE: gap-fill incomplete findings (evidence-only) and run correlation
     if it never ran,
  5. compute critical issues (await user decision) + overall status,
  6. persist Finding.qa and one QAReport per hunt (idempotent re-runs).
"""
from __future__ import annotations

import json
import logging
import time

from sqlalchemy.orm import Session

from app.models import AnalysisJob, Dataset, Finding, Hunt, QAReport
from app.services import jobs, prompts, qa_engine, tenant_models
from app.services import ollama_client as ollama

logger = logging.getLogger("lens.qa")

_FIX_FIELDS = ("mitre", "recommendations", "affected_assets", "affected_users",
               "severity", "confidence")


def _correlation_done(db: Session, hunt_id: int, tenant_id: int) -> bool:
    return (
        db.query(AnalysisJob)
        .filter_by(hunt_id=hunt_id, tenant_id=tenant_id, phase="correlation", status="done")
        .first()
        is not None
    )


def _parse_error_datasets(db: Session, hunt_id: int, tenant_id: int) -> list[int]:
    # A parse failure now lands a job in status='error' (it is no longer reported
    # as a clean 'done'); older runs may still be 'done' with the trace flag, so
    # accept both rather than filter by status.
    out: list[int] = []
    for j in db.query(AnalysisJob).filter_by(
        hunt_id=hunt_id, tenant_id=tenant_id, phase="analysis"
    ):
        if j.dataset_id and ((j.result or {}).get("trace") or {}).get("analyst_parse_error"):
            out.append(j.dataset_id)
    return out


def _gap_fill(finding: Finding, model: str | None = None) -> tuple[dict, dict] | None:
    """Ask the analyst model to fill QA-flagged gaps from the finding's own
    evidence. Returns (applied_fields, before_values) so the change can be rolled
    back, or None when nothing was filled."""
    qa = finding.qa or {}
    missing = list(qa.get("gaps", [])) + list((qa.get("judge") or {}).get("missing", []))
    if not missing:
        return None
    payload = {
        "finding_ref": finding.finding_ref,
        "title": finding.title,
        "summary": finding.summary,
        "evidence": finding.evidence,
        "evidence_rows": (finding.evidence_rows or [])[:5],
        "behavioral_context": finding.behavioral_context,
        "mitre": finding.mitre,
        "affected_assets": finding.affected_assets,
        "affected_users": finding.affected_users,
        "severity": finding.severity,
        "confidence": finding.confidence,
    }
    sys = prompts.QA_FIX_SYSTEM.format(guardrails=prompts.GUARDRAILS)
    user = prompts.QA_FIX_PROMPT.format(
        finding_json=json.dumps(payload, ensure_ascii=False, default=str)[:4000],
        missing=", ".join(str(m) for m in missing)[:400],
    )
    try:
        out = ollama.parse_json_response(ollama.analyst(sys, user, model=model))
    except ollama.OllamaError:
        return None
    if not isinstance(out, dict):
        return None
    applied: dict = {}
    before: dict = {}
    for field in _FIX_FIELDS:
        val = out.get(field)
        if val in (None, "", [], {}):
            continue
        # Only fill where empty (don't overwrite analyst-authored values).
        current = getattr(finding, field, None)
        if current in (None, "", [], {}):
            before[field] = current  # snapshot for rollback
            setattr(finding, field, val)
            applied[field] = val
    return (applied, before) if applied else None


def _overall_status(stage_checks: list[dict], findings: list[Finding]) -> str:
    if any(c["status"] == "fail" for c in stage_checks):
        return "critical"
    if any((f.qa or {}).get("status") == "critical" for f in findings):
        return "critical"
    if any(c["status"] == "warn" for c in stage_checks) or any(
        (f.qa or {}).get("status") in ("incomplete", "minor") for f in findings
    ):
        return "needs_attention"
    return "passed"


def run_qa(db: Session, job_id: int, feedback: str | None = None) -> None:
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
        tid = job.tenant_id
        # CRITICAL: this client's configured model, never the global default.
        model = tenant_models.resolve_analyst_model(db, tid)
        job.status = "running"
        if model:
            job.model = model
        job.log = []
        stage("Starting QA", 8)

        datasets = db.query(Dataset).filter_by(hunt_id=hunt.id, tenant_id=tid).all()
        dataset_index = {d.id: (d.entity_index or {}) for d in datasets}
        findings = (
            db.query(Finding)
            .filter_by(hunt_id=hunt.id, tenant_id=tid)
            .filter(Finding.merged_into_id.is_(None))
            .order_by(Finding.id)
            .all()
        )

        # 1. Process checks
        correlation_done = _correlation_done(db, hunt.id, tid)
        stage_checks = qa_engine.check_process(
            hunt=hunt, datasets=datasets,
            parse_error_datasets=_parse_error_datasets(db, hunt.id, tid),
            correlation_done=correlation_done,
        )
        stage(f"Process checks: {sum(c['status']=='pass' for c in stage_checks)}/"
              f"{len(stage_checks)} passed", 25)

        # 2. Per-finding deterministic checks
        for f in findings:
            f.qa = qa_engine.check_finding(f, dataset_index)
        stage(f"Completeness checked on {len(findings)} finding(s)", 40)

        # 3. LLM judge
        verdicts = qa_engine.judge_findings(findings, feedback=feedback, model=model)
        for f in findings:
            v = verdicts.get(f.finding_ref)
            if v:
                qa = f.qa or {}
                qa["judge"] = v
                if v.get("verdict") == "critical":
                    qa["status"] = "critical"
                f.qa = qa
        judged = len(verdicts)
        stage(f"Judged {judged} finding(s)", 60)
        db.commit()

        # 4. Remediation
        actions: list[dict] = []
        if not correlation_done and len(findings) >= 2:
            stage("Correlation never ran — running it now", 68)
            from app.services import correlation_runner  # lazy: avoid import cycle
            corr = AnalysisJob(tenant_id=tid, hunt_id=hunt.id, phase="correlation", status="queued")
            db.add(corr); db.commit(); db.refresh(corr)
            correlation_runner.run_correlation(db, corr.id)
            actions.append({"action": "ran_correlation", "detail": "Correlation phase executed by QA."})

        filled = 0
        attempted = 0
        to_fix = [f for f in findings if (f.qa or {}).get("status") in ("incomplete", "minor")]
        for i, f in enumerate(to_fix):
            stage(f"Gap-filling finding {f.finding_ref} ({i+1}/{len(to_fix)})",
                  70 + int(18 * (i + 1) / max(1, len(to_fix))))
            attempted += 1
            result = _gap_fill(f, model=model)
            if result:
                applied, before = result
                filled += 1
                # re-check after filling
                f.qa = {**qa_engine.check_finding(f, dataset_index),
                        "judge": (f.qa or {}).get("judge")}
                actions.append({"action": "gap_filled", "finding_ref": f.finding_ref,
                                "finding_id": f.id, "fields": list(applied.keys()),
                                "before": before, "rolled_back": False})
        db.commit()
        stage(f"Gap-filled {filled} finding(s)"
              + (f" ({attempted - filled} had nothing fillable)" if attempted > filled else ""),
              90)

        # 5. Critical issues awaiting user decision
        critical_issues = []
        for c in stage_checks:
            if c["status"] == "fail":
                critical_issues.append({"type": "stage", "stage": c["stage"],
                                        "detail": c["detail"], "fix": c["fix"],
                                        "meta": c.get("meta") or {}})
        for f in findings:
            qa = f.qa or {}
            if qa.get("status") == "critical":
                critical_issues.append({
                    "type": "finding", "finding_ref": f.finding_ref, "title": f.title,
                    "detail": "; ".join(qa.get("grounding_issues", []))
                    or (qa.get("judge") or {}).get("suggested_fix")
                    or "Flagged critical by QA.",
                })

        # 6. Persist report
        status = _overall_status(stage_checks, findings)
        scores = [(f.qa or {}).get("score", 0) for f in findings]

        # Plain-language record of everything QA did this run, always populated so
        # the operator can see the phase actually worked even when nothing changed.
        checks_passed = sum(c["status"] == "pass" for c in stage_checks)
        activity = [
            f"Ran {len(stage_checks)} pipeline checks — {checks_passed} passed, "
            f"{len(stage_checks) - checks_passed} flagged.",
            f"Completeness + grounding checked on {len(findings)} finding(s).",
            (f"Reviewer model judged {judged} finding(s)."
             if judged else "Reviewer model returned no verdicts (parse failure or no findings)."),
        ]
        if filled:
            activity.append(f"Gap-filled {filled} finding(s) from their own evidence "
                            "(reversible — see Roll back).")
        elif attempted:
            activity.append(f"Attempted gap-fill on {attempted} finding(s); "
                            "nothing could be safely filled from evidence.")
        else:
            activity.append("No findings needed gap-filling.")
        if any(a["action"] == "ran_correlation" for a in actions):
            activity.append("Correlation phase executed (it had not run).")

        db.query(QAReport).filter_by(hunt_id=hunt.id, tenant_id=tid).delete(
            synchronize_session=False
        )
        db.add(QAReport(
            tenant_id=tid, hunt_id=hunt.id, status=status,
            stage_checks=stage_checks,
            totals={
                "findings": len(findings),
                "avg_completeness": round(sum(scores) / len(scores)) if scores else 0,
                "complete": sum(1 for f in findings if (f.qa or {}).get("status") == "pass"),
                "incomplete": sum(1 for f in findings if (f.qa or {}).get("status") == "incomplete"),
                "minor": sum(1 for f in findings if (f.qa or {}).get("status") == "minor"),
                "critical": sum(1 for f in findings if (f.qa or {}).get("status") == "critical"),
                "judged": judged,
                "gap_filled": filled,
                "activity": activity,
            },
            critical_issues=critical_issues,
            actions=actions,
        ))
        job.status = "done"
        job.progress = 100
        job.current_task = "Complete"
        job.result = {"status": status, "critical": len(critical_issues),
                      "gap_filled": filled}
        stage(f"QA complete — {status} ({len(critical_issues)} critical issue(s))", 100)
        db.commit()
    except jobs.JobCancelled:
        db.rollback()
        job = db.get(AnalysisJob, job_id)
        job.status = "cancelled"; job.current_task = "Cancelled"
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("QA failed (job=%s): %s", job_id, exc)
        db.rollback()
        job = db.get(AnalysisJob, job_id)
        job.status = "error"; job.error = str(exc)
        db.commit()


def rollback_qa(db: Session, hunt_id: int, tenant_id: int) -> dict:
    """Undo the automatic gap-fill edits from the latest QA run.

    Restores each affected field to the value QA snapshotted before it wrote,
    marks those actions rolled_back, and returns a count. Idempotent: actions
    already rolled back are skipped. Does NOT touch correlation (that ran as a
    real phase and is not a per-finding edit)."""
    report = (
        db.query(QAReport)
        .filter_by(tenant_id=tenant_id, hunt_id=hunt_id)
        .order_by(QAReport.id.desc())
        .first()
    )
    if report is None:
        return {"reverted_findings": 0, "reverted_fields": 0}

    actions = list(report.actions or [])
    reverted_fields = 0
    reverted_findings = 0
    for a in actions:
        if a.get("action") != "gap_filled" or a.get("rolled_back"):
            continue
        fid = a.get("finding_id")
        before = a.get("before") or {}
        finding = db.get(Finding, fid) if fid else None
        if finding is None or finding.tenant_id != tenant_id:
            a["rolled_back"] = True  # finding gone — nothing to restore
            continue
        for field, old in before.items():
            setattr(finding, field, old)
            reverted_fields += 1
        a["rolled_back"] = True
        reverted_findings += 1

    # Persist the mutated action flags (JSON column needs reassignment to flush).
    report.actions = actions
    report.totals = {**(report.totals or {}),
                     "gap_filled": 0,
                     "activity": list((report.totals or {}).get("activity") or [])
                     + [f"Rolled back {reverted_findings} gap-fill edit(s)."]}
    db.commit()
    return {"reverted_findings": reverted_findings, "reverted_fields": reverted_fields}
