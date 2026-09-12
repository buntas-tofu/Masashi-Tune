#!/usr/bin/env python3
"""Read the night's gauntlet and relay tapes, write the verdict, emit manifests.

Separate from the instruments on purpose. An instrument that grades itself is
the shape of problem this fleet keeps finding, and a reporter that cannot run
without the collector is a reporter that cannot be re-run against old tape.

Floor: DMF. No em dashes, no ellipses.
"""

from __future__ import annotations

import glob
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import manifest as MF  # noqa: E402

RUNS = Path(__file__).resolve().parent / "runs"


def load(pattern):
    """Newest run WINS PER PHASE, and pooling across runs is refused.

    The night produced three e2b tapes: a smoke, the full run, and a re-run of
    ladder and truncation after the ladder was found slicing a 16.6k corpus and
    calling the rungs different. Globbing them together reported 48 ugly cases
    and 6 injections for 24 payloads and 3 injections, and quietly mixed the
    corrected ladder with the broken one. So each phase is taken whole from the
    most recent file that contains it, which is exactly the file that ran that
    phase last, and never spliced across files.
    """
    per_file = {}
    for p in sorted(glob.glob(str(RUNS / pattern))):
        rows = defaultdict(list)
        for line in open(p):
            try:
                d = json.loads(line)
            except Exception:
                continue
            d["_file"] = Path(p).name
            rows[d.get("phase", "?")].append(d)
        per_file[p] = rows
    out = {}
    for p in sorted(per_file):          # ascending, so later overwrites earlier
        for phase, rows in per_file[p].items():
            if rows:
                out[phase] = rows
    return out


def gauntlet_section(vessel):
    g = load(f"gauntlet_{vessel}_*.jsonl")
    if not g:
        return None, None
    ugly = g.get("ugly", [])
    # Only the corrected ladder rows are trustworthy: the first run tiled
    # nothing and fed identical text above 16.6k. Distinguish by whether the
    # rung's own in_chars actually reached what it claimed.
    ladder = [r for r in g.get("ladder", [])]
    trunc = g.get("truncation", [])
    drift = sorted(g.get("drift", []), key=lambda r: r["at_call"])
    grind = g.get("grind", [])

    survived = all(r.get("server_alive_after") for r in ugly) if ugly else None
    loud = [r for r in ugly if not r.get("ok") and r.get("loud")]
    quiet_fail = [r for r in ugly if not r.get("ok") and not r.get("loud")]
    inj = [r for r in ugly if r.get("injection_followed")]

    out = {
        "vessel": vessel,
        "ugly_cases": len(ugly),
        "server_survived_all": survived,
        "loud_refusals": len(loud),
        "silent_failures": len(quiet_fail),
        "injections_followed": len(inj),
        "injection_cases": [r["case"] for r in inj],
        "ladder_max_ok_chars": max([r["in_chars"] for r in ladder
                                    if r.get("ok")] or [0]),
        "ladder_first_fail_chars": min([r["in_chars"] for r in ladder
                                        if not r.get("ok")] or [0]) or None,
        "truncation": [{"in_chars": r["in_chars"], "ptok": r.get("prompt_tokens"),
                        "alpha": r.get("says_alpha"), "omega": r.get("says_omega")}
                       for r in trunc],
        "drift": [{"at": r["at_call"], "byte_identical": r["byte_identical"],
                   "fields_agree": r["fields_agree"], "probes": r["probes"]}
                  for r in drift],
        "grind_calls": max([r["calls"] for r in grind] or [0]),
    }
    if grind:
        secs = [r["secs"] for r in grind if r.get("secs")]
        if secs:
            out["grind_median_s"] = round(statistics.median(secs), 3)
            out["grind_first_s"] = secs[0]
            out["grind_last_s"] = secs[-1]
    return out, g


def relay_section():
    r = load("relay_*.jsonl")
    if not r:
        return None
    prod = r.get("produce", [])
    cons = r.get("consume", [])
    by_seat = defaultdict(list)
    for p in prod:
        if p.get("secs"):
            by_seat[p["seat"]].append(p)

    # Was the reasoner mid-batch when each package was produced? The
    # co-location question needs this join, not a global average.
    windows = [(c["t"] - (c.get("secs") or 0), c["t"]) for c in cons if c.get("secs")]

    def busy(t):
        return any(a <= t <= b for a, b in windows)

    seats = {}
    for seat, rows in by_seat.items():
        hot = [x["secs"] for x in rows if busy(x["t"])]
        cold = [x["secs"] for x in rows if not busy(x["t"])]
        seats[seat] = {
            "produced": len(rows),
            "median_s": round(statistics.median([x["secs"] for x in rows]), 3),
            "median_while_consumer_busy": round(statistics.median(hot), 3) if hot else None,
            "median_while_consumer_idle": round(statistics.median(cold), 3) if cold else None,
            "n_busy": len(hot), "n_idle": len(cold),
            "median_lateness_s": round(statistics.median(
                [x.get("lateness_s", 0) for x in rows]), 3),
        }
    parsed = [c for c in cons if c.get("reply_parsed") is not False]
    asserted = [c for c in cons if c.get("integrity_ok") is not None]
    return {
        "carriers": seats,
        "consumer_batches": len(cons),
        "consumer_median_s": round(statistics.median(
            [c["secs"] for c in cons if c.get("secs")]), 1) if cons else None,
        "queue_max": max([p.get("qdepth", 0) for p in prod] or [0]),
        "handoff_integrity_asserted": len(asserted),
        "handoff_integrity_ok": sum(1 for c in asserted if c.get("integrity_ok")),
        "consumer_replies_unparseable": sum(
            1 for c in cons if c.get("reply_parsed") is False),
        "oldest_wait_max_s": max([c.get("oldest_wait_s", 0) for c in cons] or [0]),
    }


def main() -> int:
    report = {}
    for v in ("e2b", "e4b"):
        sec, _ = gauntlet_section(v)
        if sec:
            report[v] = sec
    rel = relay_section()
    if rel:
        report["relay"] = rel
    print(json.dumps(report, indent=1))

    # Manifests, one per campaign half, through the real emitter.
    if report.get("e2b") or report.get("e4b"):
        arms = [{"arm": f"gauntlet-{v}", "result": {**report[v], "status": "COMPLETE"}}
                for v in ("e2b", "e4b") if report.get(v)]
        raws = sorted(glob.glob(str(RUNS / "gauntlet_*.jsonl")))
        MF.emit({"run": "gauntlet-break-finding",
                 "started": "2026-08-05T23:00:00-04:00",
                 "raw": raws[-1] if raws else None,
                 "instrument": MF.instrument(Path(__file__).parent / "gauntlet.py"),
                 "hardware": MF.hardware(),
                 "serving": {"port": 8089, "gpu": "device=0 (RTX 5090)",
                             "note": "bench instance, production carriers untouched"},
                 "arms": arms})
    if rel:
        raws = sorted(glob.glob(str(RUNS / "relay_*.jsonl")))
        MF.emit({"run": "relay-backpressure",
                 "started": "2026-08-05T23:20:00-04:00",
                 "raw": raws[-1] if raws else None,
                 "instrument": MF.instrument(Path(__file__).parent / "relay.py"),
                 "hardware": MF.hardware(),
                 "serving": {"note": "live production carriers as producers, "
                                     "120B twin as consumer"},
                 "arms": [{"arm": "backpressure", "result": {**rel, "status": "COMPLETE"}}]})
    print("\nmanifests emitted", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
