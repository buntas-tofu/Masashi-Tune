#!/usr/bin/env bash
# Serve the 30B math MoE (A3B, the math specialist) via llama.cpp Vulkan
# llama-server.
#
# Relocated 2026-07-08. The dense-capacity boxes are structurally full: each
# carries a ~87GB 120B vessel, so neither holds a stable ~21GB slot for a 30B
# seat. The wake-floor lesson (wake one of {14b, 30b}, never both: the
# 121.7/121.7 freeze) was the tell. A box with small vision seats left ~93GB
# idle, so the math vessel moves to where the room is (architecture over
# lore).
#
# --reasoning-format none is deliberate (carried from the earlier serve,
# tested 2026-06-11): llama-server's token-level deepseek extractor matches
# the model's open think tag but never its close, so the whole reply lands in
# reasoning_content and content arrives empty. The harness splits the raw
# inline tags at the text level instead.
#
# Vulkan over HIP on this iGPU (gfx1151): measurably faster for inference.
# LD_LIBRARY_PATH is required because the Vulkan build's RUNPATH is absolute
# to its original build dir and went stale after a relayout.

set -euo pipefail

MODELS_ROOT="${MODELS_ROOT:-$HOME/models}"
LLAMA_SERVER="${LLAMA_SERVER:-$HOME/llama.cpp/build/vulkan/bin/llama-server}"
MODEL_DIR="${MODEL_DIR:-$MODELS_ROOT/math-30b-moe-gguf}"
# Q8_0 since 2026-08-16 (the re-seat): the quant comp measured Q8 54/58
# against Q4 47/58, the entire gap in raw arithmetic, and a proof-writing
# seat does not get to lose computation to its tier. The Q4 that served the
# old seat is cleared; the cold set holds.
MODEL="${MODEL:-$MODEL_DIR/math-30b-moe.Q8_0.gguf}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8083}"
# CTX raised 32768 -> 131072 (2026-07-23): probe receipts showed competition-grade
# problems overflow 16k of pure thinking with zero answer emitted, and the vendor
# doctrine for this family is 32,768 output for normal work, 81,920 for
# competition math. KV at 131072 is ~12.9GB (48L x 4KV heads x 128 head_dim,
# f16), well inside the box's room beside the vision seats.
CTX="${CTX:-131072}"

# The Vulkan build RUNPATH is absolute to its original build dir; after a
# relayout the shared libs resolve via LD_LIBRARY_PATH instead.
export LD_LIBRARY_PATH="$HOME/llama.cpp/build/vulkan/bin:$HOME/llama.cpp/build/vulkan/common${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

[ -x "$LLAMA_SERVER" ] || { echo "ERROR: missing $LLAMA_SERVER (rebuild llama.cpp Vulkan)"; exit 1; }
[ -f "$MODEL" ]        || { echo "ERROR: missing model $MODEL (stage the 30B GGUF to $MODEL_DIR)"; exit 1; }

echo "Serving math-30b MoE on http://${HOST}:${PORT}"
echo "Model:   $MODEL"
echo "Context: $CTX, all layers on GPU (Vulkan)"
echo "Reasoning: raw think tags (--reasoning-format none; the harness splits at text level)"
echo

exec "$LLAMA_SERVER" \
    -m "$MODEL" \
    -a math-30b-moe \
    --host "$HOST" \
    --port "$PORT" \
    -ngl 99 \
    -c "$CTX" \
    --jinja \
    --reasoning-format none \
    --metrics \
    --threads 16 \
    --threads-batch 16
