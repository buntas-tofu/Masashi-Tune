#!/usr/bin/env python3
"""Retrieval-vs-recency bench: does the field surface the event the operator
would have wanted? (synaptic spine section 5, receipt 2 of 3.)

Pure recency serves the last N hours verbatim. The field serves the k events
nearest a query by cosine+recency, whatever their age. This bench asks: for a
set of real queries that map to REAL sediment events, how often does field
retrieval surface the intended event where pure recency (a 12h window) would
have missed it because it is too old?

Method:
  1. Read the last 30 days of sediment.
  2. Build a set of candidate "should-have-been-found" events: consolidation
     (day reports), summon answers, and room.digest entries (the decisions and
     summaries an operator would want recalled), each with a query derived from
     its own text.
  3. For each, record its age. Classify it as OUTSIDE the recency window (older
     than 12h) or INSIDE.
  4. Run field search for the query, check whether the intended ref appears in
     the top-k.
  5. Report: field recall on the OLD tail (the case recency structurally cannot
     serve) and on the recent window (both should serve). A high old-tail recall
     with a working recent window is the receipt the field earns its place.

Receipts land in bench/runs/. Run:
  python bench/spine_phase4_retrieval_vs_recency.py

Floor: DMF. No em dashes, no ellipses. This is an artifact; it carries the
floor in full.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import bench_config as BC

BC.add_runtime_path()

try:
    from fabric_runtime.field import get_field  # noqa: E402
    from fabric_runtime.memory import get_memory  # noqa: E402
except ImportError as _exc:  # noqa: E402
    get_field = get_memory = None
    _RUNTIME_ERR = _exc
else:
    _RUNTIME_ERR = None

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
RUNS.mkdir(parents=True, exist_ok=True)

# A field search per candidate is an embed + a full-index cosine scan, so the
# bench is sampled rather than exhaustive. Sample up to SAMPLE_PER_BAND events
# from each age band (old tail / recent window), which keeps the runtime bounded
# while still exercising both. The recallable set is 6k+ turns, so a sample is
# the honest instrument.
SAMPLE_PER_BAND = 40
RECENCY_HORIZON_S = 12 * 3600.0

# The events worth recalling (the operator-would-want set). The digest/summary
# kinds carry decisions, but the fabric's sediment is dominated by turns and
# tool calls, and the substantive turns ARE what an operator reads back. So the
# candidate set is: consolidation, summon, room.digest, PLUS turn.seat replies
# and turn.user prompts with real substance (not terse markers like "[showed N
# photos]" or empty). A turn with under MIN_TURN_CHARS of text is noise, not a
# recall candidate.
_RECALLABLE_KINDS = ("consolidation", "summon", "room.digest",
                     "turn.seat", "turn.user")
MIN_TURN_CHARS = 40


async def _load_sediment(max_days: int = 30) -> list[dict]:
    mem = get_memory()
    now = time.time()
    events = await mem.reveal(now, horizon_s=86_400 * max_days,
                              max_events=1_000_000)
    out = []
    for ev in events:
        if ev.kind in _RECALLABLE_KINDS:
            if ev.kind in ("turn.seat", "turn.user"):
                text = str(ev.payload.get("text", ""))
                if len(text) < MIN_TURN_CHARS or text.startswith("["):
                    continue
            out.append({"ref": ev.ref, "t": ev.t, "kind": ev.kind,
                        "payload": ev.payload})
    return out


def _query_for(ev: dict) -> str:
    """A natural query someone would type to find this event."""
    p = ev["payload"]
    if ev["kind"] == "consolidation":
        return str(p.get("text", ""))[:120]
    if ev["kind"] == "summon":
        return f"{p.get('prompt', '')} {p.get('answer', '')}"[:120]
    if ev["kind"] == "room.digest":
        return f"{p.get('gist', '')} {p.get('decisions', '')}"[:120]
    if ev["kind"] in ("turn.seat", "turn.user"):
        return str(p.get("text", ""))[:120]
    return str(p.get("text", ""))[:120]


async def main() -> int:
    if get_field is None:
        raise SystemExit(f"{BC.RUNTIME_HINT}: {_RUNTIME_ERR}")
    events = await _load_sediment()
    field = get_field()
    now = time.time()

    # Split into bands and sample each, so both the old tail and the recent
    # window are exercised without a 6k-search run.
    old = [e for e in events if now - e["t"] > RECENCY_HORIZON_S]
    recent = [e for e in events if now - e["t"] <= RECENCY_HORIZON_S]
    # Deterministic sample (stable across runs): step through, not random.
    def _sample(band: list[dict], n: int) -> list[dict]:
        if len(band) <= n:
            return band
        step = len(band) / n
        return [band[int(i * step)] for i in range(n)]

    old_s = _sample(old, SAMPLE_PER_BAND)
    recent_s = _sample(recent, SAMPLE_PER_BAND)
    print(f"sampling {len(old_s)} old / {len(recent_s)} recent of "
          f"{len(old)}/{len(recent)} candidates")

    async def _run_band(band: list[dict]) -> tuple[int, int]:
        hits = 0
        for ev in band:
            q = _query_for(ev)
            if not q.strip():
                continue
            fhits = await field.search(q, k=8)
            if any(h["ref"] == ev["ref"] for h in fhits):
                hits += 1
        return hits, len(band)

    old_hits, old_total = await _run_band(old_s)
    recent_hits, recent_total = await _run_band(recent_s)

    receipt = {
        "bench": "spine_phase4_retrieval_vs_recency",
        "ts": now,
        "recency_horizon_s": RECENCY_HORIZON_S,
        "recallable_events_total": len(events),
        "sampled": {"old": len(old_s), "recent": len(recent_s)},
        "field_rows": field.stats().get("rows"),
        "old_tail": {
            "total": old_total,
            "recall": round(old_hits / old_total, 3) if old_total else None,
            "hits": old_hits,
        },
        "recent_window": {
            "total": recent_total,
            "recall": round(recent_hits / recent_total, 3) if recent_total else None,
            "hits": recent_hits,
        },
        "note": "old_tail.recall is the case recency structurally cannot serve; "
                "a high number with a working recent window is the receipt the "
                "field earns default-on.",
    }
    stamp = time.strftime("%Y%m%dT%H%M%S")
    path = RUNS / f"spine_phase4_retrieval_vs_recency_{stamp}.json"
    path.write_text(json.dumps(receipt, indent=2))

    print(f"recallable events in sediment: {len(events)}")
    print(f"field rows: {field.stats().get('rows')}")
    print(f"OLD tail (>12h):  recall {receipt['old_tail']['recall']} "
          f"({receipt['old_tail']['hits']}/{receipt['old_tail']['total']})")
    print(f"recent window:    recall {receipt['recent_window']['recall']} "
          f"({receipt['recent_window']['hits']}/{receipt['recent_window']['total']})")
    print(f"receipt: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
