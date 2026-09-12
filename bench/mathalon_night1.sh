#!/usr/bin/env bash
# mathalon_night1.sh: the math bench night driver (2026-08-11).
#
# Serial by the house rule: the heap-heavy model is never resident beside
# both compact guests. The math lead is resident and goes
# first; each guest is woken by its unit, polled up, benched at the full
# instrument, then put back to sleep before the next wakes. A guest that
# fails to wake or bench is logged and skipped, never fatal to the night.
#
# Protocol per MATH_BENCH_DESIGN.md: temperature 0, two reads, 16384 budget
# (the floor policy of 2026-07-23), direct endpoints, one candidate on
# the node at a time. Floor: DMF.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BENCH="$HERE/math_bench.py"
HOST="${MATHALON_HOST:-math-bench.example.net}"
SSH_TARGET="${MATHALON_SSH_TARGET:-math-bench}"
SERVICE_PREFIX="${MATHALON_SERVICE_PREFIX:-bench-}"
SSH7="ssh -o BatchMode=yes -o ConnectTimeout=10 $SSH_TARGET"

run_candidate() {
    local name=$1 port=$2 unit=${3:-}
    echo "=== $(date '+%H:%M:%S') $name (port $port) ==="
    if [ -n "$unit" ]; then
        if ! $SSH7 "systemctl --user start $unit"; then
            echo "!!! $name: wake failed, skipping"
            return 1
        fi
        local up=0
        for _ in $(seq 1 90); do
            if curl -s -m 5 "http://$HOST:$port/v1/models" > /dev/null 2>&1; then
                up=1
                break
            fi
            sleep 10
        done
        if [ "$up" != 1 ]; then
            echo "!!! $name: never answered on $port, sleeping it and skipping"
            $SSH7 "systemctl --user stop $unit" || true
            return 1
        fi
    fi
    python3 "$BENCH" run --endpoint "http://$HOST:$port" --candidate "$name" \
        --reads 2 --max-tokens 16384 --timeout 1500
    local rc=$?
    if [ -n "$unit" ]; then
        $SSH7 "systemctl --user stop $unit" || true
        sleep 5
    fi
    return $rc
}

echo "mathalon night: start $(date '+%F %H:%M:%S')"
run_candidate math-lead 8083 || true
run_candidate phi4rp 8090 "${SERVICE_PREFIX}phi4rp" || true
run_candidate openmath14b 8091 "${SERVICE_PREFIX}openmath14b" || true
run_candidate openmath14b-kaggle 8092 "${SERVICE_PREFIX}openmath14bk" || true
run_candidate openmath32b 8093 "${SERVICE_PREFIX}openmath32b" || true
echo "mathalon night: done $(date '+%F %H:%M:%S')"
