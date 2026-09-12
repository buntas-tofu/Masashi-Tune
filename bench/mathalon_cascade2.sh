#!/usr/bin/env bash
# mathalon_cascade2.sh: the Cascade-2 bring-up and heat (2026-08-11).
#
# The never-benched star served as BF16 straight off the local
# model shelf, no quant, on the house vLLM stack. The resident heavy
# seat rests
# for the window and is ALWAYS restored on exit, success or failure; the trap
# is the contract. Port 8010 so nothing collides with the seat's 8000.
# Floor: DMF.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BENCH="$HERE/math_bench.py"
HOST="${MATHALON_HOST:-math-bench.example.net}"
SSH_TARGET="${MATHALON_SSH_TARGET:-math-bench}"
SSHF="ssh -o BatchMode=yes -o ConnectTimeout=10 $SSH_TARGET"
HOST_IP="${MATHALON_HOST_IP:-0.0.0.0}"
MODEL_MOUNT="${MATHALON_CASCADE_MODEL:-/srv/models/nemotron-cascade-2-30b-a3b}"
RESIDENT_UNIT="${MATHALON_RESIDENT_UNIT:-resident-dispatch}"

restore() {
    echo "=== restore: cascade down, resident back ==="
    $SSHF "docker stop cascade2-bench" > /dev/null 2>&1 || true
    $SSHF "systemctl --user start $RESIDENT_UNIT" || true
}
trap restore EXIT

echo "cascade2 leg: start $(date '+%F %H:%M:%S')"
echo "=== resting the resident ==="
$SSHF "systemctl --user stop $RESIDENT_UNIT"

echo "=== launching cascade2 (BF16, 59G, off the model shelf) ==="
$SSHF "docker run -d --rm --name cascade2-bench --gpus all --ipc=host \
  --shm-size=16g \
  -v $MODEL_MOUNT:/model \
  -v \$HOME/.cache/huggingface:/root/.cache/huggingface \
  -p $HOST_IP:8010:8000 vllm/vllm-openai:v0.20.0 \
  --model /model --served-model-name cascade2 --host 0.0.0.0 --port 8000 \
  --tensor-parallel-size 1 --dtype auto --kv-cache-dtype fp8 \
  --mamba-ssm-cache-dtype float32 --gpu-memory-utilization 0.70 \
  --max-model-len 32768 --trust-remote-code --enable-chunked-prefill"

up=0
for _ in $(seq 1 120); do
    if curl -s -m 5 "http://$HOST:8010/v1/models" > /dev/null 2>&1; then
        up=1
        break
    fi
    sleep 10
done
if [ "$up" != 1 ]; then
    echo "!!! cascade2 never came up inside 20 minutes; bring-up FAILED."
    echo "!!! That is a finding, not a mystery: the quant path activates."
    $SSHF "docker logs cascade2-bench 2>&1 | tail -30" || true
    exit 1
fi

echo "=== bring-up GOOD, running the heat ==="
python3 "$BENCH" run --endpoint "http://$HOST:8010" \
    --candidate cascade2-30b-a3b --reads 2 --max-tokens 16384 --timeout 1500
echo "cascade2 leg: done $(date '+%F %H:%M:%S')"
