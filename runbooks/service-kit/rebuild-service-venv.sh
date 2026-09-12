#!/usr/bin/env bash
# rebuild-service-venv.sh - rebuild a service venv on the STABLE system python,
# decoupled from any package manager's managed-interpreter lifecycle.
#
# Why: a venv built on a uv-managed standalone python is fragile. If uv
# relocates or garbage-collects that interpreter, or the venv directory is
# removed, a running service becomes a zombie (alive on deleted files) that
# dies on the next restart or reboot. A venv built on the system python is
# immune, because the interpreter is not managed by a tool that can move it.
#
# Usage:  rebuild-service-venv.sh <venv-path> <pkg> [<pkg>]+
# Example (a keeper and a view, two co-dependent services on one venv):
#         rebuild-service-venv.sh "$HOME/runtime/.venv" registry view
#
# Each <pkg> is installed editable from <this-dir>/<pkg>. Everything is
# constrained to the lock file beside this script. After running, restart the
# affected *.service units and verify with check-service-venvs.sh.
set -euo pipefail

VENV="${1:?usage: rebuild-service-venv.sh <venv-path> <pkg> [<pkg>]+}"; shift
[ "$#" -gt 0 ] || { echo "need at least one package"; exit 2; }
PKGS=("$@")

# The system interpreter. Override SYS_PY to pin a different system python.
SYS_PY="${SYS_PY:-/usr/bin/python3.12}"
ROOT="$(cd "$(dirname "$0")" && pwd)"        # the repo root: this script's directory
LOCK="${LOCK:-$ROOT/service-venv.lock}"

# uv installs to ~/.local/bin and is absent from the non-login PATH; find it.
UV=""
for p in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" /usr/local/bin/uv; do
  [ -x "$p" ] && UV="$p" && break
done
[ -z "$UV" ] && UV="$(command -v uv 2>/dev/null || true)"

echo "venv:   $VENV"
echo "python: $SYS_PY ($("$SYS_PY" --version))"
echo "pkgs:   ${PKGS[*]}"
echo "uv:     ${UV:-none -> python3 -m venv fallback}"

EARGS=(); for pkg in "${PKGS[@]}"; do EARGS+=(-e "$ROOT/$pkg"); done
CARGS=(); [ -f "$LOCK" ] && { CARGS=(-c "$LOCK"); echo "lock:   $LOCK"; }

rm -rf "$VENV"
if [ -n "$UV" ]; then
  "$UV" venv --python "$SYS_PY" "$VENV"
  "$UV" pip install --python "$VENV/bin/python" "${EARGS[@]}" "${CARGS[@]}"
else
  "$SYS_PY" -m venv "$VENV"
  "$VENV/bin/pip" install -qU pip
  "$VENV/bin/pip" install "${EARGS[@]}" "${CARGS[@]}"
fi

set +e
echo "--- result ---"
grep -E 'home|version_info' "$VENV/pyvenv.cfg"
IMPORTS="$(IFS=,; echo "${PKGS[*]}")"
"$VENV/bin/python" -c "import $IMPORTS" && echo "imports OK: $IMPORTS" || echo "WARN: import check failed"
