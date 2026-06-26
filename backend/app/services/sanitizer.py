"""
Data Sanitizer & Anonymizer (Tools).

Takes arbitrary text (command lines, scripts, JSON, logs, notes) and anonymizes
PROPRIETARY / INTERNAL or SENSITIVE values before it's shared — while NEVER
touching public IPs or external domains.

Two layers:
  • AI detection (`analyze`): the model finds + classifies sensitive spans.
  • Deterministic application (`apply`): assigns consistent placeholders, redacts
    secrets, and enforces a HARD safety net — a public IP or known external domain
    is never replaced even if the model lists it. Pure + unit-tested.
"""
from __future__ import annotations

import ipaddress
import re
from typing import Any

from app.services import ollama_client as ollama
from app.services import prompts

# Typed placeholders for anonymized (kept-structure) entities.
_PREFIX = {
    "username": "USER", "hostname": "HOST", "internal_domain": "DOMAIN",
    "email": "EMAIL", "private_ip": "IP", "path": "PATH", "url": "URL",
}
_REDACT_TYPES = {"secret", "token", "password", "key"}

# A small allowlist of public domains we refuse to anonymize even if the model
# misclassifies them (defence in depth — the prompt already excludes these).
_EXTERNAL_DOMAINS = {
    "google.com", "microsoft.com", "github.com", "amazonaws.com", "cloudflare.com",
    "apple.com", "windows.net", "office.com", "office365.com", "live.com",
    "azure.com", "googleapis.com", "gstatic.com", "akamai.net", "digicert.com",
}


def _is_public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return ip.is_global  # public (not RFC1918/loopback/link-local)


def _is_external_domain(value: str) -> bool:
    v = value.strip().lower().rstrip(".")
    return any(v == d or v.endswith("." + d) for d in _EXTERNAL_DOMAINS)


def analyze(text: str) -> list[dict]:
    """AI detection: returns the model's list of sensitive items. Raises
    OllamaError on transport failure."""
    sys = prompts.SANITIZE_SYSTEM
    user = prompts.SANITIZE_PROMPT.format(text=text[:12000])
    out = ollama.parse_json_response(ollama.analyst(sys, user))
    items = out.get("items") if isinstance(out, dict) else (out if isinstance(out, list) else [])
    return [i for i in (items or []) if isinstance(i, dict) and str(i.get("value", "")).strip()]


def apply(text: str, items: list[dict]) -> dict:
    """Deterministically apply the detected items. Enforces the public-IP /
    external-domain safety net regardless of what the model returned."""
    counters: dict[str, int] = {}
    mapping: dict[str, str] = {}   # value.lower() -> placeholder (consistent)
    replacements: list[dict] = []
    kept: list[dict] = []

    for it in items:
        value = str(it.get("value", "")).strip()
        if len(value) < 3:
            continue
        typ = str(it.get("type", "other")).lower()
        action = str(it.get("action", "anonymize")).lower()

        # HARD safety net — never replace these.
        if _is_public_ip(value):
            kept.append({"value": value, "reason": "public IP"})
            continue
        if _is_external_domain(value):
            kept.append({"value": value, "reason": "external domain"})
            continue

        if action == "redact" or typ in _REDACT_TYPES:
            placeholder = f"[REDACTED_{typ.upper()}]"
        else:
            prefix = _PREFIX.get(typ, "ENTITY")
            key = value.lower()
            if key in mapping:
                placeholder = mapping[key]
            else:
                counters[prefix] = counters.get(prefix, 0) + 1
                placeholder = f"{prefix}_{counters[prefix]}"
                mapping[key] = placeholder
        replacements.append({"value": value, "placeholder": placeholder,
                             "type": typ, "action": "redact" if placeholder.startswith("[") else "anonymize"})

    # Replace longest-first (so overlapping names aren't partially replaced),
    # case-insensitive. De-dup by value to avoid redundant passes.
    seen: set[str] = set()
    unique = []
    for r in sorted(replacements, key=lambda r: len(r["value"]), reverse=True):
        if r["value"].lower() in seen:
            continue
        seen.add(r["value"].lower())
        unique.append(r)
    sanitized = text
    for r in unique:
        sanitized = re.sub(re.escape(r["value"]), r["placeholder"], sanitized, flags=re.IGNORECASE)

    return {"sanitized": sanitized, "replacements": unique, "kept": kept}


def sanitize(text: str) -> dict:
    """Full pipeline: AI-detect then deterministically apply."""
    return apply(text, analyze(text))
