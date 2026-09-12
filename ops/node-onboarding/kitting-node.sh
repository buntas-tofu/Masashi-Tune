#!/usr/bin/env bash
# Node kitting: bring one fresh node from bare Linux to a fabric-joined box.
# Written against a two-node ARM64 accelerator bring-up, one node at a time.
#
# Scope: a fresh node is lean compute. It carries the DISTRIBUTABLE software
# only (the control plane and the serve tooling), with the runtime tree (model
# weights, personas, memory staging) pushed from the base node as artifacts.
# The umbrella workspace and the sovereign trees are never cloned here;
# distributing those to a node is a per-node ruling.
# Kitting scope: boot, OS baseline, identity, packages, clone, venv. NO seats,
# NO roster edits, NO units enabled. Seat placement and unit enablement are
# separate, later gates.
#
# RUN THIS ON THE NODE ITSELF, not from the base node.
#   Usage:   bash kitting-node.sh <node-name>
#   (pass the node's OWN name as $1; it refuses to run for the wrong name)
#
# Idempotent and re-runnable. No rm -rf anywhere (operator floor).

set -euo pipefail

NODE="${1:?usage: kitting-node.sh <node-name>}"
HOST="$(hostname)"
echo "=== node: $NODE  hostname: $HOST  ($(uname -m)) ==="

if [ "$HOST" != "$NODE" ]; then
  echo "ERROR: this script is for $NODE but you are on $HOST. Run it ON the node."
  exit 1
fi
[ "$(uname -m)" = "aarch64" ] || { echo "WARN: expected aarch64 (GB10), got $(uname -m)"; }

# Deployment-specific values. NODE_USER is the Linux account the fabric runs as;
# REPO_HOST is the ssh alias or hostname of the node hosting the git bares;
# RUNTIME_DIR is the shared runtime mount; REPO_URL is the control-plane clone
# URL; CHECKOUT is where it lands. All are parameters with documented defaults.
USER_BASE="${NODE_USER:-$(id -un)}"
REF="${REPO_HOST:-repo-host}"
RUNTIME_DIR="${RUNTIME_DIR:-/srv/fabric}"
CHECKOUT="${CHECKOUT:-$HOME/fabric}"
REPO_URL="${REPO_URL:-}"

echo
echo "### 0. identity + clock baseline"
sudo timedatectl set-timezone America/New_York
timedatectl | grep -E 'Time zone|synchronized'

echo
echo "### 1. OS + driver parity (match the reference nodes: GB10 class, pinned driver, Ubuntu 24.04)"
. /etc/os-release && echo "image: $PRETTY_NAME"
sudo apt update
sudo apt dist-upgrade -y
echo "driver before:"
nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null || echo "  (no driver yet)"
# DGX OS ships NVIDIA drivers; if nvidia-smi is absent post-upgrade, flag it.
# Firmware: nvfwupd / the DGX update path brings GB10 to parity. Surface, don't guess.
echo "driver parity target: pin the driver the reference nodes run. Re-run nvidia-smi after any reboot."

echo
echo "### 2. kitting packages (the 09-04 list + the tier0 core, ARM-safe)"
sudo apt install -y \
  build-essential git git-lfs curl wget htop rsync iperf3 \
  python3-venv python3-pip python3-dev python-is-python3 \
  ca-certificates gnupg apt-transport-https software-properties-common \
  jq tmux ripgrep fd-find unzip zip xz-utils lsof bash-completion \
  ffmpeg libnuma-dev \
  "linux-headers-$(uname -r)"

echo
echo "### 3. Tailscale (install, then YOU authenticate interactively)"
if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi
tailscale version
echo "--- bring up; the operator authenticates at the printed URL ---"
sudo tailscale up --hostname="$NODE" --accept-dns
echo "--- confirm a DIRECT path to the base node after auth (tailscale status) ---"
tailscale status

echo
echo "### 4. runtime mount, user-owned (recorders fail silently without this)"
sudo mkdir -p "$RUNTIME_DIR"
sudo chown -R "$USER_BASE":"$USER_BASE" "$RUNTIME_DIR"
sudo mkdir -p "$RUNTIME_DIR/memory"
sudo chown -R "$USER_BASE":"$USER_BASE" "$RUNTIME_DIR/memory"

echo
echo "### 5. SSH key to reach the repo host bares (operator authorizes once)"
if [ ! -f "$HOME/.ssh/id_ed25519" ]; then
  ssh-keygen -t ed25519 -N "" -f "$HOME/.ssh/id_ed25519" -C "$NODE"
  echo "PUBLIC KEY (add to the repo host:~/.ssh/authorized_keys):"
  cat "$HOME/.ssh/id_ed25519.pub"
  echo "PAUSE: add the key on the repo host, then press Enter."
  read -r _
