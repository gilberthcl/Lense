"""
Curated, vetted model catalog for the in-app model manager.

Only models we've checked for provenance live here — this IS the safe-handling
control: the operator installs from a known-good list, not arbitrary repos.
Everything is GGUF (a data-only format that can't carry executable code, unlike
pickle / trust_remote_code safetensors), pulled via Ollama and run locally.

A custom install path still exists for power users, but it runs through the same
compliance gate (model_compliance) and a clear unverified-provenance warning.
"""
from __future__ import annotations

# Each entry: a pullable Ollama ref (`hf.co/<repo>` for HF GGUF, or an Ollama
# name), with metadata for the UI. `recommended` surfaces the best defaults.
CATALOG: list[dict] = [
    # ── Cybersecurity specialists (defensive) ──────────────────────────────
    {
        "key": "foundation-sec-8b",
        "name": "Foundation-Sec-8B",
        "ref": "hf.co/QuantFactory/Foundation-Sec-8B-GGUF",
        "params": "8B", "approx_gb": 5, "origin": "Cisco · Llama-3.1 base (US)",
        "focus": "Defensive: MITRE ATT&CK, CVE/CWE, alert triage, IR",
        "kind": "cyber", "recommended": True, "compliant": True,
        "note": "Top pick — strong cyber knowledge, 8B fits with room to spare.",
    },
    {
        "key": "cyberpal-20b",
        "name": "CyberPal-2.0-20B",
        "ref": "hf.co/cyber-pal-security/CyberPal2.0-20B-GGUF",
        "params": "20B", "approx_gb": 12, "origin": "IBM-affiliated · gpt-oss base (US)",
        "focus": "Deep CTI Q&A, vuln→weakness mapping, TTPs",
        "kind": "cyber", "recommended": True, "compliant": True,
        "note": "Heavier deep-CTI option. Verify the GGUF repo exists on install.",
    },
    {
        "key": "zysec-7b",
        "name": "ZySec-7B (SecurityLLM)",
        "ref": "hf.co/QuantFactory/SecurityLLM-GGUF",
        "params": "7B", "approx_gb": 4, "origin": "ZySec-AI · Mistral base (FR)",
        "focus": "General security assistant",
        "kind": "cyber", "recommended": False, "compliant": True,
        "note": "Lightweight assistant-style security model.",
    },
    # ── General-purpose keeper + embeddings ────────────────────────────────
    {
        "key": "gemma3-27b",
        "name": "gemma3:27b",
        "ref": "gemma3:27b",
        "params": "27B", "approx_gb": 17, "origin": "Google (US)",
        "focus": "Capable generalist — strict JSON, long context",
        "kind": "generalist", "recommended": True, "compliant": True,
        "note": "Your structural workhorse / fallback.",
    },
    {
        "key": "nomic-embed-text",
        "name": "nomic-embed-text",
        "ref": "nomic-embed-text",
        "params": "137M", "approx_gb": 1, "origin": "Nomic (US)",
        "focus": "Embeddings — required for all RAG/learning",
        "kind": "embed", "recommended": True, "compliant": True,
        "note": "Required. Do not remove.",
    },
]

# Models that must never be removed via the manager (breaks the platform).
PROTECTED_KINDS = {"embed"}


def by_ref(ref: str) -> dict | None:
    return next((m for m in CATALOG if m["ref"] == ref or m["name"] == ref), None)


def is_protected(name: str) -> bool:
    """An installed model name maps to a protected catalog entry (e.g. embeddings)."""
    m = by_ref(name)
    return bool(m and m["kind"] in PROTECTED_KINDS)
