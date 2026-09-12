#!/usr/bin/env bash
# BENCH-STAGED (2026-07-23, the reasoning-depth session): serve
# OpenMath-Nemotron-14B-Kaggle (the AIMO-competition-tuned sibling) via
# llama.cpp Vulkan for heat two of the math bench-off. NOT resident by
# default; wakes only when the room allows. Port 8092.

set -euo pipefail

MODELS_ROOT="${MODELS_ROOT:-$HOME/models}"
LLAMA_SERVER="${LLAMA_SERVER:-$HOME/llama.cpp/build/vulkan/bin/llama-server}"
MODEL_DIR="${MODEL_DIR:-$MODELS_ROOT/openmath-nemotron-14b-kaggle-gguf}"
MODEL="${MODEL:-$(ls "$MODEL_DIR"/*Q8_0*.gguf 2>/dev/null | head -1)}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8092}"
CTX="${CTX:-32768}"

export LD_LIBRARY_PATH="$HOME/llama.cpp/build/vulkan/bin:$HOME/llama.cpp/build/vulkan/common${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

[ -x "$LLAMA_SERVER" ] || { echo "ERROR: missing $LLAMA_SERVER (rebuild llama.cpp Vulkan)"; exit 1; }
[ -n "$MODEL" ] && [ -f "$MODEL" ] || { echo "ERROR: no Q8_0 GGUF in $MODEL_DIR (pull first)"; exit 1; }

echo "Serving OpenMath-Nemotron-14B-Kaggle (bench guest) on http://${HOST}:${PORT}"
echo "Model:   $MODEL"
echo "Context: $CTX, all layers on GPU (Vulkan)"

exec "$LLAMA_SERVER" \
    -m "$MODEL" \
    -a openmath-nemotron-14b-kaggle \
    --host "$HOST" \
    --port "$PORT" \
    -ngl 99 \
    -c "$CTX" \
    --jinja \
    --reasoning-format none \
    --metrics \
    --threads 16 \
    --threads-batch 16
