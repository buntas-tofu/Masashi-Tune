#!/usr/bin/env bash
# fleet-apt: package currency across the fabric, without shuffling keyboards.
#
# Born 2026-07-26. The operator keeps the main box current by hand and the passive
# nodes drift, because updating them meant physically moving a keyboard and a dongle
# to each machine. Every node runs Ubuntu 24.04 and every node is on the tailnet, so
# the keyboard was never the necessary part.
#
# THE IDEA. Do not filter dangerous packages at apply time; that has to be
# remembered correctly every single time. Instead make the dangerous set
# DECLARATIVE with `apt-mark hold`, so it persists on the node, is visible with
# `apt-mark showhold`, and makes a plain `apt upgrade` inherently safe. The risky
# path then requires a deliberate unhold, which is exactly the friction it deserves.
#
# WHY A HOLD CLASS AT ALL. These boxes serve. An unattended nvidia or kernel bump
# can desync a running driver from its loaded module and take seats down mid-inference,
# and it is the same instinct as the standing vLLM rule: controlled bring-up beside
# the live seat, never an in-place clobber.
#
# Floor: DMF. No em dashes, no ellipses. Read-only unless you ask otherwise.

set -uo pipefail

# The fleet, by SSH alias. FLEET_NODES matches the shared ops convention
# (fleet_config.py): a comma-separated list of node names, reached by ssh alias,
# each alias carrying its own user. Never hardcode another node's home path or
# username. The default is the neutral example set, which reaches nothing real.
# The local node is detected at runtime so the script runs from any node; the
# local snippet still runs in this shell, since a node may keep sudo behind a
# password.
FLEET_NODES="${FLEET_NODES:-example-a,example-b,example-c}"
ALL_NODES=()
while IFS= read -r n; do [ -n "$n" ] && ALL_NODES+=("$n"); done \
    < <(printf '%s\n' "$FLEET_NODES" | tr ',' '\n')
LOCAL_NODE="$(hostname)"
NODES=()
for n in "${ALL_NODES[@]}"; do [ "$n" = "$LOCAL_NODE" ] || NODES+=("$n"); done

# The held class: anything that touches the serving stack. Matched against package
# names as a prefix set. Kernel, NVIDIA userspace and modules, CUDA, ROCm, AMDGPU.
# xserver-xorg-video-nvidia and -amdgpu are driver stack but start with neither
# nvidia- nor libnvidia-, so the first version of this pattern walked straight past
# them. They stayed put only because their held dependencies blocked them, which is
# luck rather than policy. Anything that can desync a running driver belongs here.
HOLD_PATTERN='^(linux-image|linux-headers|linux-modules|linux-generic|linux-nvidia|nvidia-|libnvidia-|cuda|libcuda|rocm|hip-|amdgpu|libamdgpu|xserver-xorg-video-nvidia|xserver-xorg-video-amdgpu)'

ssh_do() { ssh -o ConnectTimeout=12 -o BatchMode=yes "$1" "$2" 2>/dev/null; }

# Runs a snippet on every node, local included, labelled. Local runs in this shell.
each_node() {
  local snippet="$1"
  for n in "${NODES[@]}"; do
    printf '%s\t' "$n"
    ssh_do "$n" "$snippet" || printf 'UNREACHABLE\n'
  done
  printf '%s\t' "$LOCAL_NODE"
  bash -c "$snippet"
}

cmd_report() {
  echo "# Fleet apt report"
  echo
  echo "Zero privilege: reads each node's existing apt cache, refreshed by"
  echo "apt-daily.timer. Nothing is updated or installed by this command."
  echo
  echo "| node | release | kernel | pending | of which HELD-CLASS | on hold | reboot | u-u |"
  echo "|---|---|---|---:|---:|---:|---|---|"
  local snippet
  snippet='
    rel=$(lsb_release -rs 2>/dev/null)
    kern=$(uname -r)
    up=$(apt list --upgradable 2>/dev/null | tail -n +2 | grep -c .)
    # sort -u before counting: apt lists some packages once per architecture, which
    # inflated one node to 19 against 14 real packages and read like an unheld gap.
    risky=$(apt list --upgradable 2>/dev/null | tail -n +2 | cut -d/ -f1 \
            | grep -E "'"$HOLD_PATTERN"'" | sort -u | grep -c .)
    held=$(apt-mark showhold 2>/dev/null | grep -c .)
    rb=$(test -f /var/run/reboot-required && echo YES || echo no)
    # is-enabled prints "not-found" on stdout AND exits non-zero for a missing
    # unit, so a bare `|| echo none` emits two lines and splits the table row.
    uu=$(systemctl is-enabled unattended-upgrades 2>/dev/null | head -1)
    [ -z "$uu" ] && uu=none
    printf "%s | %s | %s | %s | %s | %s | %s\n" "$rel" "$kern" "$up" "$risky" "$held" "$rb" "$uu"
  '
  each_node "$snippet" | sed 's/^/| /; s/\t/ | /; s/$/ |/'
}

