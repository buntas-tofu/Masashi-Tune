#!/usr/bin/env bash
# The overnight of 2026-08-03 into 08-04: four birds, one stone.
#
# Bird 1  the E4B question, which is currently open on a single run per build
# Bird 2  extended run testing on the chair's two seats, never measured
# Bird 3  setlisting, the phased model rotation, never exercised
# Bird 4  operations content as the workload, in the drama-free window between
#         mission three processing passes
#
# Sequential by design. Both bench cards share one box, one PCIe complex and one
# power envelope, so running the setlist and the sustained test at the same time
# would confound both. Phase 1 owns the 5090 while the 4090 idles; phase 2 owns
# the 4090 while the 5090 idles. Telemetry spans both, which is what makes the
# two halves comparable to each other and to an earlier twin capture.
#
# Nothing here touches a live seat's configuration. The setlist runs its own
# llama-server on the idle GPU, bound to loopback on a bench port, registered
# nowhere. The live seats serve untouched throughout.
#
# Floor: DMF. No em dashes, no ellipses.
set -uo pipefail

BENCH="${BENCH_DIR:-$HOME/bench}"
RUNS="$BENCH/runs"
TAG="2026-08-04"
LOG="$RUNS/overnight_${TAG}.log"
VENV="${BENCH_VENV:-$HOME/.venv/bin/activate}"

SETLIST_UNTIL="00:45"     # phase 1 hard stop
SUSTAIN_UNTIL="05:15"     # phase 2 hard stop, ahead of the 05:52 report
TELEMETRY_HOURS=6.5

mkdir -p "$RUNS"
# shellcheck disable=SC1090
[ -f "$VENV" ] && . "$VENV"

say() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

say "=== overnight $TAG starting ==="
say "phase 1 setlist until $SETLIST_UNTIL, phase 2 sustained until $SUSTAIN_UNTIL"

# ---------------------------------------------------------------- telemetry
# Spans the whole night so the thermal and clock curve covers both phases. Same
# instrument that proved the GB10 does not throttle, so the bench numbers land
# beside the earlier twin numbers in the same units.
TELEM="$RUNS/fleet_telemetry_${TAG}.jsonl"
say "starting telemetry -> $TELEM"
nohup python3 "$BENCH/fleet_telemetry.py" "$TELEM" 30 "$TELEMETRY_HOURS" \
  >> "$RUNS/telemetry_${TAG}.log" 2>&1 &
TELEM_PID=$!
say "telemetry pid $TELEM_PID"

# ---------------------------------------------------------------- phase 1
say "--- phase 1: setlist, 4 phases on the 5090 ---"
python3 "$BENCH/setlist.py" run --until "$SETLIST_UNTIL" >> "$LOG" 2>&1
say "phase 1 exit $?"

# The bench server is stopped by setlist.py itself, but never assume: phase 2
# measures a card that must have nothing else on it, and a leaked llama-server
# would quietly invalidate the entire sustained measurement.
if pgrep -f "llama-server.*port 8090" > /dev/null 2>&1; then
  say "WARNING: bench server still alive on 8090, killing it"
  pkill -f "llama-server.*port 8090"
  sleep 5
fi
say "5090 clear: $(nvidia-smi --query-gpu=index,memory.used --format=csv,noheader | tr '\n' ' ')"

# ---------------------------------------------------------------- phase 2
say "--- phase 2: sustained load, both seats on the 4090 ---"
SUSTAIN="$RUNS/sustained_${TAG}.jsonl"
python3 "$BENCH/sustained.py" run --until "$SUSTAIN_UNTIL" --out "$SUSTAIN" \
  >> "$LOG" 2>&1
say "phase 2 exit $?"

# ---------------------------------------------------------------- report
say "--- writing the report ---"
REPORT="$RUNS/OVERNIGHT_${TAG}.md"
{
  echo "# Overnight $TAG: the setlist, the E4B question, and the chair under load"
  echo
  echo "Generated $(date '+%Y-%m-%d %H:%M'). Unattended run, four"
  echo "objectives, sequential phases. Floor: DMF. Labeled inference."
  echo
  echo "## Phase 1: the setlist"
  echo
  python3 "$BENCH/setlist.py" report 2>&1
  echo
  echo "## Phase 2: sustained load"
  echo
  if [ -f "$SUSTAIN" ]; then
    python3 "$BENCH/sustained.py" report "$SUSTAIN" 2>&1
  else
    echo "No sustained run on disk. Phase 2 did not produce output, which is a"
    echo "finding and not an absence: check $LOG."
  fi
  echo
  echo "## Telemetry"
  echo
  if [ -s "$TELEM" ]; then
    echo "\`$TELEM\`, $(wc -l < "$TELEM") samples at 30s across the fleet."
  else
    echo "Telemetry produced no samples. UNKNOWN rather than clean."
  fi
} > "$REPORT" 2>&1
say "report at $REPORT"

# Telemetry outlives the phases by design; stop it once the report is written.
if kill -0 "$TELEM_PID" 2>/dev/null; then
  kill "$TELEM_PID" 2>/dev/null
  say "telemetry stopped"
fi

say "=== overnight $TAG complete ==="
