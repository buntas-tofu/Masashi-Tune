#!/usr/bin/env bash
# BENCH-STAGED (2026-08-04, the two-card contract session): serve NVIDIA
# llama-nemotron-embed-1b-v2 via vLLM docker. Embedding endpoints, no chat:
# the RAG lane's 8192-token embedder beside the small retrieval layer. The
# --task flag is the v0.20 pooling spelling; if the tag steps forward, re-read
# the new tag's --help before trusting it (flag names have moved between vLLM
# lines before).
# v0.20.0 NOTE (smoked 2026-08-05): this tag has no --task flag at all,
# it aborts at argparse. The pooling contract on this tag is
# --runner pooling, with --convert auto-detecting embed or classify
# from the model config. Discovered by the rung 2 smoke, not the docs.
set -euo pipefail

STORE="${STORE:-$HOME/models}"
MODEL_DIR="${MODEL_DIR:-llama-nemotron-embed-1b-v2}"
NAME="${NAME:-llama-nemotron-embed-1b-v2}"
PORT="${PORT:-8094}"
GPU="${GPU:-1}"
TAG="${TAG:-vllm/vllm-openai:v0.20.0}"
HOST="${HOST:-127.0.0.1}"
MAXLEN="${MAXLEN:-8192}"
# Shared-card rule (learned by the OCR canary): a guest sharing a card MUST
# pass an explicit pool, or vLLM takes 0.9 of the card for any model.
GPUMEM="${GPUMEM:-0.30}"

[ -d "$STORE/$MODEL_DIR" ] || { echo "ERROR: no model at $STORE/$MODEL_DIR"; exit 1; }

echo "Serving $NAME (bench guest, GPU $GPU, embed) on http://${HOST}:${PORT}"

exec docker run --rm --name "serve-nemotron-embed" \
  --gpus "device=${GPU}" \
  --ipc=host \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
  -v "$STORE":/models:ro \
  -p "${HOST}:${PORT}:8000" \
  "$TAG" \
  --model "/models/${MODEL_DIR}" \
  --served-model-name "$NAME" \
  --runner pooling \
  --trust-remote-code \
  --gpu-memory-utilization "$GPUMEM" \
  --max-model-len "$MAXLEN"
