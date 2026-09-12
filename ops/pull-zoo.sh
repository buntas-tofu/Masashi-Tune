#!/usr/bin/env bash
# pull-zoo.sh: fill the model shelf from a curated pull list.
# Sequential queue, resumable (hf download resumes), one failure does not
# kill the line. Repos verified live against the HF API 2026-07-03; see
# docs/PULL_LIST_2026-07-03.md for the list's provenance and destinations.
set -u

HOLD="${ZOO_DIR:-$HOME/zoo}"
HF="${HF_BIN:-$HOME/.local/bin/hf}"
export HF_HUB_DISABLE_TELEMETRY=1
mkdir -p "$HOLD"
LOG="$HOLD/pull-$(date +%Y%m%d-%H%M).log"

say() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

# repo | include pattern (empty = whole repo) | dest dir under the zoo
# Corrected 2026-07-03 evening: four items originally pointed at official
# GGUF repos that do not exist (a probe parsed HF error bodies as EXISTS;
# author-search listings are the trustworthy source). Community quants
# verified file-by-file: unsloth and bartowski, house standard.
QUEUE=$(cat <<'EOF'
mistralai/Ministral-3-14B-Instruct-2512-GGUF|*Q4_K_M*|ministral-3-14b-gguf
bartowski/mistralai_Mistral-Small-3.2-24B-Instruct-2506-GGUF|*Q4_K_M*|mistral-small-3.2-24b-gguf
unsloth/Nemotron-3-Nano-30B-A3B-GGUF|*UD-Q4_K_XL*|nemotron-3-nano-30b-gguf
google/gemma-4-E4B-it-qat-q4_0-gguf|*.gguf|gemma-4-e4b-qat-gguf
google/gemma-4-E2B-it-qat-q4_0-gguf|*.gguf|gemma-4-e2b-qat-gguf
unsloth/embeddinggemma-300m-GGUF|*.gguf|embeddinggemma-300m-gguf
mistralai/Ministral-3-3B-Instruct-2512-GGUF|*Q4_K_M*|ministral-3-3b-gguf
mistralai/Mistral-Small-4-119B-2603-NVFP4||mistral-small-4-119b-nvfp4
unsloth/Hermes-4-70B-GGUF|*Q4_K_M*|hermes-4-70b-gguf
unsloth/Hermes-4-405B-GGUF|*Q4_K_M*|hermes-4-405b-gguf
EOF
)

say "zoo pull opens: $(echo "$QUEUE" | wc -l) items -> $HOLD"
FAIL=0
while IFS='|' read -r repo inc dest; do
  [ -z "$repo" ] && continue
  say "pull: $repo ${inc:+(include $inc)}"
  if [ -n "$inc" ]; then
    "$HF" download "$repo" --include "$inc" --local-dir "$HOLD/$dest" >>"$LOG" 2>&1
  else
    "$HF" download "$repo" --local-dir "$HOLD/$dest" >>"$LOG" 2>&1
  fi
  if [ $? -eq 0 ]; then
    say "done: $dest ($(du -sh "$HOLD/$dest" 2>/dev/null | cut -f1))"
  else
    say "FAILED: $repo (queue continues; see $LOG)"
    FAIL=$((FAIL + 1))
  fi
done <<<"$QUEUE"

say "zoo pull closes: $FAIL failures"
say "shelf: $(df -h "$HOLD" | tail -1 | awk '{print $3" used, "$4" free"}')"
du -sh "$HOLD"/* 2>/dev/null | tee -a "$LOG"
exit "$FAIL"
