#!/usr/bin/env python3
"""The relay: a carrier spinning on a tight cycle until a 120B is ready to take it.

Operator directive 2026-08-05 night, and the question is his exactly: "have we
been looping against a tight frequency cycle with real data where the loop is
asked to continue spinning until a bigger model is ready to accept the package?"

The answer was no. Every loop this fabric has run was a producer talking to
itself: fixed sample, fixed cadence, no consumer, nothing downstream that could
be slower than the producer. This one has a consumer that is roughly two orders
of magnitude slower, which is the actual deployed shape of the fabric and the
condition under which real systems fail.

THE ROLES, stated because the operator asked that the synapse role be reinforced
in the output rather than left implicit (2026-08-05, off the minis re-scope):

  CARRIER (gemma-4-E2B, the familiars). Takes a record, produces a BOUNDED tag,
  hands the package off, and DUMPS. It holds nothing between records. Its job is
  volume and schema-fidelity, never judgment. This is the synapse layer.
  REASONER (a large reasoning model). Accepts accumulated packages and
  does the thing a carrier must never be asked to do: judge across them.

WHAT IS ACTUALLY UNDER TEST is not throughput, which is arithmetic and known in
advance. It is three questions a soak cannot answer:

  1. BACKPRESSURE. The producer outruns the consumer by design. Does the carrier
     degrade while it spins against a consumer that will not take delivery, or
     does it hold its cycle indifferent to the queue behind it.
  2. CADENCE FIDELITY. Asked to hold a tight fixed interval rather than to run
     flat out, can it, and what is the jitter. A loop that cannot hold a cycle
     cannot be scheduled against.
  3. HANDOFF INTEGRITY. The package the reasoner receives is byte-identical to
     what the carrier produced. A relay that quietly corrupts in transit is the
     failure nobody instruments for, because both ends look healthy.

The carriers used here are the LIVE production seats under gate 4's soak, on
purpose. Read load is what a carrier is for, it does not reset the soak clock,
and testing the deployed article beats testing a bench copy of it.

Usage: relay.py [--minutes N] [--cadence SECONDS] [--consumer reasoner]

Floor: DMF. No em dashes, no ellipses.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import queue
import statistics
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import setlist  # noqa: E402
import bench_config as BC  # noqa: E402

RUNS = Path(__file__).resolve().parent / "runs"

# Carriers and the reasoner are deployment parameters: one host:port per node
# in BENCH_NODES (BENCH_NODE_HOSTS), and BENCH_REASONER_URL for the consumer.
CARRIERS = [
    {"node": n, "seat": f"carrier-{i + 1}", "url": f"http://{h}"}
    for i, (n, h) in enumerate(zip(BC.nodes(), BC.node_hosts()))
] or [{"node": "local", "seat": "carrier-1", "url": "http://127.0.0.1:8085"}]
REASONERS = {"reasoner": BC.env("BENCH_REASONER_URL", "http://127.0.0.1:8000")}

STOP = threading.Event()
PKGS: "queue.Queue" = queue.Queue()


def post(url, body, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode(errors="replace"))
    msg = (d.get("choices") or [{}])[0].get("message", {}) or {}
    return msg.get("content") or "", time.time() - t0


def carrier_loop(carrier, records, cadence, sink, lock, stats):
    """One carrier, holding a fixed cycle, dumping after every record."""
    spec = setlist.TASKS["operations"]
    head = spec.get("head", setlist.HEAD_CHARS)
    i = 0
    next_at = time.time()
    while not STOP.is_set():
        next_at += cadence
        rec = records[i % len(records)]
        i += 1
        t_sched = next_at
        # Cadence fidelity: how late were we to our own slot, before any work.
        lateness = time.time() - t_sched
        try:
            text, secs = post(f"{carrier['url']}/v1/chat/completions",
                              {"messages": [{"role": "user",
                                             "content": spec["prompt"] % rec["text"][:head]}],
                               "max_tokens": setlist.MAX_TOKENS,
                               "temperature": setlist.TEMPERATURE,
                               "stream": False}, timeout=120)
            parsed = setlist.parse_reply(text)
            pkg = {"seat": carrier["seat"], "node": carrier["node"],
                   "rec": rec["id"], "n": i, "produced_at": time.time(),
                   "payload": setlist.norm_fields(parsed) if parsed else None,
                   "raw_sha": hashlib.sha256(text.encode()).hexdigest()[:12]}
            PKGS.put(pkg)
            row = {"phase": "produce", "seat": carrier["seat"], "n": i,
                   "secs": round(secs, 3), "parsed": parsed is not None,
                   "lateness_s": round(lateness, 3),
                   "qdepth": PKGS.qsize(), "t": time.time()}
            with lock:
                stats[carrier["seat"]].append((secs, PKGS.qsize()))
        except Exception as e:
            row = {"phase": "produce", "seat": carrier["seat"], "n": i,
                   "ok": False, "error": f"{type(e).__name__}: {e}",
                   "lateness_s": round(lateness, 3), "qdepth": PKGS.qsize(),
                   "t": time.time()}
        with lock:
            with sink.open("a") as f:
                f.write(json.dumps(row) + "\n")
        slack = next_at - time.time()
        if slack > 0:
            STOP.wait(slack)
        else:
            # Missed the slot. Do not try to catch up by firing back to back,
            # which would turn a cadence test into a flat-out test.
            next_at = time.time()


def reasoner_loop(url, batch, sink, lock):
    """The slow consumer. Takes delivery only when it is free, which is the
    whole point: everything upstream must cope with that."""
    n = 0
    while not STOP.is_set():
        pkgs = []
        deadline = time.time() + 20
        while len(pkgs) < batch and time.time() < deadline and not STOP.is_set():
            try:
                pkgs.append(PKGS.get(timeout=1))
            except queue.Empty:
                pass
        if not pkgs:
            continue
        n += 1
        depth_at_accept = PKGS.qsize()
        digest = [{"rec": p["rec"], "seat": p["seat"], "payload": p["payload"]}
                  for p in pkgs]
        prompt = ("You are the reasoner accepting a batch of tag packages from "
                  "the fabric's carrier seats. Reply with JSON only: "
                  '{"packages_seen": <int>, "distinct_seats": <int>, '
                  '"note": "<one short sentence>"}\n\nPACKAGES:\n'
                  + json.dumps(digest)[:12000])
        row = {"phase": "consume", "batch": n, "packages": len(pkgs),
               "qdepth_at_accept": depth_at_accept,
               "oldest_wait_s": round(time.time() - min(p["produced_at"] for p in pkgs), 1),
               "t": time.time()}
        try:
            # 2500, not 400. Nemotron is a reasoning vessel and a small budget
            # is spent entirely on reasoning, leaving content empty. Run A hit
            # this on 2 of 3 batches and, worse, the empty replies scored as
            # integrity FAILURES because unparseable and miscounted were folded
            # into one boolean. They are different events: one is the reasoner
            # not answering, the other is the relay corrupting a package. Only
            # the second is an integrity finding, so they are separated below.
            text, secs = post(f"{url}/v1/chat/completions",
                              {"model": "nemotron-3-super",
                               "messages": [{"role": "user", "content": prompt}],
                               "max_tokens": 2500, "temperature": 0.0,
                               "stream": False}, timeout=600)
            parsed = setlist.parse_reply(text)
            claimed = (parsed or {}).get("packages_seen")
            row.update(ok=True, secs=round(secs, 1),
                       reply_parsed=parsed is not None,
                       claimed_packages=claimed,
                       # None means "not asserted", never "failed".
                       integrity_ok=(str(claimed) == str(len(pkgs)))
                       if parsed is not None else None,
                       out_chars=len(text or ""),
                       note=str((parsed or {}).get("note"))[:120])
        except Exception as e:
            row.update(ok=False, error=f"{type(e).__name__}: {e}")
        with lock:
            with sink.open("a") as f:
                f.write(json.dumps(row) + "\n")
        print(f"  batch {n}: took {len(pkgs)} pkgs, q={depth_at_accept}, "
              f"{row.get('secs')}s, integrity={row.get('integrity_ok')}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=90)
    ap.add_argument("--cadence", type=float, default=2.0)
    ap.add_argument("--batch", type=int, default=12)
    ap.add_argument("--consumer", choices=list(REASONERS), default="reasoner")
    a = ap.parse_args()

    records, digest = setlist.load_sample("operations")
    sink = RUNS / f"relay_{setlist.stamp()}.jsonl"
    lock = threading.Lock()
    stats = {c["seat"]: [] for c in CARRIERS}

    print(f"relay: {len(CARRIERS)} carriers at {a.cadence}s cadence -> "
          f"{a.consumer} in batches of {a.batch}, {a.minutes} min, "
          f"sink {sink.name}", flush=True)

    threads = [threading.Thread(target=carrier_loop,
                               args=(c, records, a.cadence, sink, lock, stats),
                               daemon=True) for c in CARRIERS]
    threads.append(threading.Thread(target=reasoner_loop,
                                    args=(REASONERS[a.consumer], a.batch, sink, lock),
                                    daemon=True))
    for t in threads:
        t.start()

    end = time.time() + a.minutes * 60
    try:
        while time.time() < end:
            time.sleep(30)
            with lock:
                line = " ".join(f"{s}={len(v)}" for s, v in stats.items())
            print(f"  [{int(end - time.time())}s left] q={PKGS.qsize()} {line}",
                  flush=True)
    except KeyboardInterrupt:
        pass
    STOP.set()
    for t in threads:
        t.join(timeout=30)

    with lock:
        summary = {"phase": "summary", "queue_final": PKGS.qsize(),
                   "digest": digest[:16], "cadence_s": a.cadence,
                   "consumer": a.consumer, "t": time.time()}
        for s, v in stats.items():
            if v:
                lat = [x[0] for x in v]
                summary[s] = {"produced": len(v),
                              "median_s": round(statistics.median(lat), 3),
                              "p95_s": round(sorted(lat)[int(len(lat) * .95) - 1], 3)}
        with sink.open("a") as f:
            f.write(json.dumps(summary) + "\n")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
