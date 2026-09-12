#!/usr/bin/env python3
"""memory_hygiene: a read-only hygiene REPORT over the memory spine: duplicates,
stale rooms, malformed entries, and excluded kinds. The report is read_only=true
and performs NO remediation; a separate gated read_only=false variant would do
epoch-split / quarantine moves, never rm -rf (plan rule 12).

Input:  {node?, horizon_s?, sediment?}
Output: {counts, duplicates:[{a,b}], stale:[{ref,last_t}], malformed:[{ref}],
         exclusions:[{ref,reason}]}
"""
import json
import os
import sys
import time
from pathlib import Path

STALE_DEFAULT_S = 86400 * 30          # 30 days
EXCLUDED_KINDS = ("tag", "reveal.viewed", "reveal.pushed")  # not subject to hygiene


def _parse_args(argv):
    if len(argv) == 1 and argv[0].lstrip().startswith("{"):
        try:
            d = json.loads(argv[0])
            if isinstance(d, dict):
                return d
        except (json.JSONDecodeError, ValueError):
            pass
    out = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            key = a[2:]
            if "=" in key:
                k, v = key.split("=", 1)
                out[k] = v
            else:
                v = argv[i + 1] if i + 1 < len(argv) else True
                out[key] = v
                i += 1
        else:
            out.setdefault("_pos", []).append(a)
        i += 1
    return out


def run(args):
    base = args.get("sediment") or os.path.expanduser(
        os.environ.get("FLEET_MEMORY_DIR", "~/memory"))
    root = Path(base) / "sediment" if not str(base).endswith("sediment") else Path(base)
    try:
        horizon_s = float(args.get("horizon_s", STALE_DEFAULT_S))
    except (ValueError, TypeError):
        horizon_s = STALE_DEFAULT_S
    now = time.time()
    duplicates = []
    malformed = []
    exclusions = []
    seen = {}
    last_by_room = {}
    total = 0
    if root.exists():
        for p in sorted(root.glob("*.jsonl")):
            try:
                with open(p, encoding="utf-8") as f:
                    for line_no, line in enumerate(f, 1):
                        ref = f"{p.name}:{line_no}"
                        total += 1
                        try:
                            ev = json.loads(line)
                        except (json.JSONDecodeError, ValueError):
                            malformed.append({"ref": ref})
                            continue
                        if not isinstance(ev, dict):
                            malformed.append({"ref": ref})
                            continue
                        kind = ev.get("kind", "")
                        if kind in EXCLUDED_KINDS:
                            exclusions.append({"ref": ref, "reason": f"kind {kind} excluded"})
                            continue
                        key = json.dumps({"kind": kind,
                                          "payload": ev.get("payload", {})},
                                         sort_keys=True)
                        if key in seen:
                            duplicates.append({"a": seen[key], "b": ref})
                        else:
                            seen[key] = ref
                        t = ev.get("t")
                        room = ev.get("room") or ev.get("session") or "_none"
                        if isinstance(t, (int, float)):
                            last_by_room[room] = max(last_by_room.get(room, 0), t)
            except OSError:
                continue
    stale = [{"ref": room, "last_t": lt}
             for room, lt in last_by_room.items() if now - lt > horizon_s]
    return {
        "counts": {"total_events": total, "duplicates": len(duplicates),
                   "stale": len(stale), "malformed": len(malformed),
                   "exclusions": len(exclusions)},
        "duplicates": duplicates, "stale": stale,
        "malformed": malformed, "exclusions": exclusions,
        "read_only": True, "remediated": False,
    }


def main():
    print(json.dumps(run(_parse_args(sys.argv[1:])), ensure_ascii=False))


if __name__ == "__main__":
    main()
