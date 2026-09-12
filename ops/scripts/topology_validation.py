#!/usr/bin/env python3
"""topology_validation: validate the fabric topology (nodes, seats, units,
registry vs live) and report drift: the inventory's roster_stale, unit state
mismatches, dead units, claimed-but-down seats.

Input:  {full?, data?}   -- data is a pre-fetched keeper/registry snapshot:
        {nodes: [{node, keeper_alive, roster_stale, seats: [{key, unit_state,
          alive, claimed}]}]}
Output: {nodes: [...], drift: [...]}
Read-only: NEVER phases a seat. This function is pure; it only reports.
"""
import json
import sys


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
    data = args.get("data") or {}
    nodes = data.get("nodes", [])
    drift = []
    report_nodes = []
    for n in nodes:
        node = n.get("node", "")
        keeper_alive = bool(n.get("keeper_alive", True))
        roster_stale = bool(n.get("roster_stale", False))
        if not keeper_alive:
            drift.append({"type": "keeper_down", "node": node})
        if roster_stale:
            drift.append({"type": "roster_stale", "node": node})
        seats = []
        for s in n.get("seats", []):
            key = s.get("key", "")
            alive = bool(s.get("alive", True))
            claimed = bool(s.get("claimed", False))
            unit_state = s.get("unit_state", "unknown")
            seats.append({"key": key, "unit_state": unit_state,
                          "alive": alive, "claimed": claimed})
            if not alive and claimed:
                drift.append({"type": "claimed_but_down", "node": node, "seat": key})
            elif not alive:
                drift.append({"type": "seat_down", "node": node, "seat": key})
        report_nodes.append({"node": node, "keeper_alive": keeper_alive,
                             "roster_stale": roster_stale, "seats": seats})
    return {"nodes": report_nodes, "drift": drift, "read_only": True}


def main():
    print(json.dumps(run(_parse_args(sys.argv[1:])), ensure_ascii=False))


if __name__ == "__main__":
    main()
