#!/usr/bin/env bash
# BENCH-STAGED (2026-07-23, the reasoning-depth session): serve
# OpenMath-Nemotron-32B (the family ceiling, Q6_K, ~27G resident) via
# llama.cpp Vulkan for heat two of the math bench-off. NOT resident by
# default and never beside both 14B guests: the box does not hold five
# mathematicians at once. Port 8093.

set -euo pipefail

MODELS_ROOT="${MODELS_ROOT:-$HOME/models}"
LLAMA_SERVER="${LLAMA_SERVER:-$HOME/llama.cpp/build/vulkan/bin/llama-server}"
MODEL_DIR="${MODEL_DIR:-$MODELS_ROOT/openmath-nemotron-32b-gguf}"
MODEL="${MODEL:-$(ls "$MODEL_DIR"/*Q6_K*.gguf 2>/dev/null | head -1)}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8093}"
CTX="${CTX:-32768}"

export LD_LIBRARY_PATH="$HOME/llama.cpp/build/vulkan/bin:$HOME/llama.cpp/build/vulkan/common${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

[ -x "$LLAMA_SERVER" ] || { echo "ERROR: missing $LLAMA_SERVER (rebuild llama.cpp Vulkan)"; exit 1; }
[ -n "$MODEL" ] && [ -f "$MODEL" ] || { echo "ERROR: no Q6_K GGUF in $MODEL_DIR (pull first)"; exit 1; }

echo "Serving OpenMath-Nemotron-32B (bench guest, family ceiling) on http://${HOST}:${PORT}"
echo "Model:   $MODEL"
echo "Context: $CTX, all layers on GPU (Vulkan)"

exec "$LLAMA_SERVER" \
    -m "$MODEL" \
    -a openmath-nemotron-32b \
    --host "$HOST" \
    --port "$PORT" \
    -ngl 99 \
    -c "$CTX" \
    --jinja \
    --reasoning-format none \
    --metrics \
    --threads 16 \
    --threads-batch 16
