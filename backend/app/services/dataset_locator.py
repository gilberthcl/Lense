"""
Find which dataset an offline finding came from, when the analyst doesn't know.

Strategy (per the analyst's spec):
  1. Rank datasets by DESCRIPTIVE FILENAME similarity first — a dataset called
     "5-ropc-signins.csv" is a strong hint for a ROPC sign-in finding — then by
     entity overlap (entities the finding mentions that appear in the dataset).
  2. Walk the ranked candidates and ask the model to CONFIRM whether the finding
     is observable in each, stopping at the first confident hit.
  3. Once found, the caller runs the SAME learning analysis as a known dataset.

`rank_datasets` is pure and unit-tested; `confirm_in_dataset` / `locate` are the
model/DB-backed steps.
"""
from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Dataset
from app.services import csv_loader, dataset_report, methodology_parser
from app.services import ollama_client as ollama
from app.services import prompts

# Filename match dominates (descriptive names are the strongest hint), entity
# overlap breaks ties / surfaces datasets whose name doesn't obviously match.
_NAME_WEIGHT = 2.0


def _tokens(text: str) -> set[str]:
    return methodology_parser._tokens(text or "")


def rank_datasets(finding_text: str, datasets: list[dict]) -> list[dict]:
    """Order candidate datasets best-first for a described finding.

    `datasets`: [{"id", "filename", "entities": set[str]|list[str]}]. Returns the
    same dicts with a "score" added, sorted descending. Pure."""
    ftok = _tokens(finding_text)
    flow = (finding_text or "").lower()
    ranked = []
    for d in datasets:
        name_tok = _tokens(d.get("filename", ""))
        name_overlap = len(ftok & name_tok) / max(1, len(name_tok)) if name_tok else 0.0
        ents = {str(e).lower() for e in (d.get("entities") or []) if e}
        ent_hits = sum(1 for e in ents if e and e in flow)
        ent_score = ent_hits / max(1, len(ents)) if ents else 0.0
        score = name_overlap * _NAME_WEIGHT + ent_score
        ranked.append({**d, "score": round(score, 4), "name_overlap": round(name_overlap, 4),
                       "entity_hits": ent_hits})
    ranked.sort(key=lambda d: (d["score"], d["entity_hits"]), reverse=True)
    return ranked


def _dataset_entities(ds: Dataset) -> set[str]:
    """Entities known for a dataset without re-reading the CSV: prefer the
    persisted analysis report's pool, fall back to the entity_index."""
    pool = dataset_report.entity_pool(getattr(ds, "analysis_notes", None))
    if pool:
        return pool
    idx = getattr(ds, "entity_index", None) or {}
    out: set[str] = set()
    if isinstance(idx, dict):
        for v in idx.values():
            if isinstance(v, (list, tuple)):
                out.update(str(x).lower() for x in v)
    return out


def candidate_meta(datasets: list[Dataset]) -> list[dict]:
    """Build the rank() input from ORM datasets (id, filename, known entities)."""
    return [
        {"id": ds.id, "filename": ds.filename, "entities": _dataset_entities(ds)}
        for ds in datasets
    ]


def confirm_in_dataset(
    dataset_name: str, evidence: dict, finding_text: str, model: str | None = None
) -> dict:
    """Ask the model whether the described finding is observable in this dataset.
    Returns {present: bool, confidence, rationale}; {} on a transport/parse error
    (treated as 'not confirmed' by the caller)."""
    import json

    sys = prompts.LOCATE_SYSTEM.format(guardrails=prompts.GUARDRAILS)
    user = prompts.LOCATE_PROMPT.format(
        dataset_name=dataset_name,
        evidence_json=json.dumps(evidence, ensure_ascii=False, default=str)[:6000],
        description=(finding_text or "").strip()[:2000],
    )
    try:
        out = ollama.parse_json_response(ollama.analyst(sys, user, model=model))
    except ollama.OllamaError:
        return {}
    return out if isinstance(out, dict) else {}


# Don't model-check more than this many datasets in one locate (bounds runtime on
# a local model). The deterministic rank puts the relevant datasets first.
_HARD_CHECK_CAP = 20


def locate_matches(
    db: Session,
    tenant_id: int,
    hunt_id: int,
    finding_text: str,
    *,
    model: str | None = None,
    on_progress: Callable[[str, int], None] | None = None,
) -> dict[str, Any]:
    """Scan the hunt's datasets (descriptive-name priority) and collect EVERY
    dataset that confirms the finding — a finding can span several datasets and
    then needs correlation. Returns {matches: [{dataset, evidence, confidence,
    rationale}], ranked, checked, note}.

    Efficiency: once at least one match is found, only datasets with a deterministic
    signal (name/entity overlap) are model-checked; with zero matches yet we keep
    scanning everything so a poorly-named source is still found. Bounded by a hard
    check cap."""
    def progress(msg: str, pct: int) -> None:
        if on_progress:
            on_progress(msg, pct)

    datasets = db.query(Dataset).filter_by(tenant_id=tenant_id, hunt_id=hunt_id).all()
    if not datasets:
        return {"matches": [], "ranked": [], "checked": 0,
                "note": "This hunt has no datasets to scan."}

    by_id = {ds.id: ds for ds in datasets}
    ranked = rank_datasets(finding_text, candidate_meta(datasets))
    progress(f"Ranked {len(ranked)} datasets by name + entities; scanning…", 20)

    matches: list[dict] = []
    checked = 0
    total = len(ranked)
    for i, cand in enumerate(ranked):
        has_signal = cand["name_overlap"] > 0 or cand["entity_hits"] > 0
        # Once we have a hit, spend model calls only on candidates with some signal.
        if matches and not has_signal:
            continue
        if checked >= _HARD_CHECK_CAP:
            break
        ds = by_id[cand["id"]]
        pct = 20 + int(60 * (i / max(1, total)))
        progress(f"Checking {ds.filename} ({i + 1}/{total})…", pct)
        try:
            df = csv_loader.load_csv(ds.file_path, settings.max_upload_bytes)
            evidence = csv_loader.build_evidence_package(df, sample_rows=12)
        except Exception:  # noqa: BLE001 — unreadable file, skip this candidate
            continue
        checked += 1
        verdict = confirm_in_dataset(ds.filename, evidence, finding_text, model=model)
        if verdict.get("present") and str(verdict.get("confidence", "")).lower() in ("medium", "high"):
            matches.append({"dataset": ds, "evidence": evidence,
                            "confidence": verdict.get("confidence"),
                            "rationale": verdict.get("rationale")})
            progress(f"Found in {ds.filename} ({verdict.get('confidence')}). Matches: {len(matches)}.", min(84, pct + 5))

    note = None if matches else "Scanned the datasets; none clearly contained the finding."
    return {"matches": matches, "ranked": ranked, "checked": checked, "note": note}
