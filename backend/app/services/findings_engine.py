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
    for hit in evidence_package.get("offensive_tool_hits", []):
        values.add(str(hit.get("value", "")).lower())
        values.add(str(hit.get("tool", "")).lower())
    for sig in evidence_package.get("suspicious_signals", []):
        values.add(str(sig.get("example", "")).lower())
    # Behavioral signals carry citable entities too (fan-out sources/targets,
    # concentration values, external IPs) — a spray finding cites these.
    behavioral = evidence_package.get("behavioral", {})
    for pair in behavioral.get("fan_out", []):
        for src in pair.get("top_sources", []):
            values.add(str(src.get("source", "")).lower())
            values.update(str(t).lower() for t in src.get("example_targets", []))
    for conc in behavioral.get("concentration", []):
        values.update(str(v.get("value", "")).lower() for v in conc.get("top", []))
    values.update(str(ip).lower() for ip in behavioral.get("ip_classification", {}).get("external_ips", []))
    # Threat-intel enrichment: indicators + their attributes are citable.
    for rec in evidence_package.get("threat_intel", []):
        values.add(str(rec.get("indicator", "")).lower())
        values.update(str(v).lower() for v in (rec.get("attributes") or {}).values())
    for row in evidence_package.get("sample_rows", []) + evidence_package.get("targeted_rows", []):
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
    dataset_focus: str | None = None,
    hunt_name: str = "Threat Hunt",
    language: str = "English",
    edr: str | None = None,
    siem: str | None = None,
    tenant_context: str | None = None,
    run_reviewer: bool = True,
    run_qa: bool = True,
    analyst_model: str | None = None,
    on_stage=None,
) -> dict[str, Any]:
    """Run the full pipeline. Returns {dataset_assessment, findings, trace}."""
    def stage(name: str, pct: int) -> None:
        if on_stage:
            on_stage(name, pct)

    # Prompt budget. Split content by STAGE so each prompt only carries what it
    # needs:
    #   • Extractor gets the protocol + methodology + evidence (NOT the format).
    #   • Writer gets the finding format + the extracted findings (NOT the data).
    # The caps below keep the worst-case extractor prompt under ~6k tokens so it
    # fits an 8k num_ctx with room for the generated findings. Crucially, the
    # bulky constant context (full methodology doc, instructions, categories) is
    # trimmed: on a 5-row CSV it otherwise dwarfs the actual evidence, sending
    # 8-12k tokens through gemma3:27b on a 32 GB box — slow, and enough to crash
    # it. The high-signal evidence (tool hits, suspicious signals, targeted rows)
    # is always preserved below; the per-dataset focus + brief carry the specific
    # query context, so the full methodology doc here is only a compact fallback.
    finding_format = (finding_format or DEFAULT_FINDING_FORMAT)[:8000]
    finding_categories = (finding_categories or prompts.DEFAULT_CATEGORIES)[:2000]
    analysis_instructions = (
        analysis_instructions or "Follow standard evidence-based threat-hunting practice."
    )[:2500]
    dataset_focus = (
        dataset_focus
        or "No specific methodology query matched this dataset by name — rely on "
        "the full methodology below."
    )[:2000]
    tenant_context = (tenant_context or "No additional tenant context provided.")[:1500]
    if isinstance(methodology_brief, dict):
        brief_text = json.dumps(methodology_brief, ensure_ascii=False, default=str)
    else:
        brief_text = methodology_brief or "No methodology brief available."
    brief_text = brief_text[:1600]
    methodology = (methodology or "No methodology document provided.")[:3500]
    evidence_json = json.dumps(evidence_package, ensure_ascii=False, default=str)
    if len(evidence_json) > 7000:
        # Wide/large dataset — shrink the bulky parts but ALWAYS keep the
        # high-signal evidence (tool hits, suspicious signals, targeted rows, the
        # entity/stat summary). Those are exactly where findings come from.
        slim = dict(evidence_package)
        stats = dict(slim.get("stats", {}))
        # Keep only the most informative top-value columns.
        tv = stats.get("top_values", {})
        if isinstance(tv, dict) and len(tv) > 12:
            stats["top_values"] = dict(list(tv.items())[:12])
        slim["stats"] = stats
        slim["sample_rows"] = slim.get("sample_rows", [])[:8]
        evidence_json = json.dumps(slim, ensure_ascii=False, default=str)
        if len(evidence_json) > 7000:  # still huge — drop top_values entirely, keep signals
            stats.pop("top_values", None)
            slim["stats"] = stats
            evidence_json = json.dumps(slim, ensure_ascii=False, default=str)[:7000]
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
        dataset_focus=dataset_focus,
        methodology_brief=brief_text,
        methodology=methodology,
        tenant_context=tenant_context,
        dataset_name=dataset_name,
        evidence_json=evidence_json,
    )
    stage(f"Analyzing data — extracting findings (~{len(user) // 4} prompt tokens)…", 55)
    _t = time.perf_counter()
    raw = ollama.analyst(sys, user, model=analyst_model)
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
