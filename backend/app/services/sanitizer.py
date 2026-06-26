"""
Data Sanitizer & Anonymizer (Tools).

Takes arbitrary text (command lines, scripts, JSON, logs, notes) and anonymizes
PROPRIETARY / INTERNAL or SENSITIVE values before it's shared — while NEVER
touching public IPs or external domains.

Layers:
  • Optional decode (`decode_text`): base64 / hex / URL-encoded payloads are
    decoded first, then the decoded text is what gets sanitized.
  • AI detection (`analyze`): the model finds + classifies sensitive spans and
    flags ones it is unsure about.
  • Deterministic application (`apply`): assigns consistent placeholders, redacts
    secrets, and enforces hard rules — a public IP or external domain is never
    replaced, and a whole path / combined string is never swapped wholesale: only
    the sensitive substring inside it is. Pure + unit-tested.
"""
from __future__ import annotations

import base64
import binascii
import ipaddress
import re
from typing import Any
from urllib.parse import unquote

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

# Markers that a value is a path / combined string rather than a bare identifier.
_COMPOUND_RE = re.compile(r"[\\/]|://|\s")
# Username segment inside a typical home/profile path: \Users\jdoe, /home/jdoe.
_PATH_USER_RE = re.compile(r"(?:[\\/](?:users|home))[\\/]+([^\\/\s]+)", re.IGNORECASE)
# Host in a UNC path: \\HOST\share.
_UNC_HOST_RE = re.compile(r"\\\\([^\\/\s]+)")
# Internal-looking domain suffixes (kept deterministic — external ones excluded).
_INTERNAL_SUFFIX = (".local", ".internal", ".lan", ".corp", ".intranet", ".ad")
_TOKEN_RE = re.compile(r"[A-Za-z0-9_.\-]+")


def _is_public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return ip.is_global  # public (not RFC1918/loopback/link-local)


def _is_private_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not ip.is_global and not ip.is_loopback


def _is_external_domain(value: str) -> bool:
    v = value.strip().lower().rstrip(".")
    return any(v == d or v.endswith("." + d) for d in _EXTERNAL_DOMAINS)


def _is_internal_domain(value: str) -> bool:
    v = value.strip().lower().rstrip(".")
    return "." in v and v.endswith(_INTERNAL_SUFFIX) and not _is_external_domain(v)


def decode_text(text: str, mode: str) -> dict:
    """Decode an encoded payload before sanitizing. mode ∈ base64|hex|url|auto.
    Returns {decoded, codec, changed}. Never raises — on failure the original
    text is returned unchanged with codec=None."""
    mode = (mode or "").strip().lower()
    order = ["base64", "hex", "url"] if mode in ("", "auto") else [mode]
    for codec in order:
        try:
            if codec == "base64":
                raw = base64.b64decode(text.strip(), validate=True)
                out = raw.decode("utf-8")
            elif codec == "hex":
                out = bytes.fromhex(re.sub(r"\s+", "", text)).decode("utf-8")
            elif codec == "url":
                out = unquote(text)
            else:
                continue
        except (binascii.Error, ValueError, UnicodeDecodeError):
            continue
        # Require the decode to actually change something and yield printable text.
        if out and out != text and out.isprintable() or (out and "\n" in out and out != text):
            return {"decoded": out, "codec": codec, "changed": True}
    return {"decoded": text, "codec": None, "changed": False}


def analyze(text: str) -> list[dict]:
    """AI detection: returns the model's list of sensitive items (each may carry
    a `confidence` 0–1 and `uncertain` flag). Raises OllamaError on failure."""
    sys = prompts.SANITIZE_SYSTEM
    user = prompts.SANITIZE_PROMPT.format(text=text[:12000])
    out = ollama.parse_json_response(ollama.analyst(sys, user))
    items = out.get("items") if isinstance(out, dict) else (out if isinstance(out, list) else [])
    return [i for i in (items or []) if isinstance(i, dict) and str(i.get("value", "")).strip()]


def _is_uncertain(it: dict) -> bool:
    conf = it.get("confidence")
    if isinstance(conf, (int, float)) and conf < 0.5:
        return True
    return str(it.get("uncertain", "")).strip().lower() in ("true", "1", "yes")


