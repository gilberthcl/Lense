"""
Correlation engine — Phase B (deterministic) + Phase C (LLM reasoning).

The correlation PHASE runs after all datasets are analyzed. It does not create
new findings from raw data; it works over the findings already produced (and
their Phase-A structured detail) to:

  • link findings that share entities (same user/host/ip/…),
  • see where each finding's entities ALSO appear across other datasets,
  • order everything on a timeline,
  • cluster linked findings into candidate attack-chains (incidents).

This file holds the DETERMINISTIC layer (Phase B): a pure, unit-testable
function that turns a list of finding dicts + the per-dataset entity indexes
into a structured "correlation package". The LLM pass (Phase C) consumes that
package to merge duplicates, enrich findings, and name the attack chains.

Pure functions over plain dicts (the API/runner adapts ORM rows), mirroring
correlation.py.
"""
from __future__ import annotations

from typing import Any, Iterable

# Entity buckets carried on each finding (Phase A `entities` column).
_BUCKETS = ("users", "hosts", "ips", "domains", "hashes", "applications")


def _entity_pairs(finding: dict[str, Any]) -> set[tuple[str, str]]:
    """(bucket, lowercased value) pairs a finding references."""
    out: set[tuple[str, str]] = set()
    for bucket, vals in (finding.get("entities") or {}).items():
        if bucket not in _BUCKETS:
            continue
        for v in vals or []:
            s = str(v).strip()
            if s:
                out.add((bucket, s.lower()))
    return out


def shared_entities(a: dict[str, Any], b: dict[str, Any]) -> list[dict[str, str]]:
    """Entities referenced by BOTH findings (the reason to consider linking)."""
    common = _entity_pairs(a) & _entity_pairs(b)
    return [{"type": t, "value": v} for t, v in sorted(common)]


def build_links(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pairwise finding links wherever they share at least one entity."""
    links: list[dict[str, Any]] = []
    for i in range(len(findings)):
        for j in range(i + 1, len(findings)):
            shared = shared_entities(findings[i], findings[j])
            if shared:
                links.append({
                    "a": findings[i].get("id"),
                    "b": findings[j].get("id"),
                    "a_ref": findings[i].get("finding_ref"),
                    "b_ref": findings[j].get("finding_ref"),
                    "shared": shared,
                    "weight": len(shared),
                })
    return links


def cross_dataset_presence(
    findings: list[dict[str, Any]], dataset_index: dict[int, dict[str, Any]]
) -> dict[int, list[dict[str, Any]]]:
    """
    For each finding, which OTHER datasets contain its entities — the signal for
    "is this activity isolated to its dataset, or part of something broader?".
    """
    value_to_datasets: dict[str, set[int]] = {}
    for did, idx in (dataset_index or {}).items():
        for vals in (idx.get("entities") or {}).values():
            for v in vals or []:
                value_to_datasets.setdefault(str(v).strip().lower(), set()).add(did)

    out: dict[int, list[dict[str, Any]]] = {}
    for f in findings:
        hits: list[dict[str, Any]] = []
        for bucket, vals in (f.get("entities") or {}).items():
            for v in vals or []:
                others = sorted(
                    d for d in value_to_datasets.get(str(v).strip().lower(), set())
                    if d != f.get("dataset_id")
                )
                if others:
                    hits.append({"entity": v, "type": bucket, "also_in_datasets": others})
        if hits:
            out[f["id"]] = hits
    return out


def _start_key(finding: dict[str, Any]) -> str:
    tr = finding.get("time_range") or {}
    return str(tr.get("start") or tr.get("min") or tr.get("first") or "")


def timeline(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Findings ordered by observed start time (blank times sort last)."""
    ordered = sorted(findings, key=lambda f: (_start_key(f) == "", _start_key(f)))
    return [{
        "finding_id": f.get("id"),
        "finding_ref": f.get("finding_ref"),
        "title": f.get("title"),
        "category": f.get("category"),
        "start": (f.get("time_range") or {}).get("start"),
        "dataset_id": f.get("dataset_id"),
    } for f in ordered]


def clusters(findings: list[dict[str, Any]], links: list[dict[str, Any]]) -> list[list[int]]:
    """Connected components over the link graph — candidate attack-chains.

    Only components with >= 2 findings are returned (a lone finding is not a
    chain). Sorted largest-first so the strongest campaigns surface on top.
    """
    parent = {f["id"]: f["id"] for f in findings}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for link in links:
        a, b = link["a"], link["b"]
        if a in parent and b in parent:
            parent[find(a)] = find(b)

    comps: dict[int, list[int]] = {}
    for f in findings:
        comps.setdefault(find(f["id"]), []).append(f["id"])
    return sorted((sorted(v) for v in comps.values() if len(v) >= 2),
                  key=len, reverse=True)


def build_correlation_package(
    findings: Iterable[dict[str, Any]],
    dataset_index: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The full deterministic correlation package fed to the LLM pass."""
    findings = [f for f in findings if f.get("id") is not None]
    dataset_index = dataset_index or {}
    links = build_links(findings)
    return {
        "finding_count": len(findings),
        "links": links,
        "clusters": clusters(findings, links),
        "cross_dataset": cross_dataset_presence(findings, dataset_index),
        "timeline": timeline(findings),
    }
