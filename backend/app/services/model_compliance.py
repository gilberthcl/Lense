"""
Model compliance allowlist (W0b).

The project rule is hard: client data may only ever be routed through a
Western-origin, locally-run, verified model — never a `-cloud` model (breaks
local-only/tenant-isolation) and never an unverified community fine-tune
(unknown provenance). This module is the single source of truth that the model
selector and the routing layer both check, so the rule is enforced in code, not
by memory.

Maintained allowlist by model family. Add new verified families here.
"""
from __future__ import annotations

# Verified Western-origin families (match on the name root before the ':' tag).
WESTERN_FAMILIES = (
    "gemma",          # Google
    "gpt-oss",        # OpenAI
    "llama", "llama2", "llama3", "codellama",  # Meta
    "mistral", "mixtral", "ministral",         # Mistral (FR)
    "nemotron",       # NVIDIA
    "phi",            # Microsoft
    "granite",        # IBM
    "command-r", "command",  # Cohere (CA)
    "nomic-embed",    # Nomic (embeddings)
    "snowflake-arctic", "arctic-embed",  # Snowflake
    "olmo",           # AI2
    "dbrx",           # Databricks
    "falcon",         # TII (UAE — Western-aligned/open; adjust if policy differs)
)

# Explicitly non-Western families — blocked even if a name looks familiar.
NON_WESTERN_FAMILIES = (
    "qwen", "deepseek", "yi", "glm", "chatglm", "internlm",
    "baichuan", "ernie", "minicpm", "skywork", "telechat",
)


def _root(name: str) -> str:
    return (name or "").strip().lower().split(":")[0]


def classify(name: str) -> tuple[bool, str]:
    """Return (allowed, reason). `reason` is the family when allowed, else why
    it's blocked — surfaced in the UI."""
    n = (name or "").strip().lower()
    if not n:
        return False, "empty name"
    if "cloud" in n:
        return False, "cloud model — breaks local-only and tenant isolation"
    # A model on the curated catalog has been provenance-checked by us — it's
    # vetted even though it's namespaced (e.g. hf.co/<org>/<repo>-GGUF). This is
    # what lets the verified HF cyber models (Foundation-Sec, ZySec) be used while
    # arbitrary namespaced community models stay blocked below.
    from app.services import model_catalog  # local import avoids any import cycle
    cat = model_catalog.by_ref(name)
    if cat and cat.get("compliant"):
        return True, "vetted catalog model"
    if "/" in n:
        return False, "unverified community model (namespaced provenance)"
    root = _root(n)
    for fam in NON_WESTERN_FAMILIES:
        if root.startswith(fam):
            return False, f"non-Western origin ({fam})"
    for fam in WESTERN_FAMILIES:
        if root.startswith(fam):
            return True, fam
    return False, "unrecognised provenance — not on the verified allowlist"


def is_allowed(name: str) -> bool:
    return classify(name)[0]
