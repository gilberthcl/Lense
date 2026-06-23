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

import ipaddress
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
        for col in df.columns:
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


# ── Behavioral signals ───────────────────────────────────────────────────────
# Frequency tables ("Python Requests appeared 4,000 times") cannot reveal a
# password spray or a volume anomaly. Those are RELATIONAL/BEHAVIORAL patterns:
# one source touching many distinct targets in a short window (fan-out), or one
# actor owning a large share of all events (concentration). The local model
# can't compute these itself (no pandas REPL), so we compute them here — this is
# what turns "29 unique user agents" into "IP X authenticated 47 distinct users
# in 6 minutes". General across any identity/auth/network telemetry.

_NULLISH = {"", "nan", "null", "none", "-", "n/a", "na"}


def _clean(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    return s[~s.str.lower().isin(_NULLISH)]


def _time_column(df: pd.DataFrame) -> str | None:
    for col in df.columns:
        if any(h in col.lower() for h in _TIME_HINTS):
            return col
    return None


def compute_fan_out(
    df: pd.DataFrame, *, max_pairs: int = 4, top: int = 8, examples: int = 5
) -> list[dict[str, Any]]:
    """
    For source→target column pairs (IP→user, IP→host, user→IP), how many DISTINCT
    targets each source touches — plus the time span over which it did so. A
    source that reaches many distinct targets in a tight window is the signature
    of password spraying / scanning / credential stuffing.
    """
    by_type = _classify_columns(list(df.columns))
    ips, users, hosts = (by_type.get(t, []) for t in ("ips", "users", "hosts"))
    time_col = _time_column(df)
    pairs: list[tuple[str, str]] = []
    for s in ips:
        pairs += [(s, t) for t in users] + [(s, t) for t in hosts]
    for s in users:
        pairs += [(s, t) for t in ips]

    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for source_col, target_col in pairs:
        if source_col == target_col or (source_col, target_col) in seen:
            continue
        seen.add((source_col, target_col))
        cols = [source_col, target_col] + ([time_col] if time_col else [])
        sub = df[cols].copy()
        sub[source_col] = sub[source_col].astype(str).str.strip()
        sub[target_col] = sub[target_col].astype(str).str.strip()
        sub = sub[
            ~sub[source_col].str.lower().isin(_NULLISH)
            & ~sub[target_col].str.lower().isin(_NULLISH)
        ]
        if sub.empty:
            continue
        rows: list[dict[str, Any]] = []
        for src, g in sub.groupby(source_col):
            distinct = int(g[target_col].nunique())
            if distinct <= 1:  # one source → one target is not fan-out
                continue
            entry: dict[str, Any] = {
                "source": str(src)[:120],
                "distinct_targets": distinct,
                "events": int(len(g)),
                "example_targets": [str(x)[:80] for x in pd.unique(g[target_col])[:examples]],
            }
            if time_col:
                ts = pd.to_datetime(g[time_col], errors="coerce", utc=True).dropna()
                if len(ts) >= 2:
                    entry["time_span_min"] = round((ts.max() - ts.min()).total_seconds() / 60.0, 1)
            rows.append(entry)
        if not rows:
            continue
        rows.sort(key=lambda r: (r["distinct_targets"], r["events"]), reverse=True)
        results.append(
            {"source_column": source_col, "target_column": target_col, "top_sources": rows[:top]}
        )
        if len(results) >= max_pairs:
            break
    return results


def compute_concentration(
    df: pd.DataFrame, *, top: int = 6, dominant_pct: float = 15.0
) -> list[dict[str, Any]]:
    """
    For each actor column (user/account/IP/host/app), each value's share of all
    events. One actor owning a large share (e.g. a service account = 60% of all
    MailItemsAccessed) is a volume-anomaly signal the frequency table hides.
    """
    by_type = _classify_columns(list(df.columns))
    total = len(df)
    if total == 0:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for etype in ("users", "ips", "hosts", "applications"):
        for col in by_type.get(etype, []):
            if col in seen:
                continue
            seen.add(col)
            s = _clean(df[col])
            if s.empty:
                continue
            vc = s.value_counts()
            top_vals = [
                {"value": str(k)[:120], "events": int(v), "pct": round(100 * v / total, 1)}
                for k, v in vc.head(top).items()
            ]
            out.append({
                "column": col,
                "distinct": int(s.nunique()),
                "dominant": bool(top_vals and top_vals[0]["pct"] >= dominant_pct),
                "top": top_vals,
            })
    return out


def classify_ips(df: pd.DataFrame, *, limit: int = 40) -> dict[str, Any]:
    """Split observed IPs into external (public/routable) vs internal (RFC1918,
    loopback, link-local). External source IPs are a prerequisite for most
    identity-attack findings — internal automation is usually baseline."""
    by_type = _classify_columns(list(df.columns))
    external: set[str] = set()
    internal: set[str] = set()
    for col in by_type.get("ips", []):
        for v in _clean(df[col]).unique():
            try:
                ip = ipaddress.ip_address(v)
            except ValueError:
                m = IPV4_RE.search(v)
                if not m:
                    continue
                try:
                    ip = ipaddress.ip_address(m.group(0))
                except ValueError:
                    continue
            (internal if (ip.is_private or ip.is_loopback or ip.is_link_local) else external).add(str(ip))
    return {
        "external_ips": sorted(external)[:limit],
        "external_ip_count": len(external),
        "internal_ip_count": len(internal),
    }


def compute_behavioral(df: pd.DataFrame) -> dict[str, Any]:
    """All behavioral signals in one block, computed defensively (a failure in
    one signal must not sink the whole evidence package)."""
    out: dict[str, Any] = {}
    for key, fn in (
        ("fan_out", compute_fan_out),
        ("concentration", compute_concentration),
        ("ip_classification", classify_ips),
    ):
        try:
            out[key] = fn(df)
        except Exception:  # noqa: BLE001 — best-effort enrichment, never fatal
            out[key] = [] if key != "ip_classification" else {}
    return out


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
        # Behavioral/relational signals — fan-out (spray/scan), concentration
        # (volume anomaly), external-vs-internal IPs. This is where spray and
        # volume-anomaly findings come from; frequency tables alone can't.
        "behavioral": compute_behavioral(df),
        "offensive_tool_hits": tool_hits,
        "suspicious_signals": suspicious,
        # A bounded verbatim sample so the model can quote real rows.
        "sample_rows": df.head(sample_rows).to_dict(orient="records"),
        "targeted_rows": targeted,
    }
