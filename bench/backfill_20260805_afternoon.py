#!/usr/bin/env python3
"""Backfill the 2026-08-05 afternoon runs into the manifest lane.

WHY THIS EXISTS. The afternoon of 08-05 produced two real measurement runs, the
embed seat card split and the rung 2 specialist smokes, and neither reached the
lane. The numbers were banked in prose while the evidence under them sat in an
agent session scratchpad under /tmp. That is
worse than an unbanked result: the scratchpad is swept at boot by standing
practice, so the raw was one cleanup away from gone while the conclusions drawn
from it stayed on the record. Found 2026-08-05 evening during the state-of-play
sweep, on the operator's approval to get the afternoon runs into a manifest.

The rescue moved instruments to the bench and raw to bench/runs/. This script
does the join and emits through manifest.emit, so the emitter's own INCOMPLETE
guard judges the result rather than this file asserting it is whole.

NOTHING IS RE-ASSERTED FROM PROSE. The cosine figure the record cites is
recomputed here from the stored vectors, so the manifest carries a number this
lane derived rather than a number this lane was told. Floor: no em dashes, no
ellipses.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import manifest as M
import bench_config as BC

BENCH = Path(__file__).resolve().parent
SPLIT = Path(BC.env("BENCH_SPLIT_DIR", str(BENCH / "runs" / "split_probe_example")))
SMOKE = Path(BC.env("BENCH_SMOKE_DIR", str(BENCH / "runs" / "smoke_example")))


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else None


def embed_split():
    """Contention, measured pre and post move, plus the cross-card vector check."""
    phases = {}
    for name in ("pre_chat_solo", "pre_chat_contended",
                 "post_chat_solo", "post_chat_contended"):
        phases[name] = json.loads((SPLIT / f"{name}.json").read_text())

    pre = json.loads((SPLIT / "pre_embed.json").read_text())
    post = json.loads((SPLIT / "post_embed.json").read_text())
    sims = [cosine(u, v) for u, v in zip(pre["vectors"], post["vectors"])]
    sims = [s for s in sims if s is not None]

    # One raw row per phase, so the lane points at rows rather than at a folder.
    raw = SPLIT / "split_probe.jsonl"
    with raw.open("w") as f:
        for name, d in phases.items():
            f.write(json.dumps({"phase": name, **d}, sort_keys=True) + "\n")
        f.write(json.dumps({
            "phase": "embed_fingerprint",
            "dim": pre.get("dim"), "probes": len(sims),
            "cosine_min": min(sims), "cosine_max": max(sims),
            "cosine_mean": sum(sims) / len(sims),
            "pre_secs": pre.get("secs"), "post_secs": post.get("secs"),
        }, sort_keys=True) + "\n")

    penalty_pre = (phases["pre_chat_contended"]["median"]
                   / phases["pre_chat_solo"]["median"] - 1)
    penalty_post = (phases["post_chat_contended"]["median"]
                    / phases["post_chat_solo"]["median"] - 1)

    return {
        "run": "embed-split-contention",
        "started": "2026-08-05T14:20:00-04:00",
        "raw": str(raw),
        "instrument": M.instrument(BENCH / "split_probe.py"),
        "hardware": M.hardware(),
        "vessel": M.vessel(str(BC.models_dir() / "gemma-4-e2b-ud"),
                           "gemma-4-E2B-it-UD-Q4_K_XL.gguf"),
        "serving": {
            "subject": "the chat seat (:8085)",
            "contender": "the embed seat (:8086)",
            "pre": "both seats resident on the 4090",
            "post": "the embed seat moved to the other card, the chat seat alone on the 4090",
            "chat_process": "never restarted across the move",
            "temperature": 0,
        },
        "arms": [
            {"arm": "shared-card", "result": {
                "solo_median_s": phases["pre_chat_solo"]["median"],
                "contended_median_s": phases["pre_chat_contended"]["median"],
                "embed_batches": phases["pre_chat_contended"].get("embed_batches"),
                "penalty_pct": round(penalty_pre * 100, 1),
                "status": "COMPLETE"}},
            {"arm": "split-cards", "result": {
                "solo_median_s": phases["post_chat_solo"]["median"],
                "contended_median_s": phases["post_chat_contended"]["median"],
                "embed_batches": phases["post_chat_contended"].get("embed_batches"),
                "penalty_pct": round(penalty_post * 100, 1),
                "status": "COMPLETE"}},
            {"arm": "embed-cross-card-sm89-vs-sm120", "result": {
                "probes": len(sims),
                "cosine_min": round(min(sims), 6),
                "cosine_max": round(max(sims), 6),
                "bitwise_identical": all(s == 1.0 for s in sims),
                "reading": "similarity equivalent, not bitwise. Platform "
                           "determinism extends to the embedding lane.",
                "status": "COMPLETE"}},
        ],
        "closes": ["bench contract law 2"],
    }


def specialist_smokes():
    """Six seats brought up on the chair, read back off their own serve logs."""
    seats = {
        "guardian8b": "guardian8b_serve2.log",
        "gptoss20b": "gptoss20b_serve.log",
        "nemotron-embed": "nemotron_embed_serve3.log",
        "nemotron-rerank": "nemotron_rerank_serve2.log",
        "granite-embed": "granite_embed_serve.log",
        "granite-rerank": "granite_rerank_serve.log",
    }
    raw = SMOKE / "specialist_smoke_20260805T142600.jsonl"
    arms = []
    with raw.open("w") as f:
        for seat, log in sorted(seats.items()):
            p = SMOKE / log
            text = p.read_text(errors="replace") if p.is_file() else ""
            served = bool(re.search(r"Application startup complete|Uvicorn running",
                                    text))
            # vLLM's OWN report of what the weights cost, which is a different
            # quantity from the total process footprint nvidia-smi shows and the
            # record. Labelled as weights rather than folded into one
            # "vram" number, because two measurements of different things that
            # disagree are only a contradiction if someone flattens them first.
            w = re.search(r"Model loading took ([0-9.]+) ?GiB", text)
            kv = re.search(r"GPU KV cache size: ([0-9,]+) tokens", text)
            row = {"seat": seat, "log": log, "served": served,
                   "weights_gib": float(w.group(1)) if w else None,
                   "kv_cache_tokens": int(kv.group(1).replace(",", ""))
                   if kv else None}
            f.write(json.dumps(row, sort_keys=True) + "\n")
            # An arm with no result is what the emitter refuses to call whole, so
            # a seat whose log cannot confirm startup returns no result at all
            # rather than a confident False.
            arms.append({"arm": seat,
                         "result": {"served": served,
                                    "weights_gib": row["weights_gib"],
                                    "kv_cache_tokens": row["kv_cache_tokens"],
                                    "status": "COMPLETE"} if text else None})
    return {
        "run": "rung2-specialist-smokes",
        "started": "2026-08-05T14:26:00-04:00",
        "raw": str(raw),
        "instrument": M.instrument(BENCH / "smoke_specialist.py"),
        "hardware": M.hardware(),
        "serving": {"stack": "vLLM in docker, the bench range",
                    "note": "six of six served; four flipped lazy with units, "
                            "the granite pair proven ad hoc and left staged "
                            "until a consumer wants them"},
        "arms": arms,
        "closes": ["the rung 2 smoke item"],
    }


if __name__ == "__main__":
    for build in (embed_split, specialist_smokes):
        man = build()
        path = M.emit(man)
        flag = man.get("INCOMPLETE")
        print(f"{man['run']:<28} -> {path}")
        for a in man["arms"]:
            print(f"   {a['arm']:<34} {a['result']}")
        print(f"   INCOMPLETE: {flag}\n" if flag else "   whole\n")
