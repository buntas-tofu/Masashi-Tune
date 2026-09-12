#!/usr/bin/env bash
# node-onboard.sh: one-stop onboarding for a new lightweight node. Run with sudo.
# Fetches the node kit from the kit host, offers the rename, then runs hardening
# and enrollment. This box has no sshd and keeps none.
#
# KIT_URL points at the host serving the kit artifacts. Default is a placeholder;
# set it to the real kit host before running.
set +e
cd /tmp || exit 1
KIT_URL="${KIT_URL:-http://kit-host:8123}"
curl -fsSO "$KIT_URL/node_harden.sh" || { echo "fetch failed: node_harden.sh"; exit 1; }
curl -fsSO "$KIT_URL/04_node_onboard.sh" || { echo "fetch failed: 04_node_onboard.sh"; exit 1; }
echo "current hostname: $(hostname)"
read -r -p "New hostname (the reveal), or blank to keep: " NEWNAME
if [ -n "$NEWNAME" ]; then hostnamectl set-hostname "$NEWNAME" && echo "christened: $NEWNAME (agent and tailnet pick it up)"; fi
bash /tmp/node_harden.sh
bash /tmp/04_node_onboard.sh
echo "ALL DONE: this machine now reports to the fleet keeper as $(hostname)"
