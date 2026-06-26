#!/usr/bin/env bash
#
# install-cyber-models.sh
# Install vetted, fully-local, GGUF cybersecurity models into Ollama.
#
# Safe by design:
#   - GGUF only — a data format that CANNOT carry executable model code
#     (sidesteps the pickle / trust_remote_code malware vector on HF).
#   - Runs entirely on your machine. The only network use is the one-time
#     weight download; no client data is ever involved.
#   - Re-runnable: already-installed models are skipped; a failed pull never
#     aborts the rest.
#
# Edit the MODELS list to add/remove what you want, then run:
#   chmod +x scripts/install-cyber-models.sh
#   ./scripts/install-cyber-models.sh
#
set -uo pipefail

# ── Models to install (ref → what it is) ─────────────────────────────────────
# VERIFIED GGUF (pull directly):
MODELS=(
  "hf.co/QuantFactory/Foundation-Sec-8B-GGUF"   # Cisco · Llama-3.1 8B · DEFENSIVE: MITRE/CVE/IR · ~5GB
  "hf.co/QuantFactory/SecurityLLM-GGUF"          # ZySec-7B · Mistral 7B · security assistant · ~4GB
)
# OPTIONAL (uncomment to try — GGUF repo name not yet confirmed; may 404):
#   "hf.co/cyber-pal-security/CyberPal2.0-20B"   # CyberPal-2.0-20B · deep CTI · ~12GB (likely needs conversion)
#
# NOTE: Foundation-Sec-8B above is the BASE (completion) model — ideal for the
# LENS analysis pipeline (which wraps it in structured prompts). For Sable's
# free-form CHAT, an *-Instruct* GGUF works better; install one via the custom
# field in Config → Models once you've picked a quant.

command -v ollama >/dev/null 2>&1 || {
  echo "✗ Ollama not found. Install it from https://ollama.com and retry." >&2
  exit 1
}

echo "Installing ${#MODELS[@]} model(s) into Ollama…"
installed=(); failed=()

for ref in "${MODELS[@]}"; do
  echo
  echo "==> $ref"
  if ollama list 2>/dev/null | grep -qF "$ref"; then
    echo "    already installed — skipping"
    installed+=("$ref")
    continue
  fi
  if ollama pull "$ref"; then
    installed+=("$ref")
  else
    echo "    ✗ FAILED to pull $ref"
    failed+=("$ref")
  fi
done

echo
echo "──────────────────────────────────────────────"
echo "Installed/present: ${#installed[@]}    Failed: ${#failed[@]}"
if ((${#failed[@]})); then
  printf '  ✗ %s\n' "${failed[@]}"
  echo "  A failed pull almost always means the GGUF repo name needs adjusting."
  echo "  Find the right '<org>/<repo>-GGUF' on huggingface.co and edit MODELS above,"
  echo "  or use Config → Models → custom install in LENS."
fi
echo
echo "Next: assign a model in LENS —"
echo "  • globally:    Config → Global (analyst model)"
echo "  • per client:  the client's model card"
echo "  • for Sable:   (its model setting)"
echo "Tip: 'ollama ps' shows what's loaded in RAM; only one runs at a time."
