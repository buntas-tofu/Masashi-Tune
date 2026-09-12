#!/usr/bin/env bash
# Serve Gemma 4 26B-A4B (MoE) via llama.cpp Vulkan llama-server.
#
# Local-only by default (binds 127.0.0.1). To expose on the LAN, change the
# --host or set $HOST=0.0.0.0 in the env. Don't expose without --api-key on
# untrusted networks.
#
# Vulkan was chosen over HIP because on this iGPU (gfx1151) it is measurably
# faster for inference. HIP remains better for training; llama.cpp does not
# train anyway.

set -euo pipefail

# Optional env file: set SERVE_ENV to a file that exports MODEL_DIR, HOST,
# PORT, and the rest. Everything below already has a neutral default.
[ -n "${SERVE_ENV:-}" ] && [ -f "$SERVE_ENV" ] && . "$SERVE_ENV"

MODELS_ROOT="${MODELS_ROOT:-$HOME/models}"
LLAMA_SERVER="${LLAMA_SERVER:-$HOME/llama.cpp/build/vulkan/bin/llama-server}"
MODEL_DIR="${MODEL_DIR:-$MODELS_ROOT/gemma-4-26B-A4B}"
MODEL="${MODEL:-$MODEL_DIR/gemma-4-26B-A4B-it-UD-Q4_K_M.gguf}"
MMPROJ="${MMPROJ:-$MODEL_DIR/mmproj-F16.gguf}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"
CTX="${CTX:-8192}"

# The Vulkan build RUNPATH is absolute to its original build dir; after a
# relayout the shared libs resolve via LD_LIBRARY_PATH instead.
export LD_LIBRARY_PATH="$HOME/llama.cpp/build/vulkan/bin:$HOME/llama.cpp/build/vulkan/common${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

[ -x "$LLAMA_SERVER" ] || { echo "ERROR: missing $LLAMA_SERVER (rebuild llama.cpp Vulkan)"; exit 1; }
[ -f "$MODEL" ]        || { echo "ERROR: missing model $MODEL"; exit 1; }

EXTRA=()
[ -f "$MMPROJ" ] && EXTRA+=(--mmproj "$MMPROJ")

echo "Serving Gemma 4 26B-A4B on http://${HOST}:${PORT}"
echo "Model:   $MODEL"
[ -f "$MMPROJ" ] && echo "MMProj:  $MMPROJ (vision enabled)"
echo "Context: $CTX, all layers on GPU (Vulkan)"
echo

exec "$LLAMA_SERVER" \
    -m "$MODEL" \
    "${EXTRA[@]}" \
    --host "$HOST" \
    --port "$PORT" \
    -ngl 99 \
    -c "$CTX" \
    --jinja \
    --metrics \
    --threads 16 \
    --threads-batch 16
