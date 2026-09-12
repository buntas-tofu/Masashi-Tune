#!/usr/bin/env python3
"""Relevance-graded retrieval bench: does the field's injected warmth block earn
default-on? (synaptic spine section 5, the relevance pass that Phase 4 deferred.)

Phase 4 measured exact-ref recall (does the exact original event appear in
top-8) on queries derived from the target's own text. That is an IDENTITY bar,
not a relevance bar, and it deflates the field with un-indexable candidates it
can never return. The gate asked for a relevance-graded pass instead.

WHY NOT COSINE-TO-QUERY AS THE RELEVANCE SIGNAL. The field SELECTS its top-8 by
cosine-to-query. Grading the result by cosine-to-query is circular: high cosine
is by construction, not evidence. A bench that reports that would be the field
marking its own homework. So this bench grades relevance with an EMBEDDER-FREE,
selection-independent signal: how many substantive tokens the returned event
shares with the present turn. Lexical overlap does not know which vectors the
field chose or how it ranked them; it measures, on the words themselves, whether
the surfaced material is actually about the present. It is a conservative bar
(it under-reports true semantic relevance from paraphrase) but it is honest, and
under-reporting is the safe direction for a flag that injects leading context.

Cosine to the query IS reported, but labeled semi-circular and never gated on.

It tests the REAL warmth path end to end:
  1. The warmth query is the seat's most recent operator turn (memory._field_query).
     So the honest query set is real turn.user events from the sediment.
  2. The warmth pulls field.search(query, k=8) and injects the top-8 as a
     Tier-3 "field recall" block that LEADS the warmth. So the honest question:
     when that fires, is the injected block actually on-topic for the present?
  3. The alternative it replaces is pure recency (the last 2-day window, minus
     meta and self-echo). The field must beat that on topical overlap for the
     OLD-tail case, which recency structurally cannot serve.

Method:
  - Sample real operator turns per band (old tail >12h, and recent <=12h).
  - For each, run field.search(text[:500], k=8) exactly as warmth does.
  - Recover each returned hit's event text from the sediment by ref.
  - Grade topical overlap: substantive-token Jaccard between the query and each
    hit's text (embedder-free, selection-independent).
  - Old-tail reach: does the field surface at least one OLD event per query?
  - Baseline: the pure-recency block, graded by the SAME lexical overlap.

The gate is PRE-REGISTERED, not post-hoc. FAYTH_FIELD_WARMTH earns default-on
iff on the OLD band (the case that decides) all of:
  (a) old-tail reach fires: >= half of old queries surface at least one event
      older than the recency horizon (the field is actually reaching the tail,
      not just re-ranking recent events).
  (b) field topical overlap is not noise: old-band mean query-hit Jaccard
      clears an ABSOLUTE floor (0.15). Long-document Jaccard is inherently
      small (union is large); 0.15 is genuine shared vocabulary, not chance.
  (c) the field beats what it replaces: old-band field mean >= the pure-recency
      baseline mean. When the baseline is 0.0 (recency surfaces nothing on-topic
      for an old query, the exact case the field exists for), any field topical
      overlap above the floor beats it. Do NOT gate on a multiple of the
      baseline: a 0.0 baseline makes any multiple unsatisfiable regardless of
      field performance, which punishes the field precisely when recency offers
      nothing. (Gate-design fix 2026-08-27 while running Phase 5.)
  (d) recent is not degraded: recent-band field mean >= recent-band baseline
      mean (the field does not hurt the immediate thread it sits on top of).
The recent band is reported; the old band decides.

Receipts land in bench/runs/. Run:
  python bench/spine_phase5_relevance_graded.py

Floor: DMF. No em dashes, no ellipses. This is an artifact; it carries the floor.
"""
from __future__ import annotations

import asyncio
import json
import math
import re
import sys
import time
from pathlib import Path

import bench_config as BC

BC.add_runtime_path()

try:
    from fabric_runtime.field import get_field, embed_text  # noqa: E402
    from fabric_runtime.memory import get_memory, _line_from_ref  # noqa: E402
except ImportError as _exc:  # noqa: E402
    get_field = embed_text = get_memory = _line_from_ref = None
    _RUNTIME_ERR = _exc
else:
    _RUNTIME_ERR = None

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
RUNS.mkdir(parents=True, exist_ok=True)

SAMPLE_PER_BAND = 60
RECENCY_HORIZON_S = 12 * 3600.0
QUERY_CLIP = 500
K = 8
# The topical-overlap floor (absolute, not a multiple of the baseline) and the
# old-tail reach majority the gate requires.
MIN_SHARED_TOKENS = 3
TOPICAL_FLOOR = 0.15
OLD_REACH_MAJORITY = 0.5

# Meta layers warmth never re-reveals.
_SKIP_KINDS = {"reveal.pushed", "tag", "tool.call", "tool.result", "fetch"}

