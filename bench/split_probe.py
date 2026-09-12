#!/usr/bin/env python3
"""Embed split instrument, 2026-08-05: fingerprint and contention, pre and post.

Three modes, one file, so pre-move and post-move runs are the same code:
  embed <out.json>    embed the fixed probe strings via the embed seat, save vectors
  chat <out.json>     N bounded Red XIII calls at temperature 0, latencies
  contend <out.json>  same chat probe while an embed loop hammers in a
                      background thread, so contention is measured not argued
  compare <a> <b>     cosine similarity per probe string between two embed runs

The embed fingerprint exists because a card swap changes the embed seat's silicon and the
platform-determinism finding says platform is instrument identity. Embeddings
are float reductions; sm_89 and sm_120 need not agree bitwise, so the question
is how far apart they land, measured, not assumed.
Floor: no em dashes, no ellipses.
"""
import json
import statistics
import sys

import bench_config as BC
import threading
import time
import urllib.request

HOST = BC.env("BENCH_HOST", "127.0.0.1")
EMBED = f"http://{HOST}:8086"
CHAT = f"http://{HOST}:8085"

PROBES = [
    "carrier online.",
    "The ranking pipeline feeds the true reference to the scorer to isolate post-processing.",
    "unsloth UD-Q4_K_XL quantization of the E2B, pinned at revision 0314792d.",
    "A carrier parses, hands off, sheds, and wipes; eyes belong to the face.",
    "Route by fit across the whole roster. One instrument, one reader.",
]

CHAT_N = 8


def post(url, payload, timeout=120):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode(errors="replace")), time.time() - t0


def embed_once(texts):
    d, secs = post(f"{EMBED}/v1/embeddings", {"input": texts, "model": "bench-embed"})
    return [row["embedding"] for row in d["data"]], secs


def mode_embed(out):
    vecs, secs = embed_once(PROBES)
    json.dump({"probes": PROBES, "vectors": vecs, "secs": round(secs, 3),
               "dim": len(vecs[0])}, open(out, "w"))
    print(f"embedded {len(vecs)} probes, dim {len(vecs[0])}, {secs:.3f}s -> {out}")


def chat_batch():
    lats = []
    for _ in range(CHAT_N):
        _, secs = post(f"{CHAT}/v1/chat/completions", {
            "model": "bench-chat", "temperature": 0, "max_tokens": 40,
            "messages": [{"role": "user", "content":
                          "Reply with exactly: carrier online."}]})
        lats.append(secs)
    return lats


def mode_chat(out):
    lats = chat_batch()
    med = statistics.median(lats)
    json.dump({"lats": [round(x, 3) for x in lats],
               "median": round(med, 3)}, open(out, "w"))
    print(f"chat seat solo: median {med:.3f}s over {CHAT_N} -> {out}")


def mode_contend(out):
    stop = threading.Event()
    count = {"n": 0}

    def hammer():
        big = [p * 8 for p in PROBES] * 4
        while not stop.is_set():
            try:
                embed_once(big)
                count["n"] += 1
            except Exception:
                time.sleep(0.5)

    t = threading.Thread(target=hammer, daemon=True)
    t.start()
    time.sleep(2)
    lats = chat_batch()
    stop.set()
    t.join(timeout=10)
    med = statistics.median(lats)
    json.dump({"lats": [round(x, 3) for x in lats],
               "median": round(med, 3), "embed_batches": count["n"]},
              open(out, "w"))
    print(f"chat seat under embed load: median {med:.3f}s over {CHAT_N}, "
          f"{count['n']} embed batches -> {out}")


def mode_compare(a, b):
    A = json.load(open(a))
    B = json.load(open(b))
    for i, probe in enumerate(A["probes"]):
        va, vb = A["vectors"][i], B["vectors"][i]
        dot = sum(x * y for x, y in zip(va, vb))
        na = sum(x * x for x in va) ** 0.5
        nb = sum(x * x for x in vb) ** 0.5
        print(f"cosine {dot / (na * nb):.8f}  {probe[:50]}")


if __name__ == "__main__":
    m = sys.argv[1]
    if m == "embed":
        mode_embed(sys.argv[2])
    elif m == "chat":
        mode_chat(sys.argv[2])
    elif m == "contend":
        mode_contend(sys.argv[2])
    elif m == "compare":
        mode_compare(sys.argv[2], sys.argv[3])
