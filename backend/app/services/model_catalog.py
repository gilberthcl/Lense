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
        "ref": "hf.co/QuantFactory/Foundation-Sec-8B-GGUF:Q5_K_M",
        "params": "8B", "approx_gb": 6, "origin": "Cisco · Llama-3.1 base (US)",
        "focus": "Defensive: MITRE ATT&CK, CVE/CWE, alert triage, IR",
        "kind": "cyber", "recommended": True, "compliant": True,
        "note": "Top pick — strong cyber knowledge, 8B fits with room to spare.",
    },
    {
        "key": "cyberpal-20b",
        "name": "CyberPal-2.0-20B",
        # No public GGUF exists for this model (the publisher ships safetensors;
        # no community quant on the Hub). So this is a BUILD-FROM-SOURCE entry:
        # convert the official weights to GGUF locally with import-hf-gguf.sh.
        # That is also the cleanest provenance — we quantize IBM's own weights,
        # not a stranger's re-upload. `ollama_name` is what the script registers.
        "ref": "hf.co/cyber-pal-security/CyberPal2.0-20B",
        "ollama_name": "cyberpal2.0-20b",
        "params": "20B", "approx_gb": 14, "origin": "IBM SecKnowledge · gpt-oss-20B base (US)",
        "focus": "Deep CTI Q&A, vuln→weakness mapping, TTPs",
        "kind": "cyber", "recommended": False, "compliant": True,
        "build_only": True,
        "build_cmd": "./scripts/import-hf-gguf.sh cyber-pal-security/CyberPal2.0-20B Q5_K_M cyberpal2.0-20b",
        "note": "No public GGUF — build locally from the official weights with the "
                "import script (one-time, ~40 GB temp disk). Cleaner provenance "
                "than a community re-upload.",
    },
    {
        "key": "zysec-7b",
        "name": "ZySec-7B (SecurityLLM)",
        "ref": "hf.co/QuantFactory/SecurityLLM-GGUF:Q5_K_M",
        "params": "7B", "approx_gb": 5, "origin": "ZySec-AI · Mistral base (FR)",
        "focus": "Security assistant — Sable's default brain",
        "kind": "cyber", "recommended": True, "compliant": True,
        "note": "Assistant-style security model; powers Sable's chat.",
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


def _base(ref: str) -> str:
    """Drop a trailing :tag for matching (`...GGUF:Q5_K_M` → `...GGUF`,
    `nomic-embed-text:latest` → `nomic-embed-text`)."""
    # hf.co refs and plain names only carry a colon for the tag.
    return ref.rsplit(":", 1)[0] if ":" in ref else ref


def by_ref(ref: str) -> dict | None:
    """Match an installed model name to a catalog entry, tag-insensitively, so
    `:latest` / `:Q5_K_M` suffixes still resolve. Also matches a build-from-source
    entry's locally-registered `ollama_name` (e.g. `cyberpal2.0-20b`), so a model
    we built ourselves is still recognised as vetted/compliant after the build."""
    b = _base(ref)
    def _names(m: dict) -> list[str]:
        return [n for n in (m["ref"], m["name"], m.get("ollama_name")) if n]
    return next(
        (m for m in CATALOG
         if ref in _names(m) or b in [_base(n) for n in _names(m)]),
        None,
    )


def is_protected(name: str) -> bool:
    """An installed model name maps to a protected catalog entry (e.g. embeddings)."""
    m = by_ref(name)
    return bool(m and m["kind"] in PROTECTED_KINDS)
