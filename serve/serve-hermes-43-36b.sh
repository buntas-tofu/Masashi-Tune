#!/usr/bin/env bash
# Serve Hermes-4.3-36B as the creative writer (2026-08-23: hermes-4.3-36b
# BF16). Runs llama.cpp Vulkan, the same build path the other Vulkan serves
# use. The model is the F16 GGUF converted from the BF16 safetensors pull
# (weights and serving are separable; the BF16 tandems land in the model store
# and convert to F16 GGUF via llama.cpp convert_hf_to_gguf.py, since
# llama-server does not eat safetensors).
#
# Port 8094, clear of the seated map.
#
# Hybrid-mode note: Hermes 4.3 reasons by default (the thinking/response split
# in its cards). For a creative writer the reasoning budget is a quality lever,
# not a defect, so this serve does NOT carry the vision vessel's
# --reasoning-off law. That law is chat-specific (the THINKDEFAULT tape); a
# writer benefits from letting the vessel deliberate.

set -euo pipefail

MODELS_ROOT="${MODELS_ROOT:-$HOME/models}"
LLAMA_SERVER="${LLAMA_SERVER:-$HOME/llama.cpp/build/vulkan/bin/llama-server}"
MODEL_DIR="${MODEL_DIR:-$MODELS_ROOT/Hermes-4.3-36B-F16}"
MODEL="${MODEL:-$(ls "$MODEL_DIR"/*F16*.gguf 2>/dev/null | head -1)}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8094}"
CTX="${CTX:-32768}"

export LD_LIBRARY_PATH="$HOME/llama.cpp/build/vulkan/bin:$HOME/llama.cpp/build/vulkan/common${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

[ -x "$LLAMA_SERVER" ] || { echo "ERROR: missing $LLAMA_SERVER (rebuild llama.cpp Vulkan)"; exit 1; }
[ -n "$MODEL" ] && [ -f "$MODEL" ] || { echo "ERROR: no F16 GGUF in $MODEL_DIR (convert the BF16 pull first)"; exit 1; }

echo "Serving Hermes-4.3-36B (creative writer) on http://${HOST}:${PORT}"
echo "Model:   $MODEL"
echo "Context: $CTX, all layers on GPU (Vulkan)"

exec "$LLAMA_SERVER" \
    -m "$MODEL" \
    -a hermes-4.3-36b \
    --host "$HOST" \
    --port "$PORT" \
    -ngl 99 \
    -c "$CTX" \
    --jinja \
    --metrics \
    --threads 16 \
    --threads-batch 16