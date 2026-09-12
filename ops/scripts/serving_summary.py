#!/usr/bin/env python3
"""serving_summary: a compact serving telemetry summary: per-seat model,
container/image digest, GPU assignment, context window, queue, prefill/decode,
throughput, cache, OOM/retry counts, per-request ids.

Input:  {node?, since?, until?, data?}  -- data is a pre-fetched snapshot:
        {seats: [{key, model, stack, gpu, ctx, ...}], metrics: [...]}
Output: {seats: [{key, model, stack, gpu, ctx, p50_latency_ms, tps, cache_hits,
         oom, retries}], aggregate}
Read-only: never touches GPU state; it is pure over the supplied snapshot.
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
    seats_in = data.get("seats", [])
    metrics = data.get("metrics", [])
    seats = []
    for s in seats_in:
        key = s.get("key", "")
        lat = [m.get("latency_ms") for m in metrics
               if m.get("seat") == key and m.get("latency_ms") is not None]
        latency = sorted(lat)[len(lat) // 2] if lat else None  # p50
        oom = sum(1 for m in metrics if m.get("seat") == key and m.get("oom"))
        retries = sum(m.get("retries", 0) for m in metrics if m.get("seat") == key)
        seats.append({
            "key": key,
            "model": s.get("model"),
            "stack": s.get("stack"),
            "gpu": s.get("gpu"),
            "ctx": s.get("ctx"),
            "p50_latency_ms": latency,
            "tps": s.get("tps"),
            "cache_hits": s.get("cache_hits", 0),
            "oom": oom,
            "retries": retries,
        })
    total_requests = len(metrics)
    healthy = all(s.get("alive", True) for s in seats_in)
    return {
        "seats": seats,
        "aggregate": {"seats": len(seats), "requests": total_requests,
                      "healthy": healthy, "util": data.get("util")},
        "read_only": True,
    }


def main():
    print(json.dumps(run(_parse_args(sys.argv[1:])), ensure_ascii=False))


if __name__ == "__main__":
    main()