cmd_hold() {
  echo "Applying the hold policy. Serving-stack packages become apt-mark hold on"
  echo "each node, so a plain upgrade can no longer touch them."
  echo
  local snippet
  snippet='
    pkgs=$(apt list --upgradable 2>/dev/null | tail -n +2 | cut -d/ -f1 \
           | grep -E "'"$HOLD_PATTERN"'" | sort -u)
    # Hold what is INSTALLED and matches, not merely what is pending, so the policy
    # holds steady across future releases rather than only todays queue.
    # The $ in ${Package} MUST stay escaped: the snippet is re-evaluated by the
    # receiving shell, which would otherwise expand it to nothing and silently
    # match zero installed packages. It did exactly that on the first run, leaving
    # 30 ROCm packages on one node unheld while reporting "nothing to hold".
    # No apostrophes in these comments: the snippet is single-quoted and one
    # would terminate the string early.
    inst=$(dpkg-query -W -f "\${Package}\n" 2>/dev/null \
           | grep -E "'"$HOLD_PATTERN"'" | sort -u)
    # Skip already-installed VERSIONED kernel artifacts. Holding
    # linux-image-6.17.0-1026-nvidia protects nothing, because that exact version
    # is never what upgrades; the meta package is. They only clutter showhold,
    # and showhold being legible is the whole point of doing it this way.
    all=$(printf "%s\n%s\n" "$pkgs" "$inst" | sort -u | grep . \
          | grep -vE "^linux-(image|headers|modules|tools|objects)-[0-9]")
    [ -z "$all" ] && { echo "nothing to hold"; exit 0; }
    before=$(apt-mark showhold 2>/dev/null | grep -c .)
    echo "$all" | xargs -r sudo -n apt-mark hold >/dev/null 2>&1
    after=$(apt-mark showhold 2>/dev/null | grep -c .)
    # Report the measured outcome, never the exit code. xargs splits a long list
    # into several apt-mark calls and the pipeline inherits only the last status,
    # which on the first run printed FAILED for nodes that had just held 154
    # packages successfully. Misreporting success as failure is the worse
    # direction to be wrong in, so count what actually changed.
    if [ "$after" -gt "$before" ]; then
      echo "held $((after - before)) new, $after on hold total"
    elif [ "$after" -eq "$before" ] && [ "$after" -gt 0 ]; then
      echo "already current, $after on hold"
    else
      echo "NOTHING HELD (check sudo)"
    fi
  '
  each_node "$snippet" | sed 's/\t/: /'
}

cmd_upgrade() {
  echo "Safe upgrade across the passive nodes. Held packages are skipped by apt"
  echo "itself, so nothing in the serving stack moves. The local node is NOT"
  echo "included: it is the operator's own box and may keep sudo behind a password."
  echo
  for n in "${NODES[@]}"; do
    echo "=== $n ==="
    ssh_do "$n" '
      sudo -n apt-get update -qq 2>/dev/null
      sudo -n DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq 2>&1 | tail -5
      echo "  remaining pending: $(apt list --upgradable 2>/dev/null | tail -n +2 | grep -c .)"
      test -f /var/run/reboot-required && echo "  REBOOT REQUIRED"
    ' || echo "  UNREACHABLE"
  done
}

cmd_held() {
  echo "# What is deliberately held back"
  echo
  echo "These need a maintenance window: drain the node's seats, unhold, upgrade,"
  echo "reboot, verify the board. Never during live inference."
  echo
  local snippet
  snippet='
    echo
    apt-mark showhold 2>/dev/null | sed "s/^/    held: /" | head -20
    apt list --upgradable 2>/dev/null | tail -n +2 | cut -d/ -f1 \
      | grep -E "'"$HOLD_PATTERN"'" | sort -u | sed "s/^/    pending: /" | head -20
  '
  each_node "$snippet" | sed 's/\t/:/'
}

case "${1:-report}" in
  report)  cmd_report ;;
  hold)    cmd_hold ;;
  upgrade) cmd_upgrade ;;
  held)    cmd_held ;;
  *) cat <<EOF
fleet-apt: package currency across the fabric.

  report   (default) zero-privilege census of pending updates per node
  hold     make the serving stack (kernel, nvidia, cuda, rocm) apt-mark hold
  upgrade  safe upgrade of the passive nodes; holds protect the serving stack
  held     show what is held and what is pending behind the hold

Order of operations on a fresh fleet: report, then hold, then upgrade.
Driver and kernel work is deliberate and separate: drain seats, unhold, upgrade,
reboot, verify the board.
EOF
    exit 1 ;;
esac
