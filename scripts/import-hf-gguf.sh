#!/usr/bin/env bash
#
# import-hf-gguf.sh
# Make a Hugging Face model that ISN'T published as GGUF usable in Ollama, by
# converting the official weights to GGUF locally and registering them.
#
# This is the supported path for strong models (e.g. CyberPal-2.0-20B) that have
# no community GGUF on the Hub. It is also the most COMPLIANCE-CLEAN path:
# instead of trusting a stranger's re-upload, you quantize the PUBLISHER's own
# weights yourself.
#
# Safe by design:
#   - The OUTPUT is GGUF — a data format that cannot carry executable model code
#     (sidesteps the pickle / trust_remote_code malware vector on HF).
#   - Everything runs on your machine. The only network use is the one-time
#     weight download from Hugging Face. No client/tenant data is ever involved.
#   - Idempotent-ish: an already-registered Ollama model is left alone.
#
# Usage:
#   chmod +x scripts/import-hf-gguf.sh
#   ./scripts/import-hf-gguf.sh <hf_repo> [quant] [ollama_name]
#
# Examples:
#   ./scripts/import-hf-gguf.sh cyber-pal-security/CyberPal2.0-20B Q5_K_M cyberpal2.0-20b
#   ./scripts/import-hf-gguf.sh some-org/Some-Cyber-Model            # quant=Q5_K_M, name auto
#
# Requirements (one-time, on the host — NOT in Docker):
#   - ollama            (https://ollama.com)
#   - python3 + pip
#   - cmake + a C/C++ toolchain (Xcode Command Line Tools on macOS: xcode-select --install)
#   - ~40 GB free temp disk for a 20B model (f16 intermediate); the final GGUF is
#     much smaller (Q5_K_M of a 20B ≈ 14 GB). Set WORKDIR to a roomy volume.
#
# Tunables (env):
#   WORKDIR     scratch dir for download + conversion   (default: ./.gguf-build)
#   LLAMA_CPP   path to a llama.cpp checkout to reuse    (default: $WORKDIR/llama.cpp)
#   KEEP_TEMP   set to 1 to keep the scratch dir afterwards
#
set -uo pipefail

REPO="${1:-}"
QUANT="${2:-Q5_K_M}"
NAME="${3:-}"

if [[ -z "$REPO" ]]; then
  echo "Usage: $0 <hf_repo> [quant=Q5_K_M] [ollama_name]" >&2
  echo "Example: $0 cyber-pal-security/CyberPal2.0-20B Q5_K_M cyberpal2.0-20b" >&2
  exit 2
fi

