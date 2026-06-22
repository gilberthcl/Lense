"""
Canonical finding categories for the Structured Threat Hunt module.

The Finding Categorization doc and the Finding Format doc shipped with slightly
different outcome lists. This module is the single source of truth that
reconciles them: the eight outcomes from the dedicated categorization document,
each with a stable `key`, bilingual labels (the operator reports in EN and ES),
a short definition, and a UI colour hint.

`key` is what the engine stores in `Finding.category` and what the UI styles by.
The human-readable categorization text remains editable in the Configuration
page; this list keeps the machine-usable contract stable.
"""
from __future__ import annotations

# Ordered most-to-least severe (drives display + the report's category ordering).
CATEGORIES: list[dict[str, str]] = [
    {
        "key": "malicious",
        "label_en": "Malicious Activity Identified",
        "label_es": "Actividad Maliciosa Identificada",
        "definition": "Confirmed malicious activity with strong evidence (e.g. ransomware artifacts, active connections to known-bad).",
        "color": "red",
    },
    {
        "key": "suspicious",
        "label_en": "Suspicious Activity Identified",
        "label_es": "Actividad Sospechosa Identificada",
        "definition": "Oddness, or bad with low confidence (e.g. low-fidelity IOC connections, keylogging registry changes without exfil).",
        "color": "amber",
    },
    {
        "key": "risky",
        "label_en": "Risky Behavior Identified",
        "label_es": "Comportamiento de Riesgo Identificado",
        "definition": "Behavior that could lead to exploitation but is not inherently suspicious (e.g. cleartext or publicly available credentials).",
        "color": "orange",
    },
    {
        "key": "policy_violation",
        "label_en": "Potential Policy Violation Identified",
        "label_es": "Posible Violación de Políticas Identificada",
        "definition": "Activity that potentially violates acceptable use or organizational policy (e.g. non-business software run across many machines).",
        "color": "blue",
    },
    {
        "key": "vulnerable_configuration",
        "label_en": "Vulnerable Configuration Identified",
        "label_es": "Configuración Vulnerable Identificada",
        "definition": "A protocol or configuration option that requires changing/disabling (e.g. SMBv1/POP enabled, a CVE or outdated software present).",
        "color": "purple",
    },
    {
        "key": "new_hunting_opportunity",
        "label_en": "New Hunting Opportunity Identified",
        "label_es": "Nueva Oportunidad de 'Hunt' Identificada",
        "definition": "A new hunting opportunity surfaced during the investigation.",
        "color": "teal",
    },
    {
        "key": "unconfirmed",
        "label_en": "Unconfirmed Activity Identified",
        "label_es": "Actividad No Confirmada Identificada",
        "definition": "Observed activity tied to IOAs that requires client follow-up to confirm acceptability (e.g. a local admin account created).",
        "color": "slate",
    },
    {
        "key": "baseline",
        "label_en": "Potential Baseline Activity Identified",
        "label_es": "Posible Actividad \"Baseline\" Identificada",
        "definition": "Optional, for initial hunts: RMM/remote-access tooling not yet confirmed acceptable by the client; add explanation to the summary.",
        "color": "cyan",
    },
]

# Accepted free-text aliases mapped to canonical keys (defensive normalization of
# model output, which may emit a label, an English phrase, or a legacy key).
_ALIASES: dict[str, str] = {
    "policy violation": "policy_violation",
    "potential policy violation": "policy_violation",
    "vulnerable config": "vulnerable_configuration",
    "vulnerable configuration": "vulnerable_configuration",
    "new hunting opportunity": "new_hunting_opportunity",
    "hunting opportunity": "new_hunting_opportunity",
    "potential baseline activity": "baseline",
    "baseline activity": "baseline",
    "informational": "unconfirmed",  # format doc's "Informational" outcome -> unconfirmed
    "no finding": "no_finding",
    "no_finding": "no_finding",
}

VALID_KEYS = {c["key"] for c in CATEGORIES} | {"no_finding"}


def normalize(value: str | None) -> str:
    """Map an arbitrary model-emitted category to a canonical key (best-effort)."""
    if not value:
        return "unconfirmed"
    raw = str(value).strip()
    low = raw.lower().replace("-", " ").replace("_", " ").strip()
    if raw in VALID_KEYS:
        return raw
    # exact label / phrase matches
    for c in CATEGORIES:
        if low == c["key"].replace("_", " ") or low in (
            c["label_en"].lower(),
            c["label_es"].lower(),
        ):
            return c["key"]
    if low in _ALIASES:
        return _ALIASES[low]
    # substring fallback (e.g. "Malicious Activity Identified on host X")
    for c in CATEGORIES:
        if c["key"].split("_")[0] in low or c["label_en"].split()[0].lower() in low:
            return c["key"]
    return "unconfirmed"
