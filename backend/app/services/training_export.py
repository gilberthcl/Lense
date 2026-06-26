"""
Training-set exporter — Phase 1 of per-tenant LoRA fine-tuning.

Turns a tenant's human-validated findings into supervised fine-tuning (SFT)
examples, and its rejected findings into hard-negative examples, written as
chat-format JSONL ready for MLX-LM LoRA.

This module is INFERENCE-PATH-SAFE: it never runs during analysis, only writes
files on operator request, and is strictly tenant-scoped (every query filters by
tenant_id — Critical Rule #1). It does NOT train anything; it produces the
dataset a future offline trainer would consume. See
docs/per-tenant-lora-finetuning.md.

The example shape mirrors what the analyst is actually asked to produce at
inference (prompts.ANALYST_PROMPT → a JSON object with a `findings` array), so
the learned behaviour transfers. We omit `dataset_assessment` from the target
because it is not persisted per-finding — fabricating one would violate the
evidence-only discipline this product is built on.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models import Finding

# Below this many eligible positives, a LoRA tune overfits and degrades the
# model — the exporter still writes the files (useful for inspection) but marks
# the set NOT ready for training. Tune empirically; deliberately conservative.
MIN_VALIDATED = 200

TRAINING_ROOT = Path("training")

SYSTEM_INSTRUCTION = (
    "You are an elite threat-hunting analyst. Given the evidence extracted from a "
    "single hunt dataset, produce evidence-grounded findings as a JSON object with "
    "a `findings` array. Cite only values that appear verbatim in the evidence; "
    "never invent hosts, users, IPs, commands, or hashes. If the evidence does not "
    "support a finding, return an empty findings list."
)

# Fields a positive example must carry to be worth training on. A validated
# finding missing these is too thin to teach good output.
_REQUIRED_FOR_POSITIVE = ("title", "summary", "evidence")


def _anonymize_enabled(db: Session) -> bool:
    try:
        from app.services import global_config
        return bool(global_config.get_ai(db).get("anonymize_training", False))
    except Exception:  # noqa: BLE001 — config unavailable → safe default (off)
        return False


def _prune(obj: Any) -> Any:
    """Drop None / empty values so the prompt context stays compact."""
    if isinstance(obj, dict):
        out = {k: _prune(v) for k, v in obj.items()}
        return {k: v for k, v in out.items() if v not in (None, "", [], {}, ())}
    if isinstance(obj, (list, tuple)):
        return [_prune(v) for v in obj if v not in (None, "", [], {}, ())]
    return obj


def _dataset_name(f: Finding) -> str | None:
    if f.source_dataset:
        return f.source_dataset
    ds = getattr(f, "dataset", None)
    return getattr(ds, "filename", None) if ds else None


def input_context(f: Finding) -> str:
    """The user-turn content: the evidence the analyst would have seen, rebuilt
    from the finding's persisted, citable fields (no CSV re-read needed)."""
    ctx = _prune({
        "dataset": _dataset_name(f),
        "entities": f.entities,
        "time_range": f.time_range,
        "behavioral_context": f.behavioral_context,
        "evidence": f.evidence,
        "evidence_rows": (f.evidence_rows or [])[:5],
    })
    body = json.dumps(ctx, ensure_ascii=False, default=str)
    return f"Hunt dataset evidence:\n{body}\n\nExtract evidence-grounded findings as JSON."


def finding_target(f: Finding) -> dict:
    """The assistant-turn target for a positive example: the approved finding in
    the analyst's output shape (one finding)."""
    return {
        "findings": [{
            "title": f.title,
            "category": f.category,
            "severity": f.severity,
            "confidence": f.confidence,
            "summary": f.summary,
            "evidence": f.evidence,
            "mitre": f.mitre,
            "affected_assets": f.affected_assets,
            "affected_users": f.affected_users,
            "recommendations": f.recommendations,
        }],
    }


def _from_training_hunt(f: Finding) -> bool:
    return getattr(getattr(f, "hunt", None), "kind", None) == "training"


def _meta(f: Finding, label: str, **extra: Any) -> dict:
    return {
        "finding_ref": f.finding_ref,
        "finding_id": f.id,
        "tenant_id": f.tenant_id,
        "hunt_id": f.hunt_id,
        "dataset_id": f.dataset_id,
        "category": f.category,
        "severity": f.severity,
        "label": label,
        # Gold provenance: examples from historic Training Hunts are the
        # highest-quality supervision (expert-validated end to end).
        "from_training_hunt": _from_training_hunt(f),
        **extra,
    }


