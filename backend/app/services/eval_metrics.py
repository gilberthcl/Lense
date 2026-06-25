"""
Golden-eval metrics — Phase 2 of per-tenant LoRA fine-tuning.

Pure scoring functions (no DB, no network) so the definition of "did the model
regress" is deterministic and unit-testable. The runner (eval_runner.py) wires
these to the real analysis pipeline and persists a baseline.

We score three things a fine-tune could quietly break:
  • recall/precision of findings vs. human-labelled expectations,
  • hallucination rate (findings citing entities absent from the evidence),
  • parse-error rate (the model failing to emit valid JSON).

A finding "matches" an expected one when the category agrees and they share at
least one cited entity — lenient on wording, strict on substance (you cited the
right host/user for the right kind of finding).
"""
from __future__ import annotations

from typing import Any

from app.services.findings_engine import (
    _flatten_evidence_values,
    _validate_against_evidence,
)


def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def _produced_entities(f: dict) -> set[str]:
    out: set[str] = set()
    for key in ("affected_assets", "affected_users"):
        for v in f.get(key) or []:
            out.add(_norm(v))
    ents = f.get("entities") or {}
    if isinstance(ents, dict):
        for vals in ents.values():
            for v in vals or []:
                out.add(_norm(v))
    return {e for e in out if e}


def _expected_entities(e: dict) -> set[str]:
    return {_norm(v) for v in (e.get("entities") or []) if _norm(v)}


def matches(expected: dict, produced: dict) -> bool:
    """A produced finding satisfies an expected one: same category and at least
    one shared cited entity. If the expected case lists no entities (a
    dataset-level expectation), category agreement alone counts."""
    if _norm(expected.get("category")) != _norm(produced.get("category")):
        return False
    exp_ents = _expected_entities(expected)
    if not exp_ents:
        return True
    return bool(exp_ents & _produced_entities(produced))


def is_hallucinated(produced: dict, evidence_values: set[str]) -> bool:
    """A produced finding is hallucinated if it cites assets/users that never
    appear in the case evidence. Reuses the production anti-hallucination gate so
    the eval measures exactly what the pipeline enforces."""
    return not _validate_against_evidence(produced, evidence_values)


def score_case(
    expected: list[dict], produced: list[dict], evidence_package: dict
) -> dict:
    """Per-case confusion counts + hallucination tally."""
    evidence_values = _flatten_evidence_values(evidence_package or {})
    used: set[int] = set()
    tp = 0
    for e in expected:
        for i, p in enumerate(produced):
            if i in used:
                continue
            if matches(e, p):
                used.add(i)
                tp += 1
                break
    fp = len(produced) - len(used)
    fn = len(expected) - tp
    hallucinated = sum(1 for p in produced if is_hallucinated(p, evidence_values))
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "n_expected": len(expected), "n_produced": len(produced),
        "hallucinated": hallucinated,
    }


def _ratio(num: int, den: int, *, empty: float = 1.0) -> float:
    return round(num / den, 4) if den else empty


def aggregate(case_scores: list[dict], *, parse_errors: int = 0) -> dict:
    """Roll per-case scores into the baseline metric block."""
    tp = sum(c["tp"] for c in case_scores)
    fp = sum(c["fp"] for c in case_scores)
    fn = sum(c["fn"] for c in case_scores)
    produced = sum(c["n_produced"] for c in case_scores)
    hallucinated = sum(c["hallucinated"] for c in case_scores)
    n_cases = len(case_scores)
    precision = _ratio(tp, tp + fp)          # nothing produced → nothing wrong
    recall = _ratio(tp, tp + fn)             # nothing expected → fully satisfied
    f1 = round(2 * precision * recall / (precision + recall), 4) if (precision + recall) else 0.0
    return {
        "cases": n_cases,
        "tp": tp, "fp": fp, "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "hallucination_rate": _ratio(hallucinated, produced, empty=0.0),
        "parse_error_rate": _ratio(parse_errors, n_cases, empty=0.0),
        "findings_produced": produced,
    }


# Which direction is "worse" for each metric — used to flag regressions when a
# future tuned model is compared against this baseline.
_HIGHER_IS_BETTER = ("precision", "recall", "f1")
_LOWER_IS_BETTER = ("hallucination_rate", "parse_error_rate")


def compare(baseline: dict, candidate: dict, *, tolerance: float = 0.02) -> dict:
    """Diff a candidate model's metrics against the baseline. Returns per-metric
    deltas and a `regressed` flag (any tracked metric worse than tolerance)."""
    deltas: dict[str, float] = {}
    regressed = False
    for m in _HIGHER_IS_BETTER:
        d = round((candidate.get(m, 0) or 0) - (baseline.get(m, 0) or 0), 4)
        deltas[m] = d
        if d < -tolerance:
            regressed = True
    for m in _LOWER_IS_BETTER:
        d = round((candidate.get(m, 0) or 0) - (baseline.get(m, 0) or 0), 4)
        deltas[m] = d
        if d > tolerance:
            regressed = True
    return {"deltas": deltas, "regressed": regressed, "tolerance": tolerance}
