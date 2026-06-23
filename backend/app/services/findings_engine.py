"""
Findings engine — orchestrates the Analyst → Reviewer → QA pipeline for a
single dataset and returns normalized, evidence-grounded findings.

Each finding is post-validated against the evidence package: any finding whose
cited entities do not appear in the evidence is dropped. This is a hard,
code-level anti-hallucination gate independent of model behavior.
"""
from __future__ import annotations

import json
import time
from typing import Any

from app.services import ollama_client as ollama
from app.services import prompts

DEFAULT_FINDING_FORMAT = (
    "Title, Category, Severity, Confidence, Summary, Evidence (verbatim), "
    "MITRE ATT&CK techniques, Affected Assets, Affected Users, Recommendations."
)


def _flatten_evidence_values(evidence_package: dict[str, Any]) -> set[str]:
    """All citable verbatim strings from the evidence package, lowercased."""
    values: set[str] = set()
    for vals in evidence_package.get("entities", {}).values():
        values.update(str(v).lower() for v in vals)
    for col_vals in evidence_package.get("stats", {}).get("top_values", {}).values():
        values.update(str(item["value"]).lower() for item in col_vals)
    for row in evidence_package.get("sample_rows", []):
        values.update(str(v).lower() for v in row.values())
    return values


def _validate_against_evidence(finding: dict, evidence_values: set[str]) -> bool:
    """
    Keep a finding only if its cited assets/users appear in the evidence.
    Empty asset/user lists are allowed (dataset-level observations).
    """
    cited = []
    cited += finding.get("affected_assets") or []
    cited += finding.get("affected_users") or []
    if not cited:
        return True
    return any(str(c).lower() in evidence_values for c in cited)


