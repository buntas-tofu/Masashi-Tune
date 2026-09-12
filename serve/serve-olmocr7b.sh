#!/usr/bin/env bash
# BENCH-STAGED (2026-08-04, the two-card contract session): serve olmOCR-2-7B
# FP8 via vLLM docker.
# THE sm_120 CANARY: the pinned tag is proven only for a raw matmul, so this
# script's first successful serve IS the verification the bring-up called for.
# If sm_120 is unserved, step the tag forward per the vllm-currency routine,
# controlled bring-up, never in-place.
# GPU pinned at the docker layer with --gpus device=N (nvidia-smi index; the
# in-container CUDA order is NOT bus order, the 2026-08-01 install lesson).
# Bind posture: 127.0.0.1 by default; set HOST to expose.
set -euo pipefail

STORE="${STORE:-$HOME/models}"
MODEL_DIR="${MODEL_DIR:-olmocr-2-7b-fp8}"
NAME="${NAME:-olmocr-2-7b-fp8}"
PORT="${PORT:-8087}"
GPU="${GPU:-0}"
TAG="${TAG:-vllm/vllm-openai:v0.20.0}"
HOST="${HOST:-127.0.0.1}"
MAXLEN="${MAXLEN:-16384}"
# Shared-card rule (learned by the OCR canary): a guest sharing a card MUST
# pass an explicit pool, or vLLM takes 0.9 of the card for any model.
GPUMEM="${GPUMEM:-0.50}"

[ -d "$STORE/$MODEL_DIR" ] || { echo "ERROR: no model at $STORE/$MODEL_DIR"; exit 1; }

echo "Serving $NAME (bench guest, GPU $GPU) on http://${HOST}:${PORT}"

exec docker run --rm --name "serve-olmocr7b" \
  --gpus "device=${GPU}" \
  --ipc=host \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
  -v "$STORE":/models:ro \
  -p "${HOST}:${PORT}:8000" \
  "$TAG" \
  --model "/models/${MODEL_DIR}" \
  --served-model-name "$NAME" \
  --gpu-memory-utilization "$GPUMEM" \
  --max-model-len "$MAXLEN"
