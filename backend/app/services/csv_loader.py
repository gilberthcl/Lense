"""
CSV ingestion + evidence-package construction.

The model never sees raw files. It sees a structured *evidence package*:
schema, statistics, scanned indicators, and extracted entities computed
deterministically here. This is the anti-hallucination backbone AND the model's
"eyes" on the data: per the Universal Threat Hunter guide, an analyst that cannot
read the data cannot write a finding. We can't give a local model a pandas REPL,
so instead we pre-compute — deterministically — everything the guide's pandas
steps (value_counts, nunique, time ranges, offensive-tool scan, suspicious-row
extraction) would produce, and hand that to the model as evidence.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

# Heuristic column-name patterns for entity extraction across EDR/SIEM exports.
# Order matters: more-specific types (useragents, applications…) are matched
# BEFORE the generic ones so e.g. "UserAgent" is not miscounted as a user (its
# name contains the substring "user").
ENTITY_PATTERNS: dict[str, list[str]] = {
    "useragents": ["useragent", "user_agent"],
    "applications": ["application", "appdisplayname", "appid", "clientapp"],
    "hashes": ["hash", "sha256", "sha1", "md5", "filehash"],
    "results": ["result", "status", "action", "outcome", "errorcode", "conditionalaccess"],
    "commands": ["command", "commandline", "cmdline", "script", "scriptblock"],
    "processes": ["process", "image", "filename", "filepath", "exe"],
    "domains": ["domain", "fqdn", "url", "dns", "host_referer"],
    "ips": ["ipaddr", "src_ip", "dst_ip", "remoteaddress", "localaddress", "ipaddress", "ip"],
    "hosts": ["hostname", "computer", "device", "endpoint", "machine", "host"],
    "users": ["username", "useraccount", "samaccount", "upn", "principal", "account", "user"],
}

# Column families used to focus the offensive-tool / suspicious-pattern scan.
_SCAN_COLS = [
    "process", "image", "filename", "filepath", "exe", "command", "commandline",
    "cmdline", "script", "scriptblock", "parent", "useragent", "user_agent",
    "application", "appdisplayname", "clientapp", "name", "title", "description",
    "path", "url",
]

# Known offensive tools (Universal guide §5.3). Any confirmed appearance is a
# high-priority indicator. Matched case-insensitively on word-ish boundaries.
OFFENSIVE_TOOLS: list[str] = [
    # OAuth / identity abuse
    "ropci", "teamfiltration", "aadinternals", "o365spray", "msolspray",
    "roadrecon", "roadtools",
    # Credential access
    "mimikatz", "lazagne", "procdump", "secretsdump", "rubeus",
    # Lateral movement
    "psexec.py", "wmiexec", "smbexec", "crackmapexec", "bloodhound", "sharphound",
    "impacket",
    # C2 frameworks
    "cobalt strike", "cobaltstrike", "beacon", "brute ratel", "bruteratel",
    "sliver", "metasploit", "meterpreter", "empire", "havoc",
    # Recon
    "adfind", "powerview", "ldapdomaindump", "adrecon", "pingcastle",
    # Exfiltration
    "rclone", "megasync", "cloudsponge",
    # Web shells
    "china chopper", "antsword",
]

IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_TIME_HINTS = ["time", "timestamp", "date", "event_time", "created", "fecha", "hora"]

# Suspicious-pattern heuristics (signals, NOT findings — the analyst confirms).
_SUSPICIOUS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("exec_from_temp_or_profile",
     re.compile(r"(?:\\temp\\|\\appdata\\|\\users\\public|%temp%|/tmp/|\\downloads\\)", re.I)),
    ("encoded_powershell",
     re.compile(r"(?:-enc\b|-encodedcommand|frombase64string|-e\s+[A-Za-z0-9+/]{40,})", re.I)),
    ("ropc_grant_type_password",
     re.compile(r"grant_type[=:\s\"']+password", re.I)),
    ("scripting_user_agent",
     re.compile(r"(?:python-requests|curl/|powershell|httpclient|axios|go-http-client|okhttp)", re.I)),
    ("obfuscation_concat",
     re.compile(r"(?:\^|`|\"\s*\+\s*\"|char\(\d+\))", re.I)),
]


def load_csv(path: str | Path, max_bytes: int) -> pd.DataFrame:
    p = Path(path)
    size = p.stat().st_size
    if size > max_bytes:
        raise ValueError(f"Dataset {p.name} is {size} bytes, exceeds {max_bytes} cap")
    # Robust read: tolerate encoding quirks common in EDR/SIEM exports.
    return pd.read_csv(p, dtype=str, keep_default_na=False, encoding_errors="replace")


def _classify_columns(columns: list[str]) -> dict[str, list[str]]:
    """Assign each column to AT MOST ONE entity type, by pattern priority order,
    so a column like 'UserAgent' lands in useragents, not users."""
    assigned: dict[str, str] = {}
    for etype, keywords in ENTITY_PATTERNS.items():
        for col in columns:
            if col in assigned:
                continue
            norm = re.sub(r"[^a-z0-9]", "", col.lower())
            if any(kw in norm for kw in keywords):
                assigned[col] = etype
    out: dict[str, list[str]] = {}
    for col, etype in assigned.items():
        out.setdefault(etype, []).append(col)
    return out


def _match_columns(columns: list[str], keywords: list[str]) -> list[str]:
    """Columns whose normalized name contains any keyword (non-exclusive — used
    for the text-scan families, where overlap is fine)."""
    out = []
    for col in columns:
        norm = re.sub(r"[^a-z0-9]", "", col.lower())
        if any(kw in norm for kw in keywords):
            out.append(col)
    return out


def _scan_columns(df: pd.DataFrame) -> list[str]:
    """Columns likely to carry process/command/UA/app text worth scanning."""
    cols = _match_columns(list(df.columns), _SCAN_COLS)
    # Fall back to all object columns if nothing matched by name.
    return cols or list(df.columns)


def extract_entities(df: pd.DataFrame, max_per_type: int = 80) -> dict[str, list[str]]:
    """Pull distinct entity values by column-name heuristics. Verbatim only."""
    by_type = _classify_columns(list(df.columns))
    entities: dict[str, list[str]] = {}
    for etype, cols in by_type.items():
        values: set[str] = set()
        for col in cols:
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


def _time_range(df: pd.DataFrame) -> dict[str, str] | None:
    for col in df.columns:
        norm = col.lower()
        if any(h in norm for h in _TIME_HINTS):
            series = df[col].astype(str).str.strip()
            series = series[series != ""]
            if not series.empty:
                return {"column": col, "min": str(series.min()), "max": str(series.max())}
    return None


def compute_stats(df: pd.DataFrame, top_n: int = 15) -> dict[str, Any]:
    """Deterministic statistics the model may reference as evidence."""
    columns_meta = []
    for c in df.columns:
        s = df[c].astype(str).str.strip()
        columns_meta.append({
            "name": c,
            "non_empty": int((s != "").sum()),
            "unique": int(s[s != ""].nunique()),
        })
    value_counts: dict[str, list[dict[str, Any]]] = {}
    # Summarize more columns + deeper than before — this is the model's view of
    # the distributions it would otherwise compute with value_counts().
    for col in list(df.columns)[:40]:
        series = df[col].astype(str).str.strip()
        series = series[series != ""]
        nunique = series.nunique()
        if 0 < nunique <= max(top_n * 6, 120):
            top = series.value_counts().head(top_n)
            value_counts[col] = [{"value": str(k)[:120], "count": int(v)} for k, v in top.items()]
    # Cardinality of the key identity fields (guide Step 2).
    by_type = _classify_columns(list(df.columns))
    entity_counts: dict[str, int] = {}
    for etype in ("users", "hosts", "ips"):
        cols = by_type.get(etype, [])
        if cols:
            vals = pd.unique(pd.concat([df[c].astype(str).str.strip() for c in cols]))
            entity_counts[etype] = int(len([v for v in vals if v and v.lower() not in ("nan", "null", "-", "")]))
    return {
        "row_count": int(len(df)),
        "col_count": int(len(df.columns)),
        "columns": columns_meta,
        "time_range": _time_range(df),
        "entity_counts": entity_counts,
        "top_values": value_counts,
    }


def scan_offensive_tools(df: pd.DataFrame, max_hits: int = 25) -> list[dict[str, Any]]:
    """Scan process/command/UA/app columns for known offensive tools (§5.3)."""
    hits: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    pattern = re.compile(
        "|".join(r"\b" + re.escape(t).replace(r"\ ", r"\s+") + r"\b" for t in OFFENSIVE_TOOLS),
        re.I,
    )
    for col in _scan_columns(df):
        series = df[col].astype(str)
        mask = series.str.contains(pattern, na=False)
        if not mask.any():
            continue
        for idx, val in series[mask].items():
            m = pattern.search(val)
            tool = (m.group(0).lower() if m else "").strip()
            key = (tool, str(val)[:120])
            if key in seen:
                continue
            seen.add(key)
            hits.append({
                "tool": tool, "column": col,
                "value": str(val)[:200], "row_index": int(idx),
            })
            if len(hits) >= max_hits:
                return hits
    return hits


def scan_suspicious(df: pd.DataFrame, max_hits: int = 30) -> list[dict[str, Any]]:
    """Heuristic suspicious-pattern signals (temp-path exec, encoded PS, ROPC…)."""
    signals: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for col in _scan_columns(df):
        series = df[col].astype(str)
        for sig_name, rx in _SUSPICIOUS_PATTERNS:
            mask = series.str.contains(rx, na=False)
            n = int(mask.sum())
            if n == 0:
                continue
            example = str(series[mask].iloc[0])[:200]
            key = (sig_name, hash(col) & 0xFFFF)
            if key in seen:
                continue
            seen.add(key)
            signals.append({
                "signal": sig_name, "column": col, "count": n, "example": example,
            })
            if len(signals) >= max_hits:
                return signals
    return signals


def _rows_for_indices(df: pd.DataFrame, indices: list[int], limit: int) -> list[dict]:
    uniq: list[int] = []
    for i in indices:
        if i not in uniq:
            uniq.append(i)
        if len(uniq) >= limit:
            break
    if not uniq:
        return []
    return df.loc[uniq].to_dict(orient="records")


def build_evidence_package(df: pd.DataFrame, *, sample_rows: int = 20) -> dict[str, Any]:
    """Full deterministic package handed to the Analyst agent."""
    tool_hits = scan_offensive_tools(df)
    suspicious = scan_suspicious(df)
    # Targeted sample: the actual rows behind tool hits — the model must be able
    # to quote real values for any high-priority indicator it reports.
    targeted = _rows_for_indices(df, [h["row_index"] for h in tool_hits], limit=10)
    return {
        "schema": list(df.columns),
        "stats": compute_stats(df),
        "entities": extract_entities(df),
        "offensive_tool_hits": tool_hits,
        "suspicious_signals": suspicious,
        # A bounded verbatim sample so the model can quote real rows.
        "sample_rows": df.head(sample_rows).to_dict(orient="records"),
        "targeted_rows": targeted,
    }
