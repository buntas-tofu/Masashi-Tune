#!/usr/bin/env python3
"""Sustained load on the chair's two seats, and whether they hold.

The 2026-08-02 capture proved the GB10 does not throttle: a twin GPU node held 96 percent
utilisation for 4.7 hours with its median clock at hour four equal to hour zero.
That licensed scheduling a long campaign on a twin at its first-hour rate. The
same measurement has never been taken on the primary node, so
every scheduling assumption about it is currently inference.

This works two seats together, continuously, until a wall-clock deadline.
Both live on the 4090 (CUDA_VISIBLE_DEVICES=1 on both units), so the question is
not just whether one seat holds; it is whether two seats sharing one card hold
each other up, which is the configuration the chair actually runs.

METHOD, and the constraints are inherited rather than invented.

  serial within a seat   llama.cpp serves one slot on a context shared between
                         prompt and generation. Concurrency there starves rather
                         than parallelises and once cost this fabric 35 of 35
                         batches. Each seat therefore has exactly one call in
                         flight at a time.
  parallel across seats  The two seats run at once, because that IS the
                         configuration under test. Contention between them is
                         the measurement, not a confound.
  the same 120 records   the frozen setlist sample, looped. Reusing a fixed set
                         means a latency change over the night is the machine
                         changing, never the work getting harder.
  temperature 0          so a quality drift is the seat drifting rather than the
                         sampler wandering.

WHAT WOULD COUNT AS A FINDING. Median latency rising across half-hour windows,
error rate climbing, or parse rate decaying. What would count as a clean result
is all three flat from the first window to the last, which is what licenses
scheduling an unattended campaign on this node at its first-hour rate.

Usage:
  sustained.py run --until HH:MM [--out PATH]
  sustained.py report <jsonl>

Floor: DMF. No em dashes, no ellipses.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import threading
import time
import urllib.request
from pathlib import Path

import bench_config as BC

HERE = Path(__file__).resolve().parent
SAMPLE = HERE / "anchors" / "operations_content_v1.json"
RUNS = BC.runs_dir()

HOST = BC.env("BENCH_HOST", "127.0.0.1")  # the bench host, from the environment
CHAT = f"http://{HOST}:8085"
EMBED = f"http://{HOST}:8086"
EMBED_MODEL = "embeddinggemma-300M-Q8_0.gguf"

MAX_TOKENS = 1500                 # budget for the thinking, not just the answer
TEMPERATURE = 0.0

PROMPT = """You are reading the opening text of one document from a document archive.

Reply with JSON and nothing else, in exactly this form:
{"record_type": "...", "program": "...", "dates": ["..."]}

record_type: what kind of document this is, in two or three words. Use the string
"unknown" if the text does not say.
program: the program, survey, system or office the document concerns, in
the document's own wording. Use the string "unknown" if the text does not name one.
dates: every date the text asserts, copied exactly as written. Use an empty list
if the text states none.

