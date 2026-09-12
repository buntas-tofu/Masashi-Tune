#!/usr/bin/env bash
# Mirror every sovereign bare from the hub to the NAS, verify each mirrored
# bare with git fsck, and write a receipt beside the mirror and in the logs.
#
# Standing rule: refresh the backup mirror after a bare gains commits worth a
# second copy.
#
# Usage:  ops/mirror_bares.sh            (mirror, fsck, receipt)
#         ops/mirror_bares.sh --dry-run  (rsync -n, no receipt)
#
# Additive by default: a bare deleted on the hub is NOT deleted on the NAS
# (a mirror that follows deletions is a replica, not a backup). Pass --prune
# for a deliberate reconciliation.
set -euo pipefail

HUB="${HUB:-repo-hub}"                 # ssh alias of the host carrying the bares
SRC="${SRC:-/srv/repos/}"              # source directory on that host
NAS_MOUNT="${NAS_MOUNT:-/mnt/backup}"  # local mount of the backup store
DST="${DST:-$NAS_MOUNT/repos/}"
LOGS="${LOGS_DIR:-$HOME/logs}"

mountpoint -q "$NAS_MOUNT" || { echo "backup store not mounted at $NAS_MOUNT" >&2; exit 1; }
ssh -o BatchMode=yes -o ConnectTimeout=8 "$HUB" "test -d $SRC" \
  || { echo "hub unreachable or $SRC missing on $HUB" >&2; exit 1; }

DRY=0; ARGS=()
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1; ARGS+=(-n) ;;
    --prune)   ARGS+=(--delete-after) ;;
    *)         ARGS+=("$a") ;;
  esac
done

# A network mount may not carry POSIX perms or hardlinks faithfully; -rlt is
# what such a mount can keep, and git bares need no more than that to be
# cloneable.
rsync -rlt --itemize-changes "${ARGS[@]+"${ARGS[@]}"}" "$HUB:$SRC" "$DST"
[ "$DRY" = 1 ] && { echo "dry run, no receipt"; exit 0; }

STAMP="$(date +%Y-%m-%dT%H:%M:%S%z)"
RECEIPT="$DST/MIRROR_RECEIPT.md"
{
  echo "# Sovereign bares mirror receipt"
  echo
  echo "- taken: $STAMP on $(hostname)"
  echo "- source: $HUB:$SRC"
  echo "- destination: $DST"
  echo "- tool: ops/mirror_bares.sh"
  echo
  echo "| bare | hub HEAD | mirror HEAD | fsck |"
  echo "|---|---|---|---|"
} > "$RECEIPT.tmp"
fail=0
for d in "$DST"*.git; do
  name=$(basename "$d")
  hub_head=$(ssh -o BatchMode=yes "$HUB" "git -C $SRC$name rev-parse --short HEAD 2>/dev/null || echo none")
  mir_head=$(git -C "$d" rev-parse --short HEAD 2>/dev/null || echo none)
  if git -C "$d" fsck --no-progress --connectivity-only >/dev/null 2>&1; then v=clean; else v=FAIL; fail=1; fi
  [ "$hub_head" = "$mir_head" ] || v="$v (HEAD differs)"
  echo "| $name | $hub_head | $mir_head | $v |" >> "$RECEIPT.tmp"
done
mv "$RECEIPT.tmp" "$RECEIPT"
mkdir -p "$LOGS"; cp "$RECEIPT" "$LOGS/bares-mirror-latest.md"
echo "receipt: $RECEIPT (copy at $LOGS/bares-mirror-latest.md)"
[ "$fail" = 0 ] || { echo "at least one mirrored bare failed fsck" >&2; exit 2; }
