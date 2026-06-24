"""
Structured detail extraction for findings (Phase A of the correlation work).

A finding straight out of the analyst is mostly prose. To correlate findings —
merge duplicates, link shared entities across datasets, reconstruct attack
chains — the correlation phase needs each finding's facts in a STRUCTURED,
queryable form, captured at analysis time while the evidence package is still in
memory. This module derives, per finding:

  - entities        typed buckets (users/hosts/ips/domains/hashes/applications)
  - time_range      the observed activity window (from the dataset stats)
  - behavioral_ctx  the fan-out / concentration / threat-intel signals
  - evidence_rows   the verbatim rows behind the finding

and a per-DATASET entity index so correlation can ask "does this user also
appear in dataset 7?" without re-reading any CSV.

Everything is derived from values already present in the evidence package — no
new facts are invented (the anti-hallucination contract holds).
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.services import correlation

_BUCKETS = ("users", "hosts", "ips", "domains", "hashes", "applications")
_NULLISH = {"", "nan", "null", "none", "-", "n/a"}
# Map the evidence-package entity families onto our finding buckets.
_FAMILY_TO_BUCKET = {
    "users": "users", "hosts": "hosts", "ips": "ips", "domains": "domains",
    "hashes": "hashes", "applications": "applications",
}


def _typed_lookup(evidence: dict[str, Any]) -> dict[str, str]:
    """value(lowercased) -> bucket, from the dataset's typed entities."""
    typed: dict[str, str] = {}
    for family, vals in (evidence.get("entities") or {}).items():
        bucket = _FAMILY_TO_BUCKET.get(family)
        if not bucket:
            continue
        for v in vals or []:
            typed[str(v).strip().lower()] = bucket
    return typed


def extract_entities(finding: dict[str, Any], evidence: dict[str, Any]) -> dict[str, list[str]]:
    """Typed entity buckets for a single finding."""
    typed = _typed_lookup(evidence)
    buckets: dict[str, set[str]] = {b: set() for b in _BUCKETS}

    def place(value: Any, default: str | None = None) -> None:
        v = str(value).strip()
        if not v or v.lower() in _NULLISH:
            return
        bucket = typed.get(v.lower())
        if bucket:
            buckets[bucket].add(v)
            return
        ioc = correlation._classify_indicator(v)
        if ioc == "ip":
            buckets["ips"].add(v)
        elif ioc == "domain":
            buckets["domains"].add(v)
        elif ioc == "hash":
            buckets["hashes"].add(v)
        elif default:
            buckets[default].add(v)

    for u in correlation._as_str_list(finding.get("affected_users")):
        place(u, default="users")
    for a in correlation._as_str_list(finding.get("affected_assets")):
        place(a, default="hosts")
    # Scan the finding's own evidence/summary for any token that the dataset
    # already typed — this recovers entities the model cited but didn't list.
    blob = json.dumps(finding.get("evidence"), default=str, ensure_ascii=False)
    blob += " " + str(finding.get("summary") or "")
    for token in re.split(r"[\s,;|\"'\[\]{}()]+", blob):
        if token and token.lower() in typed:
            place(token)

    return {k: sorted(v) for k, v in buckets.items() if v}


def time_range(evidence: dict[str, Any]) -> dict[str, Any] | None:
    tr = (evidence.get("stats") or {}).get("time_range")
    return tr or None


def behavioral_context(evidence: dict[str, Any]) -> dict[str, Any] | None:
    """Compact slice of the behavioral + threat-intel signals worth carrying."""
    b = evidence.get("behavioral") or {}
    out: dict[str, Any] = {}
    fan = []
    for pair in (b.get("fan_out") or [])[:3]:
        fan.append({
            "source_column": pair.get("source_column"),
            "target_column": pair.get("target_column"),
            "top_sources": (pair.get("top_sources") or [])[:3],
        })
    if fan:
        out["fan_out"] = fan
    dominant = [c for c in (b.get("concentration") or []) if c.get("dominant")]
    if dominant:
        out["concentration"] = dominant[:3]
    ipc = b.get("ip_classification") or {}
    if ipc.get("external_ips") or ipc.get("external_ip_count"):
        out["ip_classification"] = ipc
    ti = evidence.get("threat_intel")
    if ti:
        out["threat_intel"] = ti[:8]
    return out or None


def evidence_rows(evidence: dict[str, Any], *, limit: int = 8) -> list[dict] | None:
    rows = (evidence.get("targeted_rows") or [])[:limit]
    if not rows:
        rows = (evidence.get("sample_rows") or [])[:limit]
    return rows or None


def build(finding: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    """All structured detail columns for one finding."""
    return {
        "entities": extract_entities(finding, evidence) or None,
        "time_range": time_range(evidence),
        "behavioral_context": behavioral_context(evidence),
        "evidence_rows": evidence_rows(evidence),
    }


def dataset_index(evidence: dict[str, Any]) -> dict[str, Any]:
    """Per-dataset index the correlation phase cross-references against."""
    return {
        "entities": evidence.get("entities") or {},
        "behavioral": behavioral_context(evidence),
        "time_range": time_range(evidence),
    }
