#!/usr/bin/env bash
# mathalon_night2.sh: the field resumes (2026-08-12, pre-dawn).
#
# Night one measured the resident lead whole and characterized Phi-4
# conclusively in 13
# items: at temperature 0 the reasoning tune cannot stop, 26 of 26 reads to
# the 16384 wall, deterministic loops, 106k tokens per solve. The operator
# ruled the halt "a kindness to the gpu" and the full Phi-4 heat is NOT
# re-run: the pathology is the measurement, and the model stays routed to
# conversational-temperature work where July showed it strong. Night two is
# the OpenMath family, same protocol as night one: serial, one guest at a
# time, temperature 0, two reads, 16384 budget, direct endpoints.
# Floor: DMF.
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
        # -f is load-bearing: llama.cpp binds BEFORE the weights load and
        # answers 503 "Loading model" on every endpoint; bare curl exits 0 on
        # a 503 and the 08-12 pre-dawn run benched three loading servers in
        # 47 seconds. Only a 200 on /health means ready.
        local up=0
        for _ in $(seq 1 90); do
            if curl -sf -m 5 "http://$HOST:$port/health" > /dev/null 2>&1; then
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

echo "mathalon night two: start $(date '+%F %H:%M:%S')"
run_candidate openmath14b 8091 "${SERVICE_PREFIX}openmath14b" || true
run_candidate openmath14b-kaggle 8092 "${SERVICE_PREFIX}openmath14bk" || true
run_candidate openmath32b 8093 "${SERVICE_PREFIX}openmath32b" || true
echo "mathalon night two: done $(date '+%F %H:%M:%S')"
