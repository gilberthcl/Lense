"""
QA engine — the quality-assurance phase.

Two layers, mirroring analysis/correlation:
  • DETERMINISTIC checks (this is the backbone): did each phase step run, and does
    every finding carry all the information it should + stay grounded in evidence?
  • LLM JUDGE (Reviewer model): per-finding quality — grounding, severity
    calibration, MITRE accuracy, false-positive discipline, and crucially what
    information is MISSING that the evidence actually supports.

Pure-ish functions over ORM rows / dicts so the deterministic parts are unit
testable. The runner wires them to a job, persists results, and remediates.
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.services import ollama_client as ollama
from app.services import prompts

# Fields every finding must carry to be report-ready.
REQUIRED_FIELDS = ("category", "severity", "summary", "evidence", "mitre", "recommendations")
# Phase-A structured detail that makes a finding rich enough to write up well.
DETAIL_FIELDS = ("entities", "time_range", "behavioral_context", "source_dataset", "evidence_rows")
_MITRE_RE = re.compile(r"^T\d{4}(?:\.\d{3})?$")


def _empty(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return not v.strip()
    if isinstance(v, (list, dict, tuple, set)):
        return len(v) == 0
    return False


def _flatten(v: Any) -> list[str]:
    out: list[str] = []
    if v is None:
        return out
    if isinstance(v, dict):
        for x in v.values():
            out += _flatten(x)
    elif isinstance(v, (list, tuple, set)):
        for x in v:
            out += _flatten(x)
    else:
        s = str(v).strip()
        if s:
            out.append(s)
    return out


def _mitre_issues(mitre: Any) -> list[str]:
    ids = _flatten(mitre)
    bad = [i for i in ids if _MITRE_RE.search(i) is None and re.search(r"T\d{4}", i) is None]
    return [f"invalid MITRE id: {b}" for b in bad[:5]] if bad else []


def _grounding_issues(finding: Any, dataset_index: dict[int, dict]) -> list[str]:
    """Affected entities should exist in the source dataset's entity index — a
    cited host/user that the dataset never contained is a hallucination signal."""
    idx = (dataset_index or {}).get(getattr(finding, "dataset_id", None)) or {}
    known = {str(v).lower() for v in _flatten(idx.get("entities") or {})}
    if not known:
        return []  # no index to check against (legacy dataset) — skip, don't false-alarm
    cited = _flatten(getattr(finding, "affected_assets", None)) + _flatten(
        getattr(finding, "affected_users", None)
    )
    missing = [c for c in cited if c.lower() not in known]
    return [f"cited entity not in dataset: {m}" for m in missing[:5]]


def check_finding(finding: Any, dataset_index: dict[int, dict]) -> dict[str, Any]:
    """Deterministic completeness + grounding for one finding."""
    gaps = [f for f in REQUIRED_FIELDS if _empty(getattr(finding, f, None))]
    if _empty(getattr(finding, "affected_assets", None)) and _empty(
        getattr(finding, "affected_users", None)
    ):
        gaps.append("affected_assets/users")
    detail_gaps = [d for d in DETAIL_FIELDS if _empty(getattr(finding, d, None))]
    mitre_issues = _mitre_issues(getattr(finding, "mitre", None))
    grounding = _grounding_issues(finding, dataset_index)

    total = len(REQUIRED_FIELDS) + 1  # required + affected entities
    score = round(100 * (total - len(gaps)) / total)
    if grounding:
        status = "critical"
    elif gaps:
        status = "incomplete"
    elif detail_gaps or mitre_issues:
        status = "minor"
    else:
        status = "pass"
    return {
        "score": score,
        "status": status,
        "gaps": gaps,
        "detail_gaps": detail_gaps,
        "mitre_issues": mitre_issues,
        "grounding_issues": grounding,
    }


def _chk(stage: str, ok: bool, ok_msg: str, fail_msg: str,
         fix: str | None = None, severity: str = "fail",
         meta: dict | None = None) -> dict:
    return {
        "stage": stage,
        "status": "pass" if ok else severity,
        "detail": ok_msg if ok else fail_msg,
        "fix": None if ok else fix,
        # Machine-actionable context for remediation buttons (e.g. which datasets
        # to re-analyze). Only carried when the check failed.
        "meta": None if ok else (meta or {}),
    }


def check_process(
    *, hunt: Any, datasets: list, parse_error_datasets: list[int], correlation_done: bool,
) -> list[dict]:
    """Did each phase step execute correctly?"""
    checks: list[dict] = []
    checks.append(_chk(
        "Methodology",
        bool(getattr(hunt, "methodology_text", None)),
        "Methodology document present.",
        "No methodology — analysis ran without query/FP context.",
        fix="add_methodology", severity="warn",
    ))
    not_analyzed = [d for d in datasets if d.status != "analyzed"]
    errored = [d for d in datasets if d.status == "error"]
    checks.append(_chk(
        "Dataset analysis",
        bool(datasets) and not not_analyzed,
        f"All {len(datasets)} dataset(s) analyzed.",
        f"{len(not_analyzed)} dataset(s) not analyzed"
        + (f" ({len(errored)} errored)" if errored else "") + ".",
        fix="reanalyze_datasets",
        meta={"dataset_ids": [getattr(d, "id", None) for d in not_analyzed],
              "dataset_names": [getattr(d, "filename", None) for d in not_analyzed]},
    ))
    pe_set = set(parse_error_datasets)
    pe_names = [getattr(d, "filename", None) for d in datasets if getattr(d, "id", None) in pe_set]
    checks.append(_chk(
        "Analysis integrity",
        not parse_error_datasets,
        "No analysis parse errors.",
        f"{len(parse_error_datasets)} dataset(s) had analysis parse errors — "
        "the analyst model's output failed to parse, so those findings may be "
        "degraded. Re-analyzing usually resolves it.",
        fix="reanalyze_datasets",
        meta={"dataset_ids": list(parse_error_datasets), "dataset_names": pe_names},
    ))
    checks.append(_chk(
        "Correlation",
        correlation_done,
        "Correlation phase ran.",
        # A not-yet-run correlation is a WARNING, not a failure — nothing broke,
        # the optional cross-dataset pass simply hasn't been run yet.
        "Correlation phase hasn't run yet — run it to merge duplicates and build "
        "attack-chains across datasets (optional, but recommended).",
        fix="run_correlation", severity="warn",
    ))
    return checks


# ── LLM judge (QA-B) ─────────────────────────────────────────────────────────

def _compact(finding: Any) -> dict:
    return {
        "finding_ref": finding.finding_ref,
        "title": finding.title,
        "category": finding.category,
        "severity": finding.severity,
        "confidence": finding.confidence,
        "summary": (finding.summary or "")[:500],
        "evidence": finding.evidence,
        "mitre": finding.mitre,
        "affected_assets": finding.affected_assets,
        "affected_users": finding.affected_users,
        "behavioral_context": finding.behavioral_context,
        "evidence_rows": (finding.evidence_rows or [])[:5],
    }


def judge_findings(findings: list, *, feedback: str | None = None) -> dict[str, dict]:
    """LLM quality verdicts keyed by finding_ref. Empty on parse failure."""
    if not findings:
        return {}
    payload = [_compact(f) for f in findings]
    sys = prompts.QA_JUDGE_SYSTEM.format(guardrails=prompts.GUARDRAILS)
    user = prompts.QA_JUDGE_PROMPT.format(
        findings_json=json.dumps(payload, ensure_ascii=False, default=str)[:11000],
        feedback=(feedback or "None.")[:1000],
    )
    try:
        out = ollama.parse_json_response(ollama.reviewer(sys, user))
    except ollama.OllamaError:
        return {}
    verdicts = out.get("verdicts", []) if isinstance(out, dict) else (out if isinstance(out, list) else [])
    result: dict[str, dict] = {}
    for v in verdicts or []:
        ref = v.get("finding_ref")
        if ref:
            result[ref] = {
                "verdict": v.get("verdict"),
                "missing": v.get("missing") or [],
                "false_positive_risk": v.get("false_positive_risk"),
                "severity_assessment": v.get("severity_assessment"),
                "suggested_fix": v.get("suggested_fix"),
            }
    return result
