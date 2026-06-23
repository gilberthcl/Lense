"""
Threat-intel / reputation enrichment by joining a hunt's sibling datasets.

The strongest findings (e.g. "this external IP authenticating dozens of users is
flagged malicious by N vendors and is a known TOR exit node") need data that does
NOT live in the log being analyzed — it lives in a SEPARATE reputation/threat-
intel dataset the hunt also includes. The per-dataset analyzer never saw it, so
those findings were impossible.

This module:
  1. detects reputation datasets among a hunt's CSVs (by column heuristics),
  2. builds an indicator (IP / domain / hash) -> attributes index from them,
  3. enriches an evidence package's entities with the matching TI attributes.

Deterministic + evidence-only: every enriched value exists verbatim in the
reputation dataset. Tenant isolation is preserved by the caller (it only ever
passes datasets from one hunt, which belongs to one tenant).
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

# Columns that identify the indicator a reputation row is ABOUT.
_INDICATOR_KEYS = [
    "indicator", "ioc", "observable", "artifact", "entity", "ipaddress",
    "ip", "sourceip", "srcip", "address", "domain", "fqdn", "hash", "sha256",
    "md5", "sha1", "url",
]
# Columns whose presence marks a dataset as reputation/threat-intel.
_REPUTATION_HINTS = [
    "gti", "gtiscore", "score", "reputation", "verdict", "malicious",
    "maliciousvendors", "vendors", "detections", "detection", "abuseipdb",
    "abuse", "tag", "tags", "asn", "asname", "as_name", "country", "category",
    "threat", "tor", "vt", "virustotal", "mandiant", "classification",
    "confidence", "severity", "firstseen", "lastseen", "comment",
]
_NULLISH = {"", "nan", "null", "none", "-", "n/a", "na"}

_IPV4_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
_IPV6_RE = re.compile(r"^[0-9a-fA-F:]+:[0-9a-fA-F:]+$")
_HASH_RE = re.compile(r"^[a-fA-F0-9]{32}$|^[a-fA-F0-9]{40}$|^[a-fA-F0-9]{64}$")
_DOMAIN_RE = re.compile(r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")


def _norm(col: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(col).lower())


def _clean(v: Any) -> str:
    s = str(v).strip()
    return "" if s.lower() in _NULLISH else s


def _classify(value: str) -> str | None:
    v = value.strip()
    if _IPV4_RE.match(v) and all(0 <= int(o) <= 255 for o in v.split(".")):
        return "ip"
    if _IPV6_RE.match(v):
        return "ip"
    if _HASH_RE.match(v):
        return "hash"
    if _DOMAIN_RE.match(v.lower()):
        return "domain"
    return None


def _reputation_columns(columns: list[str]) -> list[str]:
    return [c for c in columns if any(h in _norm(c) for h in _REPUTATION_HINTS)]


def _indicator_column(columns: list[str]) -> str | None:
    """Best column to use as the indicator key, by hint priority order."""
    norms = {c: _norm(c) for c in columns}
    for key in _INDICATOR_KEYS:
        for c in columns:
            if norms[c] == key:           # exact match first
                return c
    for key in _INDICATOR_KEYS:
        for c in columns:
            if key in norms[c]:           # then substring
                return c
    return None


def is_reputation_dataset(columns: list[str]) -> bool:
    """A dataset is reputation/TI-like if it has an indicator key column AND at
    least two reputation-signal columns (score, vendors, tags, asn, …)."""
    if _indicator_column(columns) is None:
        return False
    return len(_reputation_columns(columns)) >= 2


def build_intel_index(df: pd.DataFrame, *, max_attrs: int = 10) -> dict[str, dict[str, Any]]:
    """Map each indicator value (lowercased) -> {indicator, type, attributes}."""
    cols = list(df.columns)
    key_col = _indicator_column(cols)
    if key_col is None:
        return {}
    attr_cols = [c for c in _reputation_columns(cols) if c != key_col][:max_attrs]
    index: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        raw = _clean(row.get(key_col, ""))
        if not raw:
            continue
        itype = _classify(raw) or "indicator"
        key = raw.lower()
        rec = index.setdefault(
            key, {"indicator": raw, "type": itype, "attributes": {}}
        )
        for c in attr_cols:
            val = _clean(row.get(c, ""))
            if not val:
                continue
            prev = rec["attributes"].get(c)
            if prev is None:
                rec["attributes"][c] = val[:200]
            elif val not in prev:                       # merge distinct values
                rec["attributes"][c] = (prev + "; " + val)[:200]
    return index


def _candidate_indicators(evidence: dict[str, Any]) -> list[str]:
    """Indicator-ish values present in an evidence package, worth a TI lookup."""
    out: list[str] = []
    ents = evidence.get("entities", {}) or {}
    for etype in ("ips", "domains", "hashes"):
        out += [str(v) for v in ents.get(etype, []) or []]
    behav = evidence.get("behavioral", {}) or {}
    out += [str(v) for v in (behav.get("ip_classification", {}) or {}).get("external_ips", []) or []]
    for pair in behav.get("fan_out", []) or []:
        for src in pair.get("top_sources", []) or []:
            out.append(str(src.get("source", "")))
    # Dedupe, drop empties.
    seen: set[str] = set()
    uniq: list[str] = []
    for v in out:
        v = v.strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            uniq.append(v)
    return uniq


def enrich_evidence(
    evidence: dict[str, Any], intel_index: dict[str, dict[str, Any]], *, max_hits: int = 15
) -> list[dict[str, Any]]:
    """TI records for the indicators that appear in this evidence package."""
    if not intel_index:
        return []
    hits: list[dict[str, Any]] = []
    for value in _candidate_indicators(evidence):
        rec = intel_index.get(value.lower())
        if rec and rec.get("attributes"):
            hits.append(rec)
            if len(hits) >= max_hits:
                break
    return hits


def intel_values(threat_intel: list[dict[str, Any]]) -> set[str]:
    """All citable verbatim strings from a threat_intel block (for the gate)."""
    out: set[str] = set()
    for rec in threat_intel or []:
        out.add(str(rec.get("indicator", "")).lower())
        for v in (rec.get("attributes") or {}).values():
            out.add(str(v).lower())
    return out
