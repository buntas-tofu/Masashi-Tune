#!/usr/bin/env bash
# mathalon_q8_reheat.sh: the Q8_0 re-heat (queued by the operator
# 2026-08-12 morning, fires after the 32B closes).
#
# The quant-tier confound, isolated: the lead's 47/58 was a Q4_K_M number
# while Cascade ran BF16 and the guests ran Q8_0/Q6_K. Same weights lineage
# (the published GGUF repo the Q4 build came from), same
# host, same protocol; only the tier moves. The production seat is
# never touched: a transient llama-server rides port 8084 under a systemd
# user unit and is stopped on exit, success or failure.
# Floor: DMF.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BENCH="$HERE/math_bench.py"
HOST="${MATHALON_HOST:-math-bench.example.net}"
SSH_TARGET="${MATHALON_SSH_TARGET:-math-bench}"
SSH7="ssh -o BatchMode=yes -o ConnectTimeout=10 $SSH_TARGET"
Q8="${MATHALON_Q8_MODEL:-/srv/models/quantized/main.Q8_0.gguf}"
SERVE_SCRIPT="${MATHALON_SERVE_SCRIPT:-/srv/fabric/scripts/serve-model.sh}"
BIND_IP="${MATHALON_BIND_IP:-0.0.0.0}"

cleanup() {
    echo "=== cleanup: transient down ==="
    $SSH7 "systemctl --user stop bench-q8" > /dev/null 2>&1 || true
}
trap cleanup EXIT

echo "q8 re-heat: start $(date '+%F %H:%M:%S')"

if ! $SSH7 "test -s $Q8"; then
    echo "!!! Q8 artifact missing at $Q8; pull incomplete. Aborting."
    exit 1
fi

echo "=== transient llama-server on 8084 (Q8_0, production seat untouched) ==="
$SSH7 "systemd-run --user --unit=bench-q8 \
  --setenv=MODEL=$Q8 --setenv=PORT=8084 --setenv=HOST=$BIND_IP \
  $SERVE_SCRIPT"

# -f is load-bearing: only a hard 200 on /health means ready (the 08-12
# lesson; llama.cpp answers 503 on every endpoint while loading).
up=0
for _ in $(seq 1 90); do
    if curl -sf -m 5 "http://$HOST:8084/health" > /dev/null 2>&1; then
        up=1
        break
    fi
    sleep 10
done
if [ "$up" != 1 ]; then
    echo "!!! transient never reached ready on 8084"
    exit 1
fi

echo "=== ready, running the heat ==="
python3 "$BENCH" run --endpoint "http://$HOST:8084" --candidate math-lead-q8 \
    --reads 2 --max-tokens 16384 --timeout 1500
echo "q8 re-heat: done $(date '+%F %H:%M:%S')"
