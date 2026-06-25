"""
Golden-eval runner — Phase 2 of per-tenant LoRA fine-tuning.

Builds the golden case set (committed synthetic cases + an optional per-tenant
holdout of validated findings), runs each through the real analysis pipeline,
scores with eval_metrics, and persists a baseline. The baseline is the line a
future fine-tuned model must not fall below (see eval_metrics.compare).

`run_eval(cases, analyze_fn)` is the pure, testable core — it takes an injected
`analyze_fn` so tests never need a live model. The default analyze_fn (built by
`default_analyze_fn`) calls findings_engine against the configured Ollama model,
which only happens on the operator's box.

Baselines live under training/ (git-ignored): the holdout is derived from client
findings, so it must never be committed.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models import Finding
from app.services import eval_metrics

logger = logging.getLogger("lens.eval")

GOLDEN_DIR = Path(__file__).parent / "eval_golden"
BASELINE_ROOT = Path("training")
HOLDOUT_LIMIT = 25  # cap so an eval run stays bounded (each case = a full pipeline pass)


# ── Case construction ────────────────────────────────────────────────────────

def load_synthetic_cases() -> list[dict]:
    """Committed, client-free golden cases bundled with the app."""
    cases: list[dict] = []
    if not GOLDEN_DIR.is_dir():
        return cases
    for path in sorted(GOLDEN_DIR.glob("*.json")):
        try:
            cases.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            logger.warning("Skipping unreadable golden case: %s", path)
    return cases


def _mitre_ids(mitre: Any) -> list[str]:
    out: list[str] = []
    for m in mitre or []:
        if isinstance(m, dict):
            v = m.get("technique_id") or m.get("id")
            if v:
                out.append(str(v))
        elif m:
            out.append(str(m))
    return out


def build_holdout_cases(db: Session, tenant_id: int, *, limit: int = HOLDOUT_LIMIT) -> list[dict]:
    """Per-tenant holdout: the most recent validated findings, reconstructed into
    eval cases (evidence in → expected finding out). Tenant-scoped."""
    findings = (
        db.query(Finding)
        .filter_by(tenant_id=tenant_id, status="validated")
        .filter(Finding.merged_into_id.is_(None))
        .order_by(Finding.id.desc())
        .limit(limit)
        .all()
    )
    cases: list[dict] = []
    for f in findings:
        evidence = {
            "entities": f.entities or {},
            "behavioral": f.behavioral_context or {},
            "sample_rows": (f.evidence_rows or [])[:5],
            "stats": {},
        }
        if isinstance(f.evidence, dict):
            evidence["evidence"] = f.evidence
        expected_entities = list(f.affected_assets or []) + list(f.affected_users or [])
        cases.append({
            "name": f.finding_ref,
            "source": "holdout",
            "evidence_package": evidence,
            "expected": [{
                "category": f.category,
                "entities": expected_entities,
                "mitre": _mitre_ids(f.mitre),
            }],
        })
    return cases


# ── Pipeline binding ─────────────────────────────────────────────────────────

AnalyzeFn = Callable[[dict], "tuple[list[dict], bool]"]


def default_analyze_fn(db: Session, tenant_id: int) -> AnalyzeFn:
    """Bind the real analysis pipeline as the eval's analyze function. Returns
    (produced_findings, parse_error) for a case. Runs the configured Ollama
    model — only invoked on the operator's box."""
    from app.services import config_store, findings_engine, global_config

    ai = global_config.current_ai()
    fmt = config_store.get_value(db, "finding_format")
    cats = config_store.get_value(db, "finding_categories")

    def _fn(case: dict) -> "tuple[list[dict], bool]":
        result = findings_engine.analyze_dataset(
            dataset_name=case.get("name", "golden-case"),
            evidence_package=case.get("evidence_package", {}),
            methodology=(
                "Golden evaluation set. Apply general evidence-based threat-hunting "
                "methodology; report only findings supported by the evidence."
            ),
            finding_format=fmt,
            finding_categories=cats,
            run_reviewer=ai.get("enable_reviewer", True),
            run_qa=ai.get("enable_qa", True),
        )
        produced = result.get("findings", []) or []
        parse_error = bool((result.get("trace") or {}).get("analyst_parse_error"))
        return produced, parse_error

    return _fn


# ── Pure core ────────────────────────────────────────────────────────────────

def run_eval(cases: list[dict], analyze_fn: AnalyzeFn) -> dict:
    """Run every case through analyze_fn and score it. Pure orchestration: a
    case that throws is counted as a run/parse error, never aborts the sweep."""
    case_scores: list[dict] = []
    rows: list[dict] = []
    parse_errors = 0
    for c in cases:
        try:
            produced, perr = analyze_fn(c)
        except Exception as exc:  # noqa: BLE001 — a failed case is a data point, not a crash
            logger.warning("Eval case %s failed: %s", c.get("name"), exc)
            produced, perr = [], True
        if perr:
            parse_errors += 1
        score = eval_metrics.score_case(
            c.get("expected", []), produced, c.get("evidence_package", {})
        )
        case_scores.append(score)
        rows.append({"name": c.get("name"), "source": c.get("source"),
                     "parse_error": perr, **score})
    return {
        "metrics": eval_metrics.aggregate(case_scores, parse_errors=parse_errors),
        "cases": rows,
    }


# ── Orchestration + persistence ──────────────────────────────────────────────

def execute_eval(db: Session, tenant_id: int, *, include_holdout: bool = False) -> dict:
    """Build cases, run them through the real pipeline, return a full report."""
    from app.services import global_config

    cases = load_synthetic_cases()
    holdout = build_holdout_cases(db, tenant_id) if include_holdout else []
    cases = cases + holdout

    report = run_eval(cases, default_analyze_fn(db, tenant_id))
    report.update({
        "tenant_id": tenant_id,
        "model": global_config.current_ai().get("analyst_model"),
        "sources": {
            "synthetic": sum(1 for c in cases if c.get("source") == "synthetic"),
            "holdout": len(holdout),
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return report


def baseline_path(tenant_id: int) -> Path:
    return BASELINE_ROOT / f"tenant_{tenant_id}" / "eval_baseline.json"


def save_baseline(tenant_id: int, report: dict) -> Path:
    path = baseline_path(tenant_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_baseline(tenant_id: int) -> dict | None:
    path = baseline_path(tenant_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
