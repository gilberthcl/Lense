"""
Cross-dataset entity correlation.

A hunt produces findings across many datasets. The same host, user, IP, hash,
or domain showing up in findings drawn from *different* datasets is a strong
"campaign" signal: it suggests the activity is not an isolated artifact of one
query but a thread running through the engagement.

This module is deterministic and evidence-only. It correlates **only** values
that already passed the findings pipeline's anti-hallucination gate — i.e. the
typed entities a finding affects (assets/users) and the verbatim indicators it
cites in its evidence. Nothing is invented here; we only group what exists.

Pure functions operating on plain dicts so they are trivially unit-testable
without a database. The API layer adapts ORM rows into these dicts.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

# Severity ordering used to surface the "worst" category an entity touches.
CATEGORY_RANK: dict[str, int] = {
    "malicious": 5,
    "suspicious": 4,
    "risky": 3,
    "policy_violation": 2,
    "unconfirmed": 1,
    "no_finding": 0,
}

_IPV4_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
_HASH_RE = re.compile(r"^[a-fA-F0-9]{32}$|^[a-fA-F0-9]{40}$|^[a-fA-F0-9]{64}$")
_DOMAIN_RE = re.compile(r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")

# File-ish tokens that look like domains (foo.exe, bar.dll) but are not IOCs.
# Note: ".com" is intentionally excluded — .com domains vastly outnumber COM
# executables in EDR/SIEM exports, and treating them as files would hide IOCs.
_FILE_SUFFIXES = (
    ".exe", ".dll", ".sys", ".bat", ".cmd", ".ps1", ".vbs", ".js",
    ".scr", ".msi", ".lnk", ".tmp", ".dat", ".log", ".txt", ".csv", ".json",
)


def _as_str_list(value: Any) -> list[str]:
    """Normalize a list | dict | scalar | None field into a flat list of strings."""
    out: list[str] = []
    if value is None:
        return out
    if isinstance(value, dict):
        for v in value.values():
            out.extend(_as_str_list(v))
        return out
    if isinstance(value, (list, tuple, set)):
        for v in value:
            out.extend(_as_str_list(v))
        return out
    s = str(value).strip()
    if s and s.lower() not in ("nan", "null", "none", "-", ""):
        out.append(s)
    return out


def _classify_indicator(value: str) -> str | None:
    """Type a raw evidence string as an ip/hash/domain IOC, or None if it isn't one."""
    v = value.strip()
    if _IPV4_RE.match(v):
        octets = v.split(".")
        if all(0 <= int(o) <= 255 for o in octets):
            return "ip"
        return None
    if _HASH_RE.match(v):
        return "hash"
    low = v.lower()
    if low.endswith(_FILE_SUFFIXES):
        return None
    if _DOMAIN_RE.match(low):
        return "domain"
    return None


def _evidence_indicators(evidence: Any) -> list[tuple[str, str]]:
    """Pull (type, value) IOC pairs out of a finding's evidence blob."""
    pairs: list[tuple[str, str]] = []
    for raw in _as_str_list(evidence):
        # An evidence string may itself be a row; scan whitespace/comma tokens too.
        candidates = {raw}
        candidates.update(re.split(r"[\s,;|]+", raw))
        for cand in candidates:
            etype = _classify_indicator(cand)
            if etype:
                pairs.append((etype, cand.strip()))
    return pairs


def _finding_entities(finding: dict[str, Any]) -> list[tuple[str, str]]:
    """All typed (entity_type, value) pairs a single finding contributes."""
    pairs: list[tuple[str, str]] = []
    for host in _as_str_list(finding.get("affected_assets")):
        pairs.append(("host", host))
    for user in _as_str_list(finding.get("affected_users")):
        pairs.append(("user", user))
    pairs.extend(_evidence_indicators(finding.get("evidence")))
    # Dedupe within a finding so one finding counts once per entity.
    return list(dict.fromkeys(pairs))


def gather_entities(
    findings: Iterable[dict[str, Any]],
    dataset_names: dict[int, str] | None = None,
) -> dict[tuple[str, str], dict[str, Any]]:
    """
    Build a registry keyed by (entity_type, value) of where each entity appears.

    Each record tracks the distinct datasets and findings it spans plus the
    finding categories it is associated with.
    """
    dataset_names = dataset_names or {}
    registry: dict[tuple[str, str], dict[str, Any]] = {}

    for f in findings:
        # Skip dataset-level "no_finding" rows — they carry no entities of interest.
        if f.get("category") == "no_finding":
            continue
        ds_id = f.get("dataset_id")
        for etype, value in _finding_entities(f):
            rec = registry.setdefault(
                (etype, value),
                {
                    "entity_type": etype,
                    "value": value,
                    "dataset_ids": set(),
                    "categories": set(),
                    "findings": [],
                },
            )
            if ds_id is not None:
                rec["dataset_ids"].add(ds_id)
            if f.get("category"):
                rec["categories"].add(f["category"])
            rec["findings"].append(
                {
                    "finding_id": f.get("id"),
                    "finding_ref": f.get("finding_ref"),
                    "title": f.get("title"),
                    "category": f.get("category"),
                    "dataset_id": ds_id,
                    "dataset_name": dataset_names.get(ds_id),
                }
            )
    return registry


def _finalize_record(rec: dict[str, Any], dataset_names: dict[int, str]) -> dict[str, Any]:
    dataset_ids = sorted(rec["dataset_ids"])
    categories = sorted(rec["categories"], key=lambda c: CATEGORY_RANK.get(c, 0), reverse=True)
    return {
        "entity_type": rec["entity_type"],
        "value": rec["value"],
        "dataset_count": len(dataset_ids),
        "finding_count": len(rec["findings"]),
        "datasets": [
            {"dataset_id": did, "filename": dataset_names.get(did)} for did in dataset_ids
        ],
        "categories": categories,
        "max_category": categories[0] if categories else "unconfirmed",
        "findings": rec["findings"],
    }


def _sort_key(record: dict[str, Any]) -> tuple:
    return (
        record["dataset_count"],
        record["finding_count"],
        CATEGORY_RANK.get(record["max_category"], 0),
    )


def compute_correlations(
    findings: Iterable[dict[str, Any]],
    dataset_names: dict[int, str] | None = None,
) -> dict[str, Any]:
    """
    Correlate entities across a hunt's findings.

    Returns:
      - correlations: entities spanning >= 2 distinct datasets (campaign signal),
        ranked by breadth then severity.
      - iocs: every ip/hash/domain indicator seen, with occurrence counts, for the
        report's IOC table.
      - entity_count: total distinct entities observed.
    """
    dataset_names = dataset_names or {}
    findings = list(findings)
    registry = gather_entities(findings, dataset_names)
    records = [_finalize_record(rec, dataset_names) for rec in registry.values()]

    correlations = sorted(
        (r for r in records if r["dataset_count"] >= 2),
        key=_sort_key,
        reverse=True,
    )
    iocs = sorted(
        (r for r in records if r["entity_type"] in ("ip", "hash", "domain")),
        key=lambda r: (r["finding_count"], r["dataset_count"]),
        reverse=True,
    )
    return {
        "entity_count": len(records),
        "correlations": correlations,
        "iocs": iocs,
    }
