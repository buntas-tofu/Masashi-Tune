#!/usr/bin/env bash
# Serve the vision 27B multimodal vessel (Qwen3.5-27B UD-Q4_K_XL) via
# llama.cpp CUDA. Moved off gemma-4-26B (2026-08-22): gemma's KV is ~240
# MiB/1k and capped a 5090 near 26k context; qwen's GQA KV is ~80 MiB/1k and
# serves 64k on the same card with identical tool discipline (8/8 on the
# tool lane).
#
# THE FACE-SERVE LAW, learned at the bench and load-bearing: serve with
# --reasoning off --reasoning-budget 0. Qwen thinks by default and would
# spend the budget on hidden reasoning and return empty content with a
# healthy 200 (the THINKDEFAULT tape). Off is right for a chat and vision
# vessel: it trades on snap, not hidden deliberation.
#
# GPU pinned by UUID, not index: llama.cpp's CUDA enumeration can order a
# secondary card as device 0 and the primary as device 1, the reverse of
# nvidia-smi, so a numeric pin can land on the wrong card. Set GPU_UUID to
# the target card's UUID; unset, the serve uses whatever CUDA_VISIBLE_DEVICES
# already provides. Bind posture: 127.0.0.1 by default; set HOST to expose.
set -euo pipefail

# Optional env file: set SERVE_ENV to a file that exports MODEL_DIR, HOST,
# PORT, and the rest. Everything below already has a neutral default.
[ -n "${SERVE_ENV:-}" ] && [ -f "$SERVE_ENV" ] && . "$SERVE_ENV"

MODELS_ROOT="${MODELS_ROOT:-$HOME/models}"
LLAMA_SERVER="${LLAMA_SERVER:-$HOME/llama.cpp/build/cuda/bin/llama-server}"
MODEL_DIR="${MODEL_DIR:-$MODELS_ROOT/qwen3.8-27b-gguf}"
MODEL="${MODEL:-$MODEL_DIR/Qwen3.8-27B-Q4_K_M.gguf}"
MMPROJ="${MMPROJ:-$MODEL_DIR/mmproj-F16.gguf}"
GPU_UUID="${GPU_UUID:-}"   # optional: pin the card by UUID (see header)
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"
CTX="${CTX:-65536}"

# THE ADAPTER SLOT. LORA names a GGUF LoRA to ride the base weights; empty
# serves bare, so the default posture is unchanged and the adapter is an
# explicit act. Hot-swap without a restart rides llama-server's
# /lora-adapters endpoint once one is loaded. The face-serve law
# (--reasoning off --reasoning-budget 0) is NOT touched by any adapter; those
# flags stay whatever weights are worn.
LORA="${LORA:-}"

# THE REPETITION-PENALTY LANE (2026-08-30). This vessel ran with llama-server's
# DEFAULT sampling: repeat penalty 1.00 (disabled), window 64. An open-ended
# prompt made it lock onto a phrase and pour it to the 4096-token cap
# (finish_reason: length) at both temp 0 and 0.6, independent of the gemma
# reasoning-spiral the temp-0 law was built for (qwen runs --reasoning off, so
# that mechanism is already off). The lever is repetition penalty, not temp.
# Wire a real penalty and a window wide enough to catch phrase-level loops
# (default 64 is far too short for a repeated sentence). Values are env-tunable.
REPEAT_PENALTY="${REPEAT_PENALTY:-1.10}"
REPEAT_LAST_N="${REPEAT_LAST_N:-512}"
PRESENCE_PENALTY="${PRESENCE_PENALTY:-0.30}"
FREQUENCY_PENALTY="${FREQUENCY_PENALTY:-0.30}"

# The CUDA build's RUNPATH is absolute to its build dir; after a relayout the
# shared libs resolve via LD_LIBRARY_PATH instead.
BUILD_DIR="$(dirname "$LLAMA_SERVER")"
export LD_LIBRARY_PATH="$BUILD_DIR:$BUILD_DIR/../common${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
if [ -n "$GPU_UUID" ]; then
  export CUDA_VISIBLE_DEVICES="$GPU_UUID"
fi

[ -x "$LLAMA_SERVER" ] || { echo "ERROR: missing $LLAMA_SERVER"; exit 1; }
[ -f "$MODEL" ]        || { echo "ERROR: missing model $MODEL"; exit 1; }

EXTRA=()
[ -f "$MMPROJ" ] && EXTRA+=(--mmproj "$MMPROJ")
if [ -n "$LORA" ]; then
  [ -f "$LORA" ] || { echo "ERROR: LORA set but missing: $LORA"; exit 1; }
  EXTRA+=(--lora "$LORA")
fi

echo "Serving Qwen3.5-27B (vision 27B) on http://${HOST}:${PORT}, ctx ${CTX}"
[ -f "$MMPROJ" ] && echo "MMProj: $MMPROJ (vision enabled)"
[ -n "$LORA" ] && echo "Adapter: $LORA"

exec "$LLAMA_SERVER" \
    -m "$MODEL" \
    "${EXTRA[@]}" \
    --host "$HOST" \
    --port "$PORT" \
    ${LLAMA_API_KEY_FILE:+--api-key-file "$LLAMA_API_KEY_FILE"} \
    -ngl 99 \
    -c "$CTX" \
    --jinja \
    --reasoning off \
    --reasoning-budget 0 \
    --metrics \
    --repeat-penalty "$REPEAT_PENALTY" \
    --repeat-last-n "$REPEAT_LAST_N" \
    --presence-penalty "$PRESENCE_PENALTY" \
    --frequency-penalty "$FREQUENCY_PENALTY" \
    --threads 16 \
    --threads-batch 16