# Derive a sane Ollama name from the repo if none given (lowercase, no org).
if [[ -z "$NAME" ]]; then
  NAME="$(echo "${REPO##*/}" | tr '[:upper:]' '[:lower:]')"
fi

WORKDIR="${WORKDIR:-$(pwd)/.gguf-build}"
LLAMA_CPP="${LLAMA_CPP:-$WORKDIR/llama.cpp}"

step() { echo; echo "==> $*"; }
die()  { echo "✗ $*" >&2; exit 1; }

# ── Preflight ────────────────────────────────────────────────────────────────
# NOTE: cmake is NOT required up front. We only build llama.cpp as a last resort;
# the easy path is a prebuilt `llama-quantize` from `brew install llama.cpp`.
command -v ollama  >/dev/null 2>&1 || die "Ollama not found. Install from https://ollama.com and retry."
command -v python3 >/dev/null 2>&1 || die "python3 not found."

# Already registered? Don't redo the heavy work.
if ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$NAME"; then
  echo "✓ Ollama already has '$NAME' — nothing to do."
  echo "  (Remove it first with 'ollama rm $NAME' if you want to rebuild.)"
  exit 0
fi

mkdir -p "$WORKDIR" || die "Cannot create WORKDIR '$WORKDIR'."

# ── llama.cpp (convert script + quantizer) ───────────────────────────────────
if [[ ! -f "$LLAMA_CPP/convert_hf_to_gguf.py" ]]; then
  step "Fetching llama.cpp (one-time) → $LLAMA_CPP"
  command -v git >/dev/null 2>&1 || die "git not found (needed to fetch llama.cpp)."
  git clone --depth 1 https://github.com/ggml-org/llama.cpp "$LLAMA_CPP" \
    || die "Failed to clone llama.cpp."
fi

# convert_hf_to_gguf.py needs a few Python deps. Install them from PUBLIC PyPI,
# ignoring any local pip config (--isolated) — corporate setups often pin pip to
# a private, authenticated index (e.g. Artifactory) that 401s on these public
# packages. Override the index with PIP_INDEX_URL if you have a working mirror.
step "Ensuring Python conversion deps (public PyPI)"
PIP_INDEX="${PIP_INDEX_URL:-https://pypi.org/simple}"
pip_install() { python3 -m pip install --isolated --index-url "$PIP_INDEX" "$@"; }

# Prefer llama.cpp's exact converter requirements; fall back to a minimal set.
REQ=""
for r in "$LLAMA_CPP/requirements/requirements-convert_hf_to_gguf.txt" \
         "$LLAMA_CPP/requirements.txt"; do
  [[ -f "$r" ]] && { REQ="$r"; break; }
done
if [[ -n "$REQ" ]] && pip_install -r "$REQ"; then
  :  # converter requirements installed
elif pip_install "huggingface_hub[cli]" numpy safetensors sentencepiece gguf torch; then
  :  # minimal set installed
else
  die "Failed to install Python deps from '$PIP_INDEX'.
   Your pip may be pinned to a private index. Retry with a reachable one, e.g.:
     PIP_INDEX_URL=https://pypi.org/simple $0 $REPO $QUANT $NAME"
fi

# Locate a quantizer. Prefer a PREBUILT binary (brew / PATH) so most users never
# need cmake or a compiler. `brew install llama.cpp` puts `llama-quantize` on PATH.
BREW_PREFIX="$(brew --prefix 2>/dev/null || true)"
QUANT_BIN=""
for cand in \
  "$(command -v llama-quantize 2>/dev/null)" \
  "${BREW_PREFIX:+$BREW_PREFIX/bin/llama-quantize}" \
  "$LLAMA_CPP/build/bin/llama-quantize" \
  "$LLAMA_CPP/llama-quantize"; do
  [[ -n "$cand" && -x "$cand" ]] && { QUANT_BIN="$cand"; break; }
done

if [[ -z "$QUANT_BIN" ]]; then
  # No prebuilt quantizer. The easy fix is brew; only fall back to a source build.
  if ! command -v cmake >/dev/null 2>&1; then
    die "No 'llama-quantize' found and cmake isn't installed.
   Easiest fix (no compiler needed):  brew install llama.cpp
   Then re-run this script. (Alternatively: brew install cmake  to build from source.)"
  fi
  step "Building llama-quantize from source (one-time; uses cmake)"
  cmake -S "$LLAMA_CPP" -B "$LLAMA_CPP/build" -DLLAMA_CURL=OFF >/dev/null \
    || die "cmake configure failed."
  cmake --build "$LLAMA_CPP/build" --target llama-quantize -j >/dev/null \
    || die "Building llama-quantize failed."
  QUANT_BIN="$LLAMA_CPP/build/bin/llama-quantize"
fi
[[ -x "$QUANT_BIN" ]] || die "Could not locate or build llama-quantize."
echo "    using quantizer: $QUANT_BIN"

# ── Download the official weights ────────────────────────────────────────────
SNAP="$WORKDIR/${REPO//\//_}"
step "Downloading $REPO from Hugging Face → $SNAP"
python3 -m huggingface_hub download "$REPO" --local-dir "$SNAP" \
  >/dev/null 2>&1 \
  || python3 - "$REPO" "$SNAP" <<'PY' || die "Download failed (check the repo id / your HF access)."
import sys
from huggingface_hub import snapshot_download
snapshot_download(repo_id=sys.argv[1], local_dir=sys.argv[2])
PY

# ── Convert HF → GGUF (f16) ──────────────────────────────────────────────────
F16="$WORKDIR/${NAME}.f16.gguf"
step "Converting to GGUF (f16) — this is the slow part"
python3 "$LLAMA_CPP/convert_hf_to_gguf.py" "$SNAP" --outfile "$F16" --outtype f16 \
  || die "HF→GGUF conversion failed (architecture may be unsupported by this llama.cpp — try 'git -C $LLAMA_CPP pull')."

# ── Quantize ─────────────────────────────────────────────────────────────────
OUT="$WORKDIR/${NAME}.${QUANT}.gguf"
step "Quantizing → $QUANT"
"$QUANT_BIN" "$F16" "$OUT" "$QUANT" || die "Quantization to $QUANT failed."
rm -f "$F16"  # the f16 intermediate is large; the quantized GGUF is what we keep

# ── Register in Ollama ───────────────────────────────────────────────────────
MODELFILE="$WORKDIR/${NAME}.Modelfile"
printf 'FROM %s\n' "$OUT" > "$MODELFILE"
step "Registering '$NAME' in Ollama"
ollama create "$NAME" -f "$MODELFILE" || die "ollama create failed."

if [[ "${KEEP_TEMP:-0}" != "1" ]]; then
  # Keep the final GGUF (Ollama copies it into its store on create, so it's safe
  # to drop the scratch copy) but clear the bulky download snapshot.
  rm -rf "$SNAP" "$OUT" "$MODELFILE"
fi

echo
echo "──────────────────────────────────────────────"
echo "✓ Done. '$NAME' is now an installed Ollama model."
echo "  Assign it to a client in Config → Models, or set it as Sable's model."
echo "  Verify:  ollama run $NAME 'hello'"