def _atomize(value: str, typ: str) -> list[tuple[str, str]] | None:
    """Reduce a value to the sensitive substring(s) actually worth replacing.

    A bare identifier returns itself. A path / combined string returns only the
    internal atoms inside it (username, UNC host, private IP, internal domain) so
    the surrounding structure is preserved. Returns None when the value is clearly
    compound but no safe atom can be isolated — the caller routes it to `uncertain`
    rather than blowing away the whole string."""
    if not _COMPOUND_RE.search(value):
        return [(value, typ)]

    atoms: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(a: str, t: str) -> None:
        a = a.strip()
        if len(a) >= 3 and a.lower() not in seen:
            seen.add(a.lower())
            atoms.append((a, t))

    for m in _PATH_USER_RE.finditer(value):
        add(m.group(1), "username")
    for m in _UNC_HOST_RE.finditer(value):
        add(m.group(1), "hostname")
    for tok in _TOKEN_RE.findall(value):
        if _is_private_ip(tok):
            add(tok, "private_ip")
        elif _is_internal_domain(tok):
            add(tok, "internal_domain")
    return atoms or None


def apply(text: str, items: list[dict]) -> dict:
    """Deterministically apply the detected items. Enforces the public-IP /
    external-domain safety net and the substring-only rule regardless of what the
    model returned. Low-confidence items are surfaced for review, not applied."""
    counters: dict[str, int] = {}
    mapping: dict[str, str] = {}   # value.lower() -> placeholder (consistent)
    replacements: list[dict] = []
    kept: list[dict] = []
    uncertain: list[dict] = []

    def placeholder_for(atom: str, atyp: str, action: str) -> str | None:
        if _is_public_ip(atom):
            kept.append({"value": atom, "reason": "public IP"})
            return None
        if _is_external_domain(atom):
            kept.append({"value": atom, "reason": "external domain"})
            return None
        if action == "redact" or atyp in _REDACT_TYPES:
            return f"[REDACTED_{atyp.upper()}]"
        prefix = _PREFIX.get(atyp, "ENTITY")
        key = atom.lower()
        if key in mapping:
            return mapping[key]
        counters[prefix] = counters.get(prefix, 0) + 1
        ph = f"{prefix}_{counters[prefix]}"
        mapping[key] = ph
        return ph

    for it in items:
        value = str(it.get("value", "")).strip()
        if len(value) < 3:
            continue
        typ = str(it.get("type", "other")).lower()
        action = str(it.get("action", "anonymize")).lower()

        if _is_uncertain(it):
            uncertain.append({"value": value, "type": typ,
                              "reason": str(it.get("reason") or "model was not confident")})
            continue

        # Secrets are redacted as a whole token even though they look "compound".
        isolated: list[tuple[str, str]] | None
        if action == "redact" or typ in _REDACT_TYPES:
            isolated = [(value, typ)]
        else:
            isolated = _atomize(value, typ)
        if isolated is None:
            uncertain.append({
                "value": value, "type": typ,
                "reason": "looks like a path or combined string — only the sensitive part "
                          "should be replaced; confirm which substring",
            })
            continue

        for atom, atyp in isolated:
            ph = placeholder_for(atom, atyp, action)
            if ph is None:
                continue
            replacements.append({
                "value": atom, "placeholder": ph, "type": atyp,
                "action": "redact" if ph.startswith("[") else "anonymize",
            })

    # Replace longest-first (so overlapping names aren't partially replaced),
    # case-insensitive. De-dup by value so every occurrence maps to one placeholder.
    seen: set[str] = set()
    unique: list[dict] = []
    for r in sorted(replacements, key=lambda r: len(r["value"]), reverse=True):
        if r["value"].lower() in seen:
            continue
        seen.add(r["value"].lower())
        unique.append(r)
    sanitized = text
    for r in unique:
        sanitized = re.sub(re.escape(r["value"]), r["placeholder"], sanitized, flags=re.IGNORECASE)

    return {
        "sanitized": sanitized,
        "replacements": unique,
        "kept": kept,
        "uncertain": uncertain,
        "summary": _summary(unique, kept, uncertain),
    }


def _summary(replacements: list[dict], kept: list[dict], uncertain: list[dict]) -> dict:
    by_type: dict[str, int] = {}
    for r in replacements:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
    return {
        "replaced": len(replacements),
        "anonymized": sum(1 for r in replacements if r["action"] == "anonymize"),
        "redacted": sum(1 for r in replacements if r["action"] == "redact"),
        "kept": len(kept),
        "uncertain": len(uncertain),
        "by_type": by_type,
    }


def sanitize(text: str, decode: str | None = None) -> dict:
    """Full pipeline: optionally decode, AI-detect, then deterministically apply."""
    decoded_meta = {"codec": None, "changed": False}
    work = text
    if decode:
        d = decode_text(text, decode)
        work = d["decoded"]
        decoded_meta = {"codec": d["codec"], "changed": d["changed"]}
    result = apply(work, analyze(work))
    result["decoded"] = decoded_meta
    result["input"] = work        # what was actually sanitized (post-decode)
    return result
