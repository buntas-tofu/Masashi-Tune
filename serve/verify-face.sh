#!/usr/bin/env bash
# verify-face.sh: walk the rungs of a distributed vLLM face and report a verdict.
#
# Read-only by design. Every rung reports; none of them rewrites anything.
# Exit 0 when every rung passes, 1 when any rung fails or cannot be decided.
#
# Rungs, cheapest first:
#   1  API health
#   2  served model id and configured context
#   3  container running on each node
#   4  ray sees the expected number of nodes
#   5  KV cache usage and request totals (informational)
#
# Environment (all optional, neutral defaults):
#   FACE_HOST    host serving the API            default 127.0.0.1
#   FACE_PORT    port serving the API            default 8000
#   FACE_NODES   space separated ssh hosts       default empty (rungs 3 and 4 skip)
#   CONTAINER    container name on each node     default vllm_node
#   EXPECT_MODEL substring the model id must carry  default empty (rung 2 notes only)
#   RAY_MIN      minimum active ray nodes        default 0 (rung 4 checks only when set)
#
# A rung that cannot be decided reports UNKNOWN, never PASS. A screen that fails
# open while answering success is worse than no screen.

set -u

FACE_HOST="${FACE_HOST:-127.0.0.1}"
FACE_PORT="${FACE_PORT:-8000}"
FACE_NODES="${FACE_NODES:-}"
CONTAINER="${CONTAINER:-vllm_node}"
EXPECT_MODEL="${EXPECT_MODEL:-}"
RAY_MIN="${RAY_MIN:-0}"
SSH_OPTS="-o ConnectTimeout=6 -o BatchMode=yes"

fails=0
unknowns=0

pass() { printf 'PASS   %-12s %s\n' "$1" "$2"; }
fail() { printf 'FAIL   %-12s %s\n' "$1" "$2"; fails=$((fails + 1)); }
note() { printf 'NOTE   %-12s %s\n' "$1" "$2"; }
unkn() { printf 'UNKNOWN %-11s %s\n' "$1" "$2"; unknowns=$((unknowns + 1)); }

BASE="http://${FACE_HOST}:${FACE_PORT}"

# 1. health
code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "${BASE}/health" 2>/dev/null)"
case "$code" in
  200) pass health "200 from ${BASE}/health" ;;
  000) fail health "no answer from ${BASE}/health" ;;
  *)   fail health "HTTP ${code} from ${BASE}/health" ;;
esac

# 2. model id and context
models="$(curl -s --max-time 8 "${BASE}/v1/models" 2>/dev/null)"
if [ -z "$models" ]; then
  fail model "no body from ${BASE}/v1/models"
else
  mid="$(printf '%s' "$models" | tr -d '\n' | grep -o '"data":\[{"id":"[^"]*"' | sed 's/.*"id":"//; s/"$//' | head -1)"
  mlen="$(printf '%s' "$models" | sed -n 's/.*"max_model_len":\([0-9]*\).*/\1/p' | head -1)"
  if [ -n "$mid" ]; then
    pass model "id ${mid} max_model_len ${mlen:-unknown}"
    if [ -n "$EXPECT_MODEL" ]; then
      case "$mid" in
        *"$EXPECT_MODEL"*) pass model-match "id contains ${EXPECT_MODEL}" ;;
        *) fail model-match "id ${mid} does not contain ${EXPECT_MODEL}" ;;
      esac
    fi
    case "$mid" in
      /*) note model-name "id is a filesystem path; clients inherit the node layout" ;;
    esac
  else
    fail model "could not parse a model id from the response"
  fi
fi

# 3 and 4. container and ray, per node
if [ -z "$FACE_NODES" ]; then
  note container "skipped, FACE_NODES not set"
  note ray "skipped, FACE_NODES not set"
else
  running=""
  for n in $FACE_NODES; do
    state="$(ssh $SSH_OPTS "$n" "docker inspect -f '{{.State.Running}}' '$CONTAINER'" 2>/dev/null)"
    case "$state" in
      true)  running="$running $n" ;;
      false) fail container "$n: container '$CONTAINER' exists but is not running" ;;
      *)     fail container "$n: no container '$CONTAINER' or no ssh access" ;;
    esac
  done
  [ -n "$running" ] && pass container "running on:${running}"

  # ray status from any reachable node; the cluster view is shared
  raynode=""
  for n in $FACE_NODES; do
    raynode="$n"; break
  done
  status="$(ssh $SSH_OPTS "$raynode" "docker exec '$CONTAINER' ray status" 2>/dev/null)"
  if [ -z "$status" ]; then
    unkn ray "could not read ray status from ${raynode}"
  else
    active="$(printf '%s\n' "$status" | sed -n '/^Active:/,/^$/p' | grep -c 'node_')"
    if [ "$RAY_MIN" -gt 0 ] 2>/dev/null; then
      if [ "$active" -ge "$RAY_MIN" ]; then
        pass ray "${active} active nodes (minimum ${RAY_MIN})"
      else
        fail ray "${active} active nodes, expected at least ${RAY_MIN}"
      fi
    else
      note ray "${active} active nodes (set RAY_MIN to enforce)"
    fi
  fi
fi

# 5. KV usage and request totals, informational
metrics="$(curl -s --max-time 8 "${BASE}/metrics" 2>/dev/null)"
if [ -z "$metrics" ]; then
  note metrics "no metrics endpoint on ${BASE}"
else
  kv="$(printf '%s\n' "$metrics" | grep '^vllm:kv_cache_usage_perc' | awk '{print $2}' | head -1)"
  reqs="$(printf '%s\n' "$metrics" | grep '^vllm:request_success_total' | awk '{s+=$2} END {print s+0}')"
  note metrics "kv_cache_usage ${kv:-unknown} requests_served ${reqs:-0}"
fi

printf -- '---\n%s failure(s), %s undecided\n' "$fails" "$unknowns"
[ "$fails" -eq 0 ] && exit 0
exit 1
