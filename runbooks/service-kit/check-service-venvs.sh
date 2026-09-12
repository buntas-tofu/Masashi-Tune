#!/usr/bin/env bash
# check-service-venvs.sh - the corrected zombie detector for service venvs.
#
# Why: checking /proc/<pid>/exe for "(deleted)" MISSES a service whose venv was
# removed while its interpreter (a shared managed python living OUTSIDE the venv)
# survives. The process looks healthy but its code and entry script are gone,
# so it dies on the next restart. The honest check: does the binary systemd
# would re-exec actually exist on disk?
#
# Run locally, or fan out:  ssh <node> 'bash -s' < check-service-venvs.sh
# Exit 1 if any active service is a hidden zombie (its ExecStart binary missing).
#
# UNIT_PATTERN restricts the scan to this deployment's service names. The
# default covers the common trio: a keeper, a registry, a view.
set -uo pipefail
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
UNIT_PATTERN="${UNIT_PATTERN:-keeper|registry|view}"

echo "### $(hostname) ###"
units=$(systemctl --user list-units --type=service --all --plain --no-legend 2>/dev/null \
  | grep -ioE '[a-z0-9_.-]+\.service' | grep -iE "$UNIT_PATTERN" | sort -u)
[ -z "$units" ] && { echo "(no matching user services)"; exit 0; }

rc=0
for u in $units; do
  active=$(systemctl --user is-active "$u" 2>/dev/null)
  es=$(systemctl --user show "$u" -p ExecStart --value 2>/dev/null | grep -oE '/[^ ;]+' | head -1)
  [ -z "$es" ] && { echo "$u: active=$active (no ExecStart)"; continue; }
  [ -e "$es" ] && bx="bin-OK" || bx="bin-MISSING"
  vroot=$(dirname "$(dirname "$es")")
  [ -d "$vroot" ] && vd="venv-OK" || vd="venv-GONE"
  flag=""
  if [ "$active" = "active" ] && [ ! -e "$es" ]; then flag="  <<< HIDDEN-ZOMBIE (dies on restart)"; rc=1; fi
  echo "$u: active=$active | $bx | $vd | $es$flag"
done
exit "$rc"
