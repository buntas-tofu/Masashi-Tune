#!/usr/bin/env bash
# BENCH-STAGED (2026-07-23, the reasoning-depth session): serve
# OpenMath-Nemotron-14B (NVIDIA brand, Qwen2.5 base) via llama.cpp Vulkan for
# the math-seat bench-off. NOT rostered: no service unit, no seat wiring;
# roster wiring is a later step. Port 8091. CTX starts conservative at 32k;
# revisit after this card's long-CoT guidance is reviewed (the AIMO lineage
# generates long solutions).

set -euo pipefail

MODELS_ROOT="${MODELS_ROOT:-$HOME/models}"
LLAMA_SERVER="${LLAMA_SERVER:-$HOME/llama.cpp/build/vulkan/bin/llama-server}"
MODEL_DIR="${MODEL_DIR:-$MODELS_ROOT/openmath-nemotron-14b-gguf}"
MODEL="${MODEL:-$(ls "$MODEL_DIR"/*Q8_0*.gguf 2>/dev/null | head -1)}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8091}"
CTX="${CTX:-32768}"

export LD_LIBRARY_PATH="$HOME/llama.cpp/build/vulkan/bin:$HOME/llama.cpp/build/vulkan/common${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

[ -x "$LLAMA_SERVER" ] || { echo "ERROR: missing $LLAMA_SERVER (rebuild llama.cpp Vulkan)"; exit 1; }
[ -n "$MODEL" ] && [ -f "$MODEL" ] || { echo "ERROR: no Q8_0 GGUF in $MODEL_DIR (pull first)"; exit 1; }

echo "Serving OpenMath-Nemotron-14B (bench guest) on http://${HOST}:${PORT}"
echo "Model:   $MODEL"
echo "Context: $CTX, all layers on GPU (Vulkan)"

exec "$LLAMA_SERVER" \
    -m "$MODEL" \
    -a openmath-nemotron-14b \
    ${LLAMA_API_KEY_FILE:+--api-key-file "$LLAMA_API_KEY_FILE"} \
    --host "$HOST" \
    --port "$PORT" \
    -ngl 99 \
    -c "$CTX" \
    --jinja \
    --reasoning-format none \
    --metrics \
    --threads 16 \
    --threads-batch 16