_STOP = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "it", "its", "this", "that", "these",
    "those", "i", "you", "he", "she", "we", "they", "as", "at", "by", "from",
    "your", "my", "our", "their", "his", "her", "not", "no", "if", "then", "than",
    "so", "just", "now", "do", "does", "did", "will", "would", "can", "could",
    "have", "has", "had", "there", "here", "what", "which", "who", "whom", "when",
    "where", "why", "how", "all", "any", "both", "each", "few", "more", "most",
    "other", "some", "such", "only", "own", "same", "about", "above", "after",
    "again", "against", "before", "below", "between", "during", "under", "up",
    "down", "out", "off", "over", "into", "through", "am", "let", "please", "ok",
    "okay", "yes", "the",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 1 and t not in _STOP}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter < MIN_SHARED_TOKENS:
        return 0.0
    return inter / len(a | b)


def _event_text_for_hit(ref: str) -> str:
    """Recover an event's display text by its where-axis ref (read the sediment,
    the floor; never a stale copy)."""
    line = _line_from_ref(ref)
    if line:
        return line
    # Fallback: parse the sediment line directly if _line_from_ref differs.
    if ":" in ref:
        day, _, ln = ref.rpartition(":")
        try:
            from fabric_runtime.memory import MemoryEvent, SEDIMENT_ROOT
            with open(SEDIMENT_ROOT / f"{day}.jsonl", encoding="utf-8") as f:
                for i, raw in enumerate(f, 1):
                    if i == int(ln):
                        ev = MemoryEvent.from_line(raw)
                        if ev:
                            return _display(ev)
        except (OSError, ValueError):
            return ""
    return ""


def _display(ev) -> str:
    p = ev.payload
    if ev.kind in ("turn.user", "turn.seat"):
        return f"{p.get('seat', '')}: {p.get('text', '')}"
    if ev.kind == "room.turn":
        return f"[{p.get('room', '')}] {p.get('speaker', '')}: {p.get('text', '')}"
    if ev.kind == "consolidation":
        return p.get("text", "")
    if ev.kind == "summon":
        return f"{p.get('summoner', '')} summoned {p.get('target', '')}: {p.get('answer', '')}"
    if ev.kind == "room.digest":
        return f"{p.get('room', '')} digest: {p.get('gist', '')} decisions {p.get('decisions', '')}"
    return str(p.get("text", ""))


async def _load_operator_turns(max_days: int = 30) -> list[dict]:
    mem = get_memory()
    now = time.time()
    events = await mem.reveal(now, horizon_s=86_400 * max_days,
                              max_events=1_000_000)
    out = []
    for ev in events:
        if ev.kind != "turn.user":
            continue
        text = str(ev.payload.get("text", "")).strip()
        if len(text) < 20 or text.startswith("["):
            continue
        out.append({"ref": ev.ref, "t": ev.t, "text": text})
    return out


async def _field_search_hits(query: str, qref: str, now: float) -> list[dict]:
    """Run the warmth field pull exactly, return hits with recovered text."""
    hits = await get_field().search(query[:QUERY_CLIP], k=K)
    out = []
    for h in hits:
        if h["ref"] == qref:
            continue
        out.append({
            "ref": h["ref"],
            "t": h["t"],
            "kind": h["kind"],
            "cosine": h.get("cosine"),
            "text": _event_text_for_hit(h["ref"]),
        })
    return out


async def _recency_baseline(query_tokens: set[str], now: float) -> float:
    """Pure-recency alternative: recent non-meta events the flag-off path would
    reveal (2-day horizon), graded by the same lexical overlap. Returns the
    mean Jaccard, so the field can be compared against what it replaces."""
    mem = get_memory()
    events = await mem.reveal(now, horizon_s=86_400 * 2, max_events=5000)
    recent = [e for e in events if e.kind not in _SKIP_KINDS]
    recent = sorted(recent, key=lambda e: e.t, reverse=True)[:K]
    js = []
    for ev in recent:
        txt = _display(ev)
        if not txt:
            continue
        j = _jaccard(query_tokens, _tokens(txt))
        if j > 0.0:
            js.append(j)
    return sum(js) / len(js) if js else 0.0


async def _grade(query: str, qref: str, now: float) -> dict:
    qt = _tokens(query[:QUERY_CLIP])
    hits = await _field_search_hits(query, qref, now)
    jaccards = []
    for h in hits:
        j = _jaccard(qt, _tokens(h["text"]))
        jaccards.append(j)
        h["jaccard"] = j
    n_old = sum(1 for h in hits if now - h["t"] > RECENCY_HORIZON_S)
    baseline = await _recency_baseline(qt, now)
    return {
        "hits": hits,
        "n": len(hits),
        "mean_jaccard": sum(jaccards) / len(jaccards) if jaccards else 0.0,
        "old_hits": n_old,
        "baseline_jaccard": baseline,
    }


