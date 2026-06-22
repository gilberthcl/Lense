"""
CSV ingestion + evidence-package construction.

The model never sees raw files. It sees a structured *evidence package*:
schema, statistics, and extracted entities computed deterministically here.
This is the anti-hallucination backbone — every host/user/IP/command the model
is allowed to cite originates from this package, not from its imagination.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

# Heuristic column-name patterns for entity extraction across EDR/SIEM exports
ENTITY_PATTERNS: dict[str, list[str]] = {
    "hosts": ["host", "hostname", "computer", "device", "endpoint", "machine"],
    "users": ["user", "username", "account", "useraccount", "upn", "samaccount"],
    "ips": ["ip", "ipaddr", "src_ip", "dst_ip", "remoteaddress", "localaddress"],
    "processes": ["process", "image", "filename", "filepath", "exe"],
    "commands": ["command", "commandline", "cmdline", "script", "scriptblock"],
    "hashes": ["hash", "sha256", "sha1", "md5", "filehash"],
    "domains": ["domain", "fqdn", "url", "dns", "host_referer"],
}

IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def load_csv(path: str | Path, max_bytes: int) -> pd.DataFrame:
    p = Path(path)
    size = p.stat().st_size
    if size > max_bytes:
        raise ValueError(f"Dataset {p.name} is {size} bytes, exceeds {max_bytes} cap")
    # Robust read: tolerate encoding quirks common in EDR/SIEM exports.
    return pd.read_csv(p, dtype=str, keep_default_na=False, encoding_errors="replace")


def _match_columns(columns: list[str], keywords: list[str]) -> list[str]:
    out = []
    for col in columns:
        norm = re.sub(r"[^a-z0-9]", "", col.lower())
        if any(kw in norm for kw in keywords):
            out.append(col)
    return out


def extract_entities(df: pd.DataFrame, max_per_type: int = 50) -> dict[str, list[str]]:
    """Pull distinct entity values by column-name heuristics. Verbatim only."""
    columns = list(df.columns)
    entities: dict[str, list[str]] = {}
    for etype, keywords in ENTITY_PATTERNS.items():
        values: set[str] = set()
        for col in _match_columns(columns, keywords):
            for v in df[col].dropna().astype(str):
                v = v.strip()
                if v and v.lower() not in ("nan", "null", "-", ""):
                    values.add(v)
        if values:
            entities[etype] = sorted(values)[:max_per_type]
    # IP fallback: regex-scan the whole frame if no IP column matched
    if "ips" not in entities:
        found = set()
        for col in columns:
            for v in df[col].astype(str):
                found.update(IPV4_RE.findall(v))
        if found:
            entities["ips"] = sorted(found)[:max_per_type]
    return entities


def compute_stats(df: pd.DataFrame, top_n: int = 15) -> dict[str, Any]:
    """Deterministic statistics the model may reference as evidence."""
    columns_meta = [{"name": c, "non_empty": int((df[c].astype(str).str.strip() != "").sum())}
                    for c in df.columns]
    value_counts: dict[str, list[dict[str, Any]]] = {}
    for col in df.columns:
        series = df[col].astype(str).str.strip()
        series = series[series != ""]
        nunique = series.nunique()
        # Only summarize categorical-ish columns to keep the package compact.
        if 0 < nunique <= max(top_n * 4, 200):
            top = series.value_counts().head(top_n)
            value_counts[col] = [{"value": k, "count": int(v)} for k, v in top.items()]
    return {
        "row_count": int(len(df)),
        "col_count": int(len(df.columns)),
        "columns": columns_meta,
        "top_values": value_counts,
    }


def build_evidence_package(df: pd.DataFrame, *, sample_rows: int = 25) -> dict[str, Any]:
    """Full deterministic package handed to the Analyst agent."""
    return {
        "schema": list(df.columns),
        "stats": compute_stats(df),
        "entities": extract_entities(df),
        # A bounded verbatim sample so the model can quote real rows.
        "sample_rows": df.head(sample_rows).to_dict(orient="records"),
    }
