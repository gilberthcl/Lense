"""
Training-example anonymisation (W5) — optional quality lever.

Replaces a finding's concrete entities (hosts, users, IPs, domains, hashes,
apps) with consistent placeholders (HOST_1, USER_1, IP_1, …) across ALL text of
a training example. The model then learns the *pattern* ("a host running
mimikatz → credential dumping") instead of memorising a specific hostname.

With per-client isolation this is a QUALITY lever, not a safety control (a
client's model only ever sees its own data). It also stops the model
regurgitating real entity names. Off by default; toggled in Config → AI.

Pure + tested. The exporter calls `anonymize_example`.
"""
from __future__ import annotations

import re
from typing import Any

# entity-type → placeholder prefix
_PREFIX = {
    "hosts": "HOST", "host": "HOST",
    "users": "USER", "user": "USER",
    "ips": "IP", "ip": "IP",
    "domains": "DOMAIN", "domain": "DOMAIN",
    "hashes": "HASH", "hash": "HASH",
    "applications": "APP", "apps": "APP", "application": "APP",
}
_DEFAULT_PREFIX = "ENTITY"


def _flatten(v: Any) -> list[str]:
    out: list[str] = []
    if v is None:
        return out
    if isinstance(v, dict):
        for x in v.values():
            out += _flatten(x)
    elif isinstance(v, (list, tuple, set)):
        for x in v:
            out += _flatten(x)
    else:
        s = str(v).strip()
        if s:
            out.append(s)
    return out


def build_map(finding: Any) -> dict[str, str]:
    """Map each concrete entity string → a stable placeholder. Built from the
    finding's typed entities + affected assets/users."""
    counters: dict[str, int] = {}
    mapping: dict[str, str] = {}

    def assign(value: str, prefix: str) -> None:
        v = value.strip()
        # Skip trivially short tokens — replacing "a"/"10" would corrupt text.
        if len(v) < 3 or v.lower() in mapping:
            return
        counters[prefix] = counters.get(prefix, 0) + 1
        mapping[v.lower()] = f"{prefix}_{counters[prefix]}"

    ents = getattr(finding, "entities", None)
    if isinstance(ents, dict):
        for etype, vals in ents.items():
            prefix = _PREFIX.get(str(etype).lower(), _DEFAULT_PREFIX)
            for val in _flatten(vals):
                assign(val, prefix)
    for val in _flatten(getattr(finding, "affected_assets", None)):
        assign(val, "HOST")
    for val in _flatten(getattr(finding, "affected_users", None)):
        assign(val, "USER")
    return mapping


def scrub_text(text: str, mapping: dict[str, str]) -> str:
    """Replace every mapped entity in `text` (case-insensitive, longest-first so
    overlapping names don't get partially replaced)."""
    if not text or not mapping:
        return text
    for original in sorted(mapping, key=len, reverse=True):
        text = re.sub(re.escape(original), mapping[original], text, flags=re.IGNORECASE)
    return text


def anonymize_example(example: dict, finding: Any) -> dict:
    """Return a copy of a chat example with all entity mentions in its message
    contents replaced by placeholders. Meta is left untouched (not trained on)."""
    mapping = build_map(finding)
    if not mapping:
        return example
    msgs = []
    for m in example.get("messages", []):
        if isinstance(m, dict) and isinstance(m.get("content"), str):
            msgs.append({**m, "content": scrub_text(m["content"], mapping)})
        else:
            msgs.append(m)
    return {**example, "messages": msgs, "meta": {**example.get("meta", {}), "anonymized": True}}