def build_positive(f: Finding) -> dict:
    """A validated finding → 'given this evidence, produce this finding'."""
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": input_context(f)},
            {"role": "assistant",
             "content": json.dumps(finding_target(f), ensure_ascii=False, default=str)},
        ],
        "meta": _meta(f, "positive"),
    }


def build_negative(f: Finding) -> dict:
    """A rejected finding → 'given this evidence, the correct output is no
    finding'. The original (rejected) finding + reason are kept in meta so a
    later contrastive/DPO step can use them as the dispreferred response."""
    reason = (f.reviewer_notes or "").strip() or "Determined to be a false positive on analyst review."
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": input_context(f)},
            {"role": "assistant", "content": json.dumps({"findings": []}, ensure_ascii=False)},
        ],
        "meta": _meta(f, "negative", reason=reason, rejected_title=f.title),
    }


def _is_trainable_positive(f: Finding) -> bool:
    return all(getattr(f, k, None) not in (None, "", [], {}) for k in _REQUIRED_FOR_POSITIVE)


def training_stats(db: Session, tenant_id: int) -> dict:
    """Counts only — no files written. Drives the UI/preview and the gate."""
    findings = (
        db.query(Finding)
        .filter_by(tenant_id=tenant_id)
        .filter(Finding.merged_into_id.is_(None))
        .all()
    )
    validated = [f for f in findings if f.status == "validated"]
    rejected = [f for f in findings if f.status == "rejected"]
    eligible = [f for f in validated if _is_trainable_positive(f)]
    by_category: dict[str, int] = {}
    for f in eligible:
        by_category[f.category] = by_category.get(f.category, 0) + 1
    return {
        "tenant_id": tenant_id,
        "total_findings": len(findings),
        "validated": len(validated),
        "rejected": len(rejected),
        "eligible_positives": len(eligible),
        "thin_validated_skipped": len(validated) - len(eligible),
        "by_category": by_category,
        "min_validated": MIN_VALIDATED,
        "ready_for_training": len(eligible) >= MIN_VALIDATED,
    }


def export_tenant(
    db: Session, tenant_id: int, *, out_root: Path | None = None,
    min_validated: int = MIN_VALIDATED,
) -> dict:
    """Write the tenant's SFT + negatives JSONL and return stats incl. paths.

    Always writes (the files are useful for inspection even below the gate);
    `ready_for_training` tells the operator whether the positive count clears the
    overfit floor."""
    findings = (
        db.query(Finding)
        .filter_by(tenant_id=tenant_id)
        .filter(Finding.merged_into_id.is_(None))
        .order_by(Finding.id)
        .all()
    )
    positives = [f for f in findings if f.status == "validated" and _is_trainable_positive(f)]
    negatives = [f for f in findings if f.status == "rejected"]

    # Anonymisation (W5) — optional, toggled in Config → AI. Replaces concrete
    # entities with placeholders so the model learns patterns, not hostnames.
    anonymize = _anonymize_enabled(db)

    def _emit(f, builder) -> str:
        ex = builder(f)
        if anonymize:
            from app.services import anonymize as anon  # lazy: keep import light
            ex = anon.anonymize_example(ex, f)
        return json.dumps(ex, ensure_ascii=False)

    root = (out_root or TRAINING_ROOT) / f"tenant_{tenant_id}"
    root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sft_path = root / f"{ts}.sft.jsonl"
    neg_path = root / f"{ts}.negatives.jsonl"

    with sft_path.open("w", encoding="utf-8") as fh:
        for f in positives:
            fh.write(_emit(f, build_positive) + "\n")
    with neg_path.open("w", encoding="utf-8") as fh:
        for f in negatives:
            fh.write(_emit(f, build_negative) + "\n")

    stats = training_stats(db, tenant_id)
    stats.update({
        "min_validated": min_validated,
        "ready_for_training": len(positives) >= min_validated,
        "anonymized": anonymize,
        "written": {
            "sft_examples": len(positives),
            "negative_examples": len(negatives),
            "sft_path": str(sft_path),
            "negatives_path": str(neg_path),
        },
    })
    return stats