THE DOCUMENT:
---
%s
---
"""


def now():
    return dt.datetime.now()


def parse_reply(text):
    s = (text or "").strip()
    if s.startswith("```"):
        parts = s.split("```")
        s = parts[1] if len(parts) > 1 else s
        s = s[4:] if s.lower().startswith("json") else s
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        d = json.loads(s[a:b + 1])
    except Exception:
        return None
    return d if isinstance(d, dict) else None


def post(url, payload, timeout=300):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode(errors="replace"))
    return d, time.time() - t0


def chat_worker(records, deadline, out, lock, stats):
    i = 0
    while now() < deadline:
        rec = records[i % len(records)]
        i += 1
        row = {"seat": "chat", "t": now().isoformat(timespec="seconds"),
               "relpath": rec["relpath"], "i": i}
        try:
            d, secs = post(f"{CHAT}/v1/chat/completions", {
                "messages": [{"role": "user", "content": PROMPT % rec["head"]}],
                "max_tokens": MAX_TOKENS, "temperature": TEMPERATURE,
                "stream": False})
            ch = (d.get("choices") or [{}])[0]
            text = (ch.get("message", {}) or {}).get("content") or ""
            row.update(ok=True, secs=round(secs, 3),
                       parsed=parse_reply(text) is not None,
                       finish=ch.get("finish_reason"),
                       tokens=(d.get("usage") or {}).get("completion_tokens"))
            stats["chat_ok"] += 1
        except Exception as e:
            row.update(ok=False, error=f"{type(e).__name__}: {e}"[:200])
            stats["chat_err"] += 1
            time.sleep(2)
        with lock:
            out.write(json.dumps(row) + "\n")
            out.flush()


EMBED_BATCH = 32          # real work per call, not a round-trip benchmark
EMBED_ROLLUP = 100        # emit one aggregated row per this many calls


def embed_worker(records, deadline, out, lock, stats):
    """Embeddings, flat out, but written as rollups.

    The first smoke run did 6,012 calls in two minutes at 20ms each, which over a
    full night is roughly 850,000 rows of almost entirely redundant record. The
    load is worth keeping and the per-call row is not: what has to survive is
    latency against time, so calls are batched into rollups of EMBED_ROLLUP and
    only the distribution is written. Same pressure on the card, one percent of
    the rows.
    """
    i = 0
    win_lat, win_err, win_start = [], 0, now()
    while now() < deadline:
        grp = [records[(i + k) % len(records)] for k in range(EMBED_BATCH)]
        i += EMBED_BATCH
        try:
            d, secs = post(f"{EMBED}/v1/embeddings", {
                "model": EMBED_MODEL, "input": [g["head"] for g in grp]},
                timeout=120)
            vecs = d.get("data") or []
            win_lat.append(secs)
            stats["embed_ok"] += 1
            stats["embed_vectors"] += len(vecs)
        except Exception as e:
            win_err += 1
            stats["embed_err"] += 1
            stats["embed_last_error"] = f"{type(e).__name__}: {e}"[:200]
            time.sleep(2)
        if len(win_lat) + win_err >= EMBED_ROLLUP:
            lat = sorted(win_lat)
            row = {"seat": "embed", "t": now().isoformat(timespec="seconds"),
                   "window_start": win_start.isoformat(timespec="seconds"),
                   "rollup": len(lat) + win_err, "batch": EMBED_BATCH,
                   "ok": len(lat) > 0, "errors": win_err,
                   "secs": round(statistics.median(lat), 4) if lat else None,
                   "p95": round(lat[min(len(lat) - 1, int(len(lat) * 0.95))], 4)
                          if lat else None,
                   "vectors": len(lat) * EMBED_BATCH}
            with lock:
                out.write(json.dumps(row) + "\n")
                out.flush()
            win_lat, win_err, win_start = [], 0, now()


def cmd_run(until, out_path):
    payload = json.loads(SAMPLE.read_text())
    records = payload["records"]
    hh, mm = (int(x) for x in until.split(":"))
    deadline = now().replace(hour=hh, minute=mm, second=0, microsecond=0)
    if deadline <= now():
        deadline += dt.timedelta(days=1)

    RUNS.mkdir(parents=True, exist_ok=True)
    out_path = Path(out_path) if out_path else (
        RUNS / f"sustained_{now():%Y%m%dT%H%M%S}.jsonl")
    stats = {"chat_ok": 0, "chat_err": 0, "embed_ok": 0, "embed_err": 0,
             "embed_vectors": 0, "embed_last_error": None}
    lock = threading.Lock()
    print(f"sustained: {len(records)} records looped on both seats")
    print(f"  until {deadline:%Y-%m-%d %H:%M}, writing {out_path}", flush=True)

    with out_path.open("a") as out:
        threads = [
            threading.Thread(target=chat_worker,
                             args=(records, deadline, out, lock, stats)),
            threading.Thread(target=embed_worker,
                             args=(records, deadline, out, lock, stats)),
        ]
        for t in threads:
            t.start()
        while any(t.is_alive() for t in threads):
            time.sleep(300)
            print(f"  [{now():%H:%M}] chat ok={stats['chat_ok']} "
                  f"err={stats['chat_err']} | embed ok={stats['embed_ok']} "
                  f"err={stats['embed_err']}", flush=True)
        for t in threads:
            t.join()
    print(f"done. {stats}", flush=True)
    return 0


def cmd_report(path):
    rows = []
    for line in Path(path).open():
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    if not rows:
        print("no rows")
        return 1
    out = ["# Sustained load: the chair's two seats", ""]
    t0 = min(dt.datetime.fromisoformat(r["t"]) for r in rows)
    t1 = max(dt.datetime.fromisoformat(r["t"]) for r in rows)
    out.append(f"**{t0:%Y-%m-%d %H:%M} to {t1:%H:%M}, "
               f"{(t1 - t0).total_seconds() / 3600:.1f} hours.** "
               f"{len(rows):,} calls. Both seats share the 4090.")
    out.append("")
    for seat in ("chat", "embed"):
        rs = [r for r in rows if r["seat"] == seat]
        if not rs:
            continue
        ok = [r for r in rs if r.get("ok")]
        out += [f"## {seat}", "",
                f"{len(rs):,} calls, {len(rs) - len(ok)} errors.", "",
                "| window | calls | err | median s | p95 s |"
                + (" parse |" if seat == "chat" else ""),
                "|---|---:|---:|---:|---:|" + ("---:|" if seat == "chat" else "")]
        for w in range(0, int((t1 - t0).total_seconds() // 1800) + 1):
            lo = t0 + dt.timedelta(seconds=w * 1800)
            hi = lo + dt.timedelta(seconds=1800)
            win = [r for r in rs
                   if lo <= dt.datetime.fromisoformat(r["t"]) < hi]
            if not win:
                continue
            wok = [r for r in win if r.get("ok")]
            lat = sorted(r["secs"] for r in wok if r.get("secs") is not None)
            if not lat:
                continue
            med = statistics.median(lat)
            p95 = lat[min(len(lat) - 1, int(len(lat) * 0.95))]
            cell = (f"| {w / 2:.1f}h | {len(win)} | {len(win) - len(wok)} "
                    f"| {med:.2f} | {p95:.2f} |")
            if seat == "chat":
                par = sum(1 for r in wok if r.get("parsed"))
                cell += f" {100 * par // max(len(wok), 1)}% |"
            out.append(cell)
        out.append("")
    print("\n".join(out))
    return 0


def main():
    ap = argparse.ArgumentParser(description="Sustained load on the bench seats")
    ap.add_argument("mode", choices=["run", "report"])
    ap.add_argument("path", nargs="?")
    ap.add_argument("--until", help="wall-clock deadline HH:MM")
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.mode == "run":
        if not a.until:
            ap.error("run needs --until HH:MM")
        return cmd_run(a.until, a.out)
    if not a.path:
        ap.error("report needs a jsonl path")
    return cmd_report(a.path)


if __name__ == "__main__":
    raise SystemExit(main())
