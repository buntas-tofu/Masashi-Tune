#!/usr/bin/env bash
# Serve the 14B code vessel (Q6_K, the code specialist) via llama.cpp Vulkan
# llama-server.
#
# Relocated 2026-07-17 from a dense-capacity box. That box is a 120B + 2 small
# vessel mirror; an always-on 14B squatter crushed the KV headroom of the
# reasoner to under 1GB and made long drafts whiff while the roomier box
# finished the same work. Weights moved to internal storage 2026-08-10, off
# the removable hold that made a wakeable vessel fail silent if unplugged.
# Lazy here, loaded on summon, warm only while it works.
#
# --reasoning-format deepseek carried from the earlier serve.
# LD_LIBRARY_PATH is required: the Vulkan build's RUNPATH is absolute to its
# original build dir and went stale after a relayout.
set -euo pipefail

MODELS_ROOT="${MODELS_ROOT:-$HOME/models}"
LLAMA_SERVER="${LLAMA_SERVER:-$HOME/llama.cpp/build/vulkan/bin/llama-server}"
MODEL_DIR="${MODEL_DIR:-$MODELS_ROOT/code-14b-gguf}"
MODEL="${MODEL:-$MODEL_DIR/code-14b-Q6_K.gguf}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8082}"
CTX="${CTX:-32768}"

export LD_LIBRARY_PATH="$HOME/llama.cpp/build/vulkan/bin:$HOME/llama.cpp/build/vulkan/common${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

[ -x "$LLAMA_SERVER" ] || { echo "ERROR: missing $LLAMA_SERVER (rebuild llama.cpp Vulkan)"; exit 1; }
[ -f "$MODEL" ]        || { echo "ERROR: missing model $MODEL (stage the code GGUF to $MODEL_DIR)"; exit 1; }

echo "Serving code-14b on http://${HOST}:${PORT}"
echo "Model:   $MODEL (cold, lazy-loaded)"
echo "Context: $CTX, all layers on GPU (Vulkan)"
echo "Reasoning: --reasoning-format deepseek"
echo

exec "$LLAMA_SERVER" \
    -m "$MODEL" \
    -a code-14b \
    --host "$HOST" \
    --port "$PORT" \
    -ngl 99 \
    -c "$CTX" \
    --jinja \
    --reasoning-format deepseek \
    --metrics \
    --threads 16 \
    --threads-batch 16
