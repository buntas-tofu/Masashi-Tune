#!/usr/bin/env python3
"""Prefix-survival bench: does a byte-stable head let the serve prefix cache
survive a 20-turn room? (synaptic spine section 5, receipt 3 of 3.)

The spine's claim: the face's context was built from verbatim recency at every
layer, so its bytes churn at the head and every turn re-pays the whole history.
Phase 0 (frozen warmth epochs, byte-stable elision markers, projection head
reuse) and Phase 2 (two-shelf digests) make the head byte-stable so llama.cpp's
prompt cache can absorb it. This bench drives a room through the real view and
reads `llamacpp:prompt_tokens_total` from the face's /metrics after each turn.

The receipt is the MARGINAL prompt tokens per turn after warmup: if the head is
byte-stable and cached, later turns cost only the new turn's tokens (plus a
small growing tail), not a re-scan of the whole room. A flat-ish marginal curve
is the receipt; a linearly growing one means the head churns and the cache is
defeated.

Receipts land in bench/runs/. Run:
  python bench/spine_phase4_prefix_survival.py

Floor: DMF. No em dashes, no ellipses. This is an artifact; it carries the
floor in full.
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import bench_config as BC

HERE = Path(__file__).resolve().parent
RUNS = BC.runs_dir()
RUNS.mkdir(parents=True, exist_ok=True)

VIEW = BC.env("BENCH_VIEW", "http://127.0.0.1:8088")
FACE_METRICS = BC.env("BENCH_FACE_METRICS", "http://127.0.0.1:8080/metrics")
ROOM = f"bench-prefix-{int(time.time())}"
SEAT = BC.env("BENCH_SEAT", "bench-candidate")
N_TURNS = 20
COOLDOWN_S = 2.0  # between turns, so the metric flushes


def _prompt_tokens_total() -> int:
    with urllib.request.urlopen(FACE_METRICS, timeout=10) as r:
        text = r.read().decode("utf-8", "replace")
    for line in text.splitlines():
        if line.startswith("llamacpp:prompt_tokens_total"):
            return int(line.split()[-1])
    return 0


def _post_turn(prompt: str) -> str:
    body = json.dumps({"room": ROOM, "seat": SEAT, "prompt": prompt,
                       "max_tokens": 8, "temperature": 0}).encode()
    req = urllib.request.Request(f"{VIEW}/api/room/turn", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read().decode("utf-8", "replace")[:200]


def main() -> int:
    # Warmup: one turn so the model and cache are hot before we measure.
    _post_turn("warmup: just say warm.")
    time.sleep(COOLDOWN_S)
    baseline = _prompt_tokens_total()
    print(f"baseline prompt_tokens_total: {baseline}")

    marginal = []
    for i in range(1, N_TURNS + 1):
        _post_turn(f"turn {i}: continue the room briefly and stay under 8 tokens.")
        time.sleep(COOLDOWN_S)
        now = _prompt_tokens_total()
        delta = now - (marginal[-1]["cum"] if marginal else baseline)
        marginal.append({"turn": i, "cum": now, "marginal": delta})
        print(f"  turn {i:2}: marginal {delta:5} tokens (cum {now})")

    # The head of the curve (turn 1-3) includes the initial persona+warmth
    # build; the tail (last 8) is the steady-state cost per turn. If the head is
    # byte-stable and cached, the tail marginal should be small and flat.
    tail = marginal[-8:]
    avg_marginal = sum(m["marginal"] for m in tail) / len(tail)
    head = marginal[:3]
    avg_head = sum(m["marginal"] for m in head) / len(head) if head else 0

    receipt = {
        "bench": "spine_phase4_prefix_survival",
        "ts": time.time(),
        "room": ROOM,
        "n_turns": N_TURNS,
        "baseline_prompt_tokens": baseline,
        "marginal": marginal,
        "head_avg_marginal": round(avg_head, 1),
        "tail_avg_marginal": round(avg_marginal, 1),
        "tail_ratio_vs_head": round(avg_marginal / avg_head, 3) if avg_head else None,
        "note": "a low tail_avg_marginal (and ratio well under 1) means the "
                "byte-stable head is absorbed by the prompt cache; a ratio near "
                "1 or above means the head churns and the cache is defeated.",
    }
    stamp = time.strftime("%Y%m%dT%H%M%S")
    path = RUNS / f"spine_phase4_prefix_survival_{stamp}.json"
    path.write_text(json.dumps(receipt, indent=2))

    print(f"\nhead avg marginal: {avg_head:.1f} | tail avg marginal: "
          f"{avg_marginal:.1f} | ratio {receipt['tail_ratio_vs_head']}")
    print(f"receipt: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
