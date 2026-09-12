#!/usr/bin/env python3
"""Fidelity bench: does the two-shelf projection lose decisions? (spine section 5).

Builds a synthetic decision-rich room (a "flood-test room": many turns carrying
real decisions, open items, and numbers), projects it two ways -- verbatim
(the floor) and two-shelf (epoch+turn digests for the deep past, verbatim for
the tail) -- and asks the face's instruction set / a judgment read whether the
decisions survive. The receipt is what decides whether FAYTH_TWO_SHELF and
FAYTH_DIGEST_TURNS go default-on.

Receipts land in bench/runs/. Run:
  python bench/spine_phase2_fidelity_bench.py

Floor: DMF. No em dashes, no ellipses. This is an artifact; it carries the
floor in full.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import bench_config as BC

BC.add_runtime_path()

try:
    from fabric_runtime.digest import _format_digest  # noqa: E402
    from fabric_runtime.room import _project_two_shelf, room_as_conversation  # noqa: E402
except ImportError as _exc:  # noqa: E402
    _format_digest = _project_two_shelf = room_as_conversation = None
    _RUNTIME_ERR = _exc
else:
    _RUNTIME_ERR = None

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
RUNS.mkdir(parents=True, exist_ok=True)


def build_room(n_turns: int = 30) -> list[dict]:
    """A synthetic decision-rich room: 30 turns alternating operator and assistant,
    with real decisions, open items, and a couple of numbers to preserve."""
    decisions = [
        ("we switch the face to qwen3.8", "open: bench the mmproj"),
        ("phase 1 ships today", "open: nothing"),
        ("the field index targets 768 dims", "open: measure hit rate"),
        ("two-shelf stays behind a flag", "open: the fidelity bench"),
        ("the keeper binds the configured host", "open: nothing"),
    ]
    turns = []
    for i in range(n_turns):
        speaker = "you" if i % 2 == 0 else "assistant"
        if i % 6 == 0:
            dec, opn = decisions[(i // 6) % len(decisions)]
            text = f"decision {i // 6}: {dec}. {opn}."
        else:
            text = f"turn {i}: the room works on the spine, no decision."
        turns.append({"speaker": speaker, "text": text})
    return turns


def known_decisions(turns: list[dict]) -> list[str]:
    """The decisions embedded in the synthetic room (the ground truth)."""
    out = []
    for t in turns:
        if t["text"].startswith("decision "):
            out.append(t["text"])
    return out


def digest_truth(turns: list[dict]) -> list[dict]:
    """The perfect digest shelf: one epoch digest that carries every decision
    verbatim (what the familiar SHOULD produce; this is the ceiling, not a
    measured familiar)."""
    gist = " | ".join(known_decisions(turns))
    return [{
        "type": "epoch",
        "_fmt": _format_digest({
            "who": "you, assistant", "decisions": gist,
            "open": "bench", "gist": "the flood-test room, decisions preserved",
        }),
        "gist": "the flood-test room, decisions preserved",
        "room": "flood",
    }]


def project_both(turns: list[dict], self_name: str, tail: int = 12,
                 cap: int | None = 48_000):
    verbatim = room_as_conversation(turns, self_name, cap_chars=cap)
    digests = digest_truth(turns)
    two_shelf, _ = _project_two_shelf(turns, digests, self_name,
                                      cap_chars=cap, verbatim_tail=tail)
    return verbatim, two_shelf


def decision_survival(projected: list[dict], known: list[str]) -> dict:
    """What fraction of known decisions survive into the projection text."""
    text = " ".join(m["content"] for m in projected)
    found = [d for d in known if d in text]
    return {"found": len(found), "total": len(known),
            "fraction": len(found) / len(known) if known else 1.0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=30)
    ap.add_argument("--tail", type=int, default=12)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if room_as_conversation is None:
        raise SystemExit(f"{BC.RUNTIME_HINT}: {_RUNTIME_ERR}")

    turns = build_room(args.turns)
    known = known_decisions(turns)
    verbatim, two_shelf = project_both(turns, "assistant", tail=args.tail)

    v_survival = decision_survival(verbatim, known)
    t_survival = decision_survival(two_shelf, known)

    v_chars = sum(len(m["content"]) for m in verbatim)
    t_chars = sum(len(m["content"]) for m in two_shelf)

    receipt = {
        "bench": "spine_phase2_fidelity",
        "ts": time.time(),
        "n_turns": len(turns),
        "n_decisions": len(known),
        "verbatim": {"chars": v_chars, **v_survival},
        "two_shelf": {"chars": t_chars, **t_survival},
        "digest_shelf": "perfect (ceiling, not measured familiar)",
        "note": "two-shelf preserves decisions iff fraction == 1.0 with "
                "materially fewer chars; the familiar fidelity is benched "
                "separately against the live seat.",
    }

    stamp = time.strftime("%Y%m%dT%H%M%S")
    path = RUNS / f"spine_phase2_fidelity_{stamp}.json"
    path.write_text(json.dumps(receipt, indent=2))

    if args.json:
        print(json.dumps(receipt, indent=2))
    else:
        print(f"flood-test room: {len(turns)} turns, {len(known)} decisions")
        print(f"verbatim:  {v_chars:6} chars  decision survival {v_survival['fraction']:.2%}")
        print(f"two-shelf: {t_chars:6} chars  decision survival {t_survival['fraction']:.2%}")
        print(f"char saving: {100 * (1 - t_chars / max(v_chars, 1)):.1f}%")
        print(f"receipt: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
