#!/usr/bin/env python3
"""event_correlate: correlate events across surfaces by shared IDs/refs
(event_id, action_id, room, seat, timestamp): for example a memory event to the
tool call that caused it to the model response.

Input:  {seed, events?, max_events?, horizon_s?, surface?}
Output: {root, edges: [{from, to, via, t}], max_events, count}
Read-only. The ad-hoc cousin of session_reconstruct for cross-surface chains.
"""
import json
import os
import sys
from pathlib import Path

# Payload keys that carry shared correlation ids across surfaces.
_ID_KEYS = ("event_id", "action_id", "room", "seat", "turn_id", "ref")


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


def _event_ids(ev):
    """The set of shared id values an event exposes."""
    ids = set()
    for k in ("id", "ref"):
        v = ev.get(k)
        if v is not None:
            ids.add(str(v))
    payload = ev.get("payload", {})
    if isinstance(payload, dict):
        for k in _ID_KEYS:
            v = payload.get(k)
            if v is not None:
                ids.add(str(v))
        # a where-axis ref inside payload e.g. "2026-08-29.jsonl:412"
        ev_ref = payload.get("ref") or payload.get("event_id")
        if ev_ref is not None:
            ids.add(str(ev_ref))
    return ids


def _load_events(sediment):
    evs = []
    root = Path(sediment) / "sediment" if not str(sediment).endswith("sediment") else Path(sediment)
    if root.exists():
        for p in sorted(root.glob("*.jsonl")):
            try:
                with open(p, encoding="utf-8") as f:
                    for line_no, line in enumerate(f, 1):
                        try:
                            ev = json.loads(line)
                        except (json.JSONDecodeError, ValueError):
                            continue
                        ev.setdefault("id", f"{p.name}:{line_no}")
                        ev.setdefault("ref", f"{p.name}:{line_no}")
                        evs.append(ev)
            except OSError:
                continue
    return evs


def run(args):
    seed = str(args.get("seed", ""))
    events = args.get("events")
    if events is None:
        events = _load_events(args.get("sediment") or os.path.expanduser(
            os.environ.get("FLEET_MEMORY_DIR", "~/memory")))
    try:
        max_events = int(args.get("max_events", 50))
    except (ValueError, TypeError):
        max_events = 50
    events = list(events)[:max_events]

    root_ids = {seed}
    root_event = next((e for e in events if e.get("id") == seed
                       or e.get("ref") == seed), None)
    if root_event is not None:
        root_ids |= _event_ids(root_event)

    edges = []
    root_edges = []
    for ev in events:
        evids = _event_ids(ev)
        shared = evids & root_ids
        if shared:
            via = sorted(shared)[0]
            root_edges.append({"from": seed, "to": ev.get("id") or ev.get("ref"),
                               "via": via, "t": ev.get("t")})
    # chain edges: events that correlate with each other through a shared id
    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            if len(edges) >= max_events:
                break
            shared = _event_ids(events[i]) & _event_ids(events[j])
            if shared:
                edges.append({"from": events[i].get("id") or events[i].get("ref"),
                              "to": events[j].get("id") or events[j].get("ref"),
                              "via": sorted(shared)[0],
                              "t": events[j].get("t")})
        if len(edges) >= max_events:
            break
    all_edges = (root_edges + edges)[:max_events]
    return {"root": seed, "edges": all_edges, "max_events": max_events,
            "count": len(all_edges), "read_only": True}


def main():
    print(json.dumps(run(_parse_args(sys.argv[1:])), ensure_ascii=False))


if __name__ == "__main__":
    main()
