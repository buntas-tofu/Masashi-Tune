#!/usr/bin/env bash
# BENCH-STAGED (2026-08-04, the two-card contract session): serve IBM
# granite-guardian-4.1-8b via vLLM docker. The groundedness and tool-call
# auditor; BYOC criteria arrive per call, this only serves the judge. ~18G at
# BF16, so GPU0 by default (tight beside anything else on the second card).
# Same docker-layer GPU pin and bind posture as every guest.
set -euo pipefail

STORE="${STORE:-$HOME/models}"
MODEL_DIR="${MODEL_DIR:-granite-guardian-4.1-8b}"
NAME="${NAME:-granite-guardian-4.1-8b}"
PORT="${PORT:-8091}"
GPU="${GPU:-0}"
TAG="${TAG:-vllm/vllm-openai:v0.20.0}"
HOST="${HOST:-127.0.0.1}"
MAXLEN="${MAXLEN:-8192}"
# Shared-card rule (learned by the OCR canary): a guest sharing a card MUST
# pass an explicit pool, or vLLM takes 0.9 of the card for any model.
GPUMEM="${GPUMEM:-0.75}"

[ -d "$STORE/$MODEL_DIR" ] || { echo "ERROR: no model at $STORE/$MODEL_DIR"; exit 1; }

echo "Serving $NAME (bench guest, GPU $GPU) on http://${HOST}:${PORT}"

exec docker run --rm --name "serve-guardian8b" \
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