fi
# Confirm we can reach the repo host over the tailnet.
ssh -o BatchMode=yes -o ConnectTimeout=6 "$USER_BASE@$REF" 'hostname' \
  && echo "ssh to $REF OK" || { echo "WARN: cannot ssh $REF yet; tailscale auth or key may be pending."; }

echo
echo "### 6. Clone the control plane only (lean distributable)"
# The control-plane repo carries the serve tooling. The umbrella workspace and
# the sovereign trees are NOT cloned here; that is a per-node ruling.
# Set REPO_URL to the control-plane git URL before running.
if [ ! -d "$CHECKOUT/.git" ]; then
  [ -n "$REPO_URL" ] || { echo "ERROR: set REPO_URL to the control-plane git URL"; exit 1; }
  git clone "$REPO_URL" "$CHECKOUT"
else
  echo "control plane already cloned; pulling"
  git -C "$CHECKOUT" pull
fi
echo "--- control plane present ---"
ls -d "$CHECKOUT" && echo "control plane OK (a lean node carries no umbrella)"

echo
echo "### 6b. Stage the runtime dirs (weights/personas/memory arrive as artifacts)"
for d in models personas memory memory/sediment runs cache checkpoints; do
  sudo mkdir -p "$RUNTIME_DIR/$d"
  sudo chown -R "$USER_BASE":"$USER_BASE" "$RUNTIME_DIR/$d"
done
echo "staged: $(ls -d "$RUNTIME_DIR"/*/ | xargs -n1 basename | tr '\n' ' ')"

echo
echo "### 7. Service venv from the lock, proven by import (the 08-03 lesson)"
echo "FABRIC_DEBUG: rebuild-service-venv.sh is at the repo ROOT (not tools/)."
SYS_PY=/usr/bin/python3.12
[ -x "$SYS_PY" ] || { echo "ERROR: $SYS_PY missing"; exit 1; }
UV=""
for p in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" /usr/local/bin/uv; do
  [ -x "$p" ] && UV="$p" && break
done
[ -z "$UV" ] && UV="$(command -v uv 2>/dev/null || true)"
echo "uv: ${UV:-none -> python3 -m venv fallback}"

# The rebuild script lives at the repo root and takes the venv path as its
# first argument. Call it by absolute path.
if [ -x "$CHECKOUT/rebuild-service-venv.sh" ]; then
  "$CHECKOUT/rebuild-service-venv.sh" "$CHECKOUT/.venv"
else
  echo "NOTE: rebuild-service-venv.sh not found at $CHECKOUT; skipping venv."
  echo "      Check the clone landed before re-running."
fi
# Prove the venv imports rather than assuming it (the 08-03 lesson).
"$CHECKOUT/.venv/bin/python" -c "import sys; print('venv OK:', sys.executable)" 2>/dev/null \
  || echo "WARN: venv proof failed; venv may be incomplete."

echo
echo "### 8. paths.env (node absolutes; HARD-OVERRIDES systemd drop-ins)"
CONF_DIR="$HOME/.config/fabric"
mkdir -p "$CONF_DIR"
# NOTE: the reference node carries its paths.env at the same relative location.
if [ ! -f "$CONF_DIR/paths.env" ]; then
  cat > "$CONF_DIR/paths.env" <<EOF
# Per-node path manifest ($NODE).
LLAMA_SERVER=""
MODELS_DIR="$RUNTIME_DIR/models"
EOF
  echo "wrote $CONF_DIR/paths.env (edit LLAMA_SERVER/MODELS_DIR for this node)"
else
  echo "paths.env exists; leaving as-is:"
  cat "$CONF_DIR/paths.env"
fi

echo
echo "### 9. management-plane sanity (what is wired to this node)"
for dev in enP7s7 enp1s0f0np0 enp1s0f1np1; do
  if ip link show "$dev" >/dev/null 2>&1; then
    printf "  %-14s " "$dev"
    ethtool "$dev" 2>/dev/null | grep -E 'Speed|Link detected' | tr '\n' ' '
    echo
  fi
done

echo
echo "### DONE (kitting scope). Later-gate items explicitly NOT done here:"
echo "  - seats, roster edits, units enabled: a later gate"
echo "  - compute-plane switch config: cabling day"
echo "  - fabric addressing: cabling day"
echo
echo "Verify before declaring onboarded: FULL POWER-CYCLE test, then the drift capture."
echo "Record: the node table and the campaign log (those edits stay on the base node)."
