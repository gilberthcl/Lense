#!/usr/bin/env bash
#
# remove-old-models.sh
# Remove the generalist / non-compliant Ollama models we agreed to drop,
# freeing disk. Conservative and interactive:
#   - Only touches models in the REMOVE list below.
#   - NEVER removes the protected models (gemma3:27b, nomic-embed-text), even
#     if you accidentally add them to REMOVE.
#   - Only acts on models that are actually installed.
#   - Shows exactly what it will remove and asks before doing anything.
#
# Run:
#   chmod +x scripts/remove-old-models.sh
#   ./scripts/remove-old-models.sh
#
set -uo pipefail

# ── Models to remove (base names / tags as agreed) ───────────────────────────
REMOVE=(
  "gpt-oss:20b"                       # redundant once gemma3:27b is the one generalist
  "mistral-small:24b"                 # redundant second generalist
  "qwen2.5:7b"                        # Chinese-origin; repoint Sable to a cyber specialist
  "nemotron"                          # ~42GB, too big for a 32GB box
  "gemma4:31b-cloud"                  # compliance: -cloud breaks local-only
  "coney_/gpt-oss_claude-sonnet4.6"   # unverified community fine-tune
)

# ── Protected — never removed under any circumstances ────────────────────────
PROTECT=(
  "gemma3:27b"          # your kept generalist / structural workhorse
  "nomic-embed-text"    # embeddings — required for all RAG/learning
)

command -v ollama >/dev/null 2>&1 || {
  echo "✗ Ollama not found. Nothing to do." >&2
  exit 1
}

echo "Currently installed:"
ollama list
echo

# Resolve the ACTUAL installed names that match our remove patterns, skipping
# anything protected. We match on exact name or '<name>:<tag>' / '<name>...'.
present=()
while read -r name _rest; do
  [[ -z "$name" || "$name" == "NAME" ]] && continue

  skip=0
  for p in "${PROTECT[@]}"; do
    if [[ "$name" == "$p" || "$name" == "$p:"* ]]; then skip=1; break; fi
  done
  ((skip)) && continue

  for m in "${REMOVE[@]}"; do
    if [[ "$name" == "$m" || "$name" == "$m:"* || "$name" == "$m"* ]]; then
      present+=("$name"); break
    fi
  done
done < <(ollama list 2>/dev/null)

if ((${#present[@]} == 0)); then
  echo "Nothing to remove — none of the listed models are installed."
  exit 0
fi

echo "About to REMOVE these installed models:"
printf '  - %s\n' "${present[@]}"
echo
echo "Protected (kept no matter what): ${PROTECT[*]}"
echo
read -r -p "Proceed with removal? [y/N] " ans
case "${ans:-}" in
  y|Y|yes|YES) ;;
  *) echo "Aborted — nothing removed."; exit 0 ;;
esac

for name in "${present[@]}"; do
  echo "==> removing $name"
  ollama rm "$name" || echo "   (failed to remove $name)"
done

echo
echo "Done. Remaining models:"
ollama list