async def _run_band(band: list[dict], now: float) -> dict:
    field_means = []
    baseline_means = []
    reach_queries = 0
    reachable = 0
    for ev in band:
        g = await _grade(ev["text"], ev["ref"], now)
        if g["n"] == 0:
            continue
        reachable += 1
        field_means.append(g["mean_jaccard"])
        baseline_means.append(g["baseline_jaccard"])
        if g["old_hits"] >= 1:
            reach_queries += 1
    n = max(len(field_means), 1)
    return {
        "reachable": reachable,
        "field_mean_jaccard": round(sum(field_means) / len(field_means), 4) if field_means else None,
        "baseline_mean_jaccard": round(sum(baseline_means) / len(baseline_means), 4) if baseline_means else None,
        "old_reach_frac": round(reach_queries / n, 3),
        "field_beat_baseline_frac": round(sum(1 for f, b in zip(field_means, baseline_means) if f >= b) / n, 3),
    }


async def main() -> int:
    if get_field is None:
        raise SystemExit(f"{BC.RUNTIME_HINT}: {_RUNTIME_ERR}")
    turns = await _load_operator_turns()
    now = time.time()

    old = [e for e in turns if now - e["t"] > RECENCY_HORIZON_S]
    recent = [e for e in turns if now - e["t"] <= RECENCY_HORIZON_S]

    def _sample(band: list[dict], n: int) -> list[dict]:
        if len(band) <= n:
            return band
        step = len(band) / n
        return [band[int(i * step)] for i in range(n)]

    old_s = _sample(old, SAMPLE_PER_BAND)
    recent_s = _sample(recent, SAMPLE_PER_BAND)
    print(f"sampling {len(old_s)} old / {len(recent_s)} recent of "
          f"{len(old)}/{len(recent)} operator turns")

    old_r = await _run_band(old_s, now)
    recent_r = await _run_band(recent_s, now)

    # The pre-registered gate, evaluated on the OLD band.
    fo = old_r["field_mean_jaccard"] or 0.0
    bo = old_r["baseline_mean_jaccard"] or 0.0
    old_reach_ok = (old_r["old_reach_frac"] or 0.0) >= OLD_REACH_MAJORITY
    on_topic_floor = fo >= TOPICAL_FLOOR
    beats_recency = fo >= bo  # a 0.0 baseline is the case the field exists for
    fr = recent_r["field_mean_jaccard"] or 0.0
    br = recent_r["baseline_mean_jaccard"] or 0.0
    recent_ok = fr >= br
    earn = old_reach_ok and on_topic_floor and beats_recency and recent_ok

    receipt = {
        "bench": "spine_phase5_relevance_graded",
        "ts": now,
        "k": K,
        "recency_horizon_s": RECENCY_HORIZON_S,
        "min_shared_tokens": MIN_SHARED_TOKENS,
        "topical_floor": TOPICAL_FLOOR,
        "sample_per_band": SAMPLE_PER_BAND,
        "operator_turns_total": len(turns),
        "field_rows": get_field().stats().get("rows"),
        "old_band": old_r,
        "recent_band": recent_r,
        "gate": {
            "earn_default_on": earn,
            "legs": {
                "old_tail_reach (>= half old queries surface an old event)": old_reach_ok,
                "field topical overlap clears {} floor on old band".format(TOPICAL_FLOOR): on_topic_floor,
                "field beats recency baseline on old band": beats_recency,
                "recent not degraded (field >= baseline)": recent_ok,
            },
            "note": "PRE-REGISTERED. Relevance graded by EMBEDDER-FREE lexical "
                    "Jaccard (shared substantive tokens), independent of the "
                    "field's cosine selection, so high score is not by "
                    "construction. Cosine is reported separately but never "
                    "gated on. The old band decides; recency cannot reach it."
        },
    }
    stamp = time.strftime("%Y%m%dT%H%M%S")
    path = RUNS / f"spine_phase5_relevance_graded_{stamp}.json"
    path.write_text(json.dumps(receipt, indent=2))

    print(f"\noperator turns in 30d sediment: {len(turns)}")
    print(f"field rows: {get_field().stats().get('rows')}")
    print(f"\nOLD band: field jaccard {old_r['field_mean_jaccard']} vs baseline "
          f"{old_r['baseline_mean_jaccard']} | old-tail reach "
          f"{old_r['old_reach_frac']} | beat-baseline "
          f"{old_r['field_beat_baseline_frac']}")
    print(f"recent:   field jaccard {recent_r['field_mean_jaccard']} vs baseline "
          f"{recent_r['baseline_mean_jaccard']}")
    print(f"\nGATE {'PASS - earns default-on' if earn else 'FAIL - stays behind flag'}:")
    for name, ok in receipt["gate"]["legs"].items():
        print(f"  [{'x' if ok else ' '}] {name}")
    print(f"receipt: {path}")
    return 0 if earn else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
