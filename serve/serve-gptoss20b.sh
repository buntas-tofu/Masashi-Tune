#!/usr/bin/env bash
# BENCH-STAGED (2026-08-04, the two-card contract session): serve gpt-oss-20b
# (MXFP4, 3.6B active) via vLLM docker. The smoke characterizes what reasoning
# looks like through this serve BEFORE any scored use, then the vessel's
# reasoning_format is set honestly. Fits either card; GPU0 default.
set -euo pipefail

STORE="${STORE:-$HOME/models}"
MODEL_DIR="${MODEL_DIR:-gpt-oss-20b}"
NAME="${NAME:-gpt-oss-20b}"
PORT="${PORT:-8092}"
GPU="${GPU:-0}"
TAG="${TAG:-vllm/vllm-openai:v0.20.0}"
HOST="${HOST:-127.0.0.1}"
MAXLEN="${MAXLEN:-32768}"
# Shared-card rule (learned by the OCR canary): a guest sharing a card MUST
# pass an explicit pool, or vLLM takes 0.9 of the card for any model.
GPUMEM="${GPUMEM:-0.75}"

[ -d "$STORE/$MODEL_DIR" ] || { echo "ERROR: no model at $STORE/$MODEL_DIR"; exit 1; }

echo "Serving $NAME (bench guest, GPU $GPU) on http://${HOST}:${PORT}"

exec docker run --rm --name "serve-gptoss20b" \
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
