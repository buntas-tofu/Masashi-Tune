#!/usr/bin/env bash
# Serve Nemotron-3-Nano-Omni-30B NVFP4 via vLLM docker on the primary card.
# Seated lazy; the serve shape is the vision bench's receipt: 300 tok/s, 0.61s
# TTFT on a 22k prompt, 29.4 GiB seated at 0.86 pool.
# WAKE GATE: 21G weights do not fit beside the resident vision vessel, so this
# serves only in a declared window with the resident vessel stopped. The unit
# does not enforce that; the summoner declares the window.
set -euo pipefail

STORE="${STORE:-$HOME/models}"
MODEL_DIR="${MODEL_DIR:-nemotron-3-nano-omni-30b-nvfp4}"
NAME="${NAME:-nano-omni}"
PORT="${PORT:-8003}"
GPU="${GPU:-0}"   # nvidia-smi ordering: 0 is the primary card
TAG="${TAG:-vllm/vllm-openai:v0.20.0}"
HOST="${HOST:-127.0.0.1}"
MAXLEN="${MAXLEN:-32768}"
# Shared-card rule: a guest MUST pass an explicit pool or vLLM takes 0.9.
GPUMEM="${GPUMEM:-0.86}"

[ -d "$STORE/$MODEL_DIR" ] || { echo "ERROR: no model at $STORE/$MODEL_DIR"; exit 1; }

echo "Serving $NAME (burst tongue, GPU $GPU) on http://${HOST}:${PORT}"

exec docker run --rm --name "serve-nano-omni" \
  --gpus "device=${GPU}" \
  --ipc=host --shm-size=8g \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
  -v "$STORE":/models:ro \
  -p "${HOST}:${PORT}:8000" \
  "$TAG" \
  --model "/models/${MODEL_DIR}" \
  --served-model-name "$NAME" \
  --gpu-memory-utilization "$GPUMEM" \
  --max-model-len "$MAXLEN" \
  --max-num-seqs 2 \
  --kv-cache-dtype fp8 \
  --mamba-ssm-cache-dtype float32 \
  --reasoning-parser nemotron_v3 \
  --trust-remote-code
