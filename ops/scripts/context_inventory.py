#!/usr/bin/env python3
"""context_inventory: list every session/room a node's sediment holds, with
sizes, turn counts, kinds, and time windows.

Input:  {node?, max_rooms?, since?, sediment?}
Output: {rooms: [{id, turns, events, bytes, first_t, last_t, kinds}], total}
Read-only: reads the sediment spine only, writes nothing.
Self-contained so the managed runner can execute it as a subprocess from the
shelf with no sibling imports.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path


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


def _iso_to_t(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).timestamp()
    except (ValueError, TypeError):
        return None


def run(args):
    base = args.get("sediment") or os.path.expanduser(
        os.environ.get("FLEET_MEMORY_DIR", "~/memory"))
    root = Path(base) / "sediment" if not str(base).endswith("sediment") else Path(base)
    since_t = _iso_to_t(args.get("since"))
    try:
        max_rooms = int(args.get("max_rooms", 1000))
    except (ValueError, TypeError):
        max_rooms = 1000
    rooms = {}
    if root.exists():
        for p in sorted(root.glob("*.jsonl")):
            try:
                with open(p, encoding="utf-8") as f:
                    for line in f:
                        try:
                            ev = json.loads(line)
                        except (json.JSONDecodeError, ValueError):
                            continue
                        t = ev.get("t")
                        kind = ev.get("kind", "")
                        if since_t and (not isinstance(t, (int, float)) or t < since_t):
                            continue
                        room = ev.get("room") or ev.get("session") or "_none"
                        r = rooms.setdefault(room, {
                            "id": room, "turns": 0, "events": 0, "bytes": 0,
                            "first_t": None, "last_t": None, "kinds": {}})
                        r["events"] += 1
                        r["bytes"] += len(line.encode("utf-8"))
                        r["kinds"][kind] = r["kinds"].get(kind, 0) + 1
                        if kind == "room.turn":
                            r["turns"] += 1
                        if isinstance(t, (int, float)):
                            if r["first_t"] is None or t < r["first_t"]:
                                r["first_t"] = t
                            if r["last_t"] is None or t > r["last_t"]:
                                r["last_t"] = t
            except OSError:
                continue
    room_list = sorted(rooms.values(), key=lambda r: -r["events"])[:max_rooms]
    return {"rooms": room_list, "total": len(rooms), "read_only": True}


def main():
    print(json.dumps(run(_parse_args(sys.argv[1:])), ensure_ascii=False))


if __name__ == "__main__":
    main()