def analyze_dataset(
    *,
    dataset_name: str,
    evidence_package: dict[str, Any],
    methodology: str,
    finding_format: str | None = None,
    finding_categories: str | None = None,
    analysis_instructions: str | None = None,
    methodology_brief: dict[str, Any] | str | None = None,
    hunt_name: str = "Threat Hunt",
    language: str = "English",
    edr: str | None = None,
    siem: str | None = None,
    tenant_context: str | None = None,
    run_reviewer: bool = True,
    run_qa: bool = True,
    on_stage=None,
) -> dict[str, Any]:
    """Run the full pipeline. Returns {dataset_assessment, findings, trace}."""
    def stage(name: str, pct: int) -> None:
        if on_stage:
            on_stage(name, pct)

    # Prompt budget. The earlier build over-trimmed everything to ~4k tokens,
    # which starved the model of the methodology + protocol it needs to hunt.
    # We now split content by STAGE so each prompt only carries what it needs:
    #   • Extractor gets the protocol + methodology + evidence (NOT the format).
    #   • Writer gets the finding format + the extracted findings (NOT the data).
    # That keeps each prompt rich but well within num_ctx (raised to 16k).
    finding_format = (finding_format or DEFAULT_FINDING_FORMAT)[:9600]
    finding_categories = (finding_categories or prompts.DEFAULT_CATEGORIES)[:3500]
    analysis_instructions = (
        analysis_instructions or "Follow standard evidence-based threat-hunting practice."
    )[:6500]
    tenant_context = (tenant_context or "No additional tenant context provided.")[:2500]
    if isinstance(methodology_brief, dict):
        brief_text = json.dumps(methodology_brief, ensure_ascii=False, default=str)
    else:
        brief_text = methodology_brief or "No methodology brief available."
    brief_text = brief_text[:2500]
    methodology = (methodology or "No methodology document provided.")[:10000]
    evidence_json = json.dumps(evidence_package, ensure_ascii=False, default=str)
    if len(evidence_json) > 9000:
        # Wide dataset — drop the bulky per-column top-values, keep schema/sample/stats.
        slim = dict(evidence_package)
        stats = dict(slim.get("stats", {}))
        stats.pop("top_values", None)
        slim["stats"] = stats
        evidence_json = json.dumps(slim, ensure_ascii=False, default=str)[:9000]
    trace: dict[str, Any] = {}

    # ── Stage 1: Extractor — investigate the data, extract every finding ────
    sys = prompts.ANALYST_SYSTEM.format(
        analysis_instructions=analysis_instructions,
        guardrails=prompts.GUARDRAILS,
        categories=finding_categories,
    )
    user = prompts.ANALYST_PROMPT.format(
        hunt_name=hunt_name,
        edr=edr or "unspecified",
        siem=siem or "unspecified",
        language=language or "English",
        methodology_brief=brief_text,
        methodology=methodology,
        tenant_context=tenant_context,
        dataset_name=dataset_name,
        evidence_json=evidence_json,
    )
    stage(f"Analyzing data — extracting findings (~{len(user) // 4} prompt tokens)…", 55)
    _t = time.perf_counter()
    raw = ollama.analyst(sys, user)
    trace["analyst_secs"] = round(time.perf_counter() - _t, 1)
    stage(f"Extraction finished in {trace['analyst_secs']}s (~{len(raw) // 4} tokens out)", 66)
    try:
        analyst_out = ollama.parse_json_response(raw)
    except ollama.OllamaError:
        # Don't crash the whole job on a malformed analyst response — surface it.
        analyst_out = {}
        trace["analyst_parse_error"] = True
    assessment = analyst_out.get("dataset_assessment", "") if isinstance(analyst_out, dict) else ""
    findings = analyst_out.get("findings", []) if isinstance(analyst_out, dict) else []
    trace["analyst_count"] = len(findings)

    # ── Stage 1b: Reviewer (optional false-positive reduction) ─────────────
    if run_reviewer and findings:
        stage(f"Reviewer challenging {len(findings)} finding(s)…", 74)
        r_sys = prompts.REVIEWER_SYSTEM.format(guardrails=prompts.GUARDRAILS)
        r_user = prompts.REVIEWER_PROMPT.format(
            evidence_json=evidence_json,
            findings_json=json.dumps(findings, ensure_ascii=False, default=str),
        )
        try:
            _t = time.perf_counter()
            reviewed = ollama.parse_json_response(ollama.reviewer(r_sys, r_user))
            trace["reviewer_secs"] = round(time.perf_counter() - _t, 1)
            stage(f"Reviewer finished in {trace['reviewer_secs']}s", 80)
            if isinstance(reviewed, dict):
                kept = reviewed.get("reviewed_findings", findings)
                findings = [f for f in kept if f.get("review_decision") != "reject"]
                for f in findings:  # apply reviewer adjustments
                    if f.get("adjusted_severity"):
                        f["severity"] = f["adjusted_severity"]
                    if f.get("adjusted_confidence"):
                        f["confidence"] = f["adjusted_confidence"]
        except ollama.OllamaError:
            trace["reviewer_error"] = True  # fail open: keep analyst findings
    trace["after_review_count"] = len(findings)

    # ── Stage 2: Writer — render each finding in the approved format ───────
    # Always runs (it is the second of the user's two tasks): a dedicated pass
    # that rewrites the extracted findings into the client's finding format and
    # report language. Fails open — on error we keep the extractor's findings.
    if findings:
        stage(f"Writing {len(findings)} finding(s) in the required format…", 88)
        w_sys = prompts.WRITER_SYSTEM.format(guardrails=prompts.GUARDRAILS)
        w_user = prompts.WRITER_PROMPT.format(
            language=language or "English",
            finding_format=finding_format,
            findings_json=json.dumps(findings, ensure_ascii=False, default=str),
        )
        try:
            _t = time.perf_counter()
            written = ollama.parse_json_response(ollama.qa(w_sys, w_user))
            trace["writer_secs"] = round(time.perf_counter() - _t, 1)
            stage(f"Writer finished in {trace['writer_secs']}s", 94)
            if isinstance(written, list):
                new_findings = written
            elif isinstance(written, dict) and "findings" in written:
                new_findings = written["findings"]
            else:
                new_findings = []
            # Only accept the rewrite if it preserved the finding set; otherwise
            # keep the richer extractor output rather than lose findings.
            if len(new_findings) == len(findings):
                findings = new_findings
            else:
                trace["writer_count_mismatch"] = [len(findings), len(new_findings)]
        except ollama.OllamaError:
            trace["writer_error"] = True

    # ── Hard anti-hallucination gate (code, not model) ─────────────────────
    evidence_values = _flatten_evidence_values(evidence_package)
    validated = [f for f in findings if _validate_against_evidence(f, evidence_values)]
    trace["dropped_unsupported"] = len(findings) - len(validated)

    return {
        "dataset_assessment": assessment,
        "findings": validated,
        "trace": trace,
    }
