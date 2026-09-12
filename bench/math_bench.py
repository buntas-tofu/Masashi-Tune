#!/usr/bin/env python3
"""math_bench.py: the math instrument (commissioned 2026-08-11).

The comprehensive successor to the July 23 overnight's 8-item gauntlet, built
for the bench series between common models. Three auto-graded sections in
bench/math/items.jsonl, every answer independently re-derived by
verify_answers.py before any heat:

  A  standard-form core, public-style items across six domains at three
     difficulty tiers (the comparability section; training corpora contain
     these TYPES by construction)
  B  homegrown parallel-form items authored 2026-08-11 for this instrument,
     never published (the contamination control; the A-minus-B delta per seat
     reads memorization against skill)
  C  house-shaped applied items (rounding preimages, weighted medians,
     provisioning quantiles, reconciliation); ranks fit for OUR lanes

Law, per the routing law and the July grader lesson: one instrument one
reader (this runner IS the reader; grading is deterministic), temperature 0
on every scored read, two reads minimum, per-item agreement published beside
the ranking, dual-format extraction (ANSWER: line instructed; \\boxed{}
recovered and recorded, format adherence is its own routing finding), cost
reported beside quality and never blended in.

Envelope, per the corpus-bounds card: this ranks fit on THESE task families
at temperature 0 under a fixed token budget. It is not a general supremacy
claim, and proof-writing is out of scope here (the proof-writing harness
exam heats carry that lane separately).

Usage:
  math_bench.py run --endpoint http://HOST:PORT --candidate NAME \
      [--reads 2] [--max-tokens 16384] [--ids id1,id2] [--limit N] \
      [--sections A,B,C] [--timeout 900] [--sleep 0]
  math_bench.py report runs/math_bench_*.jsonl

Endpoints are the seats' own /v1/chat/completions, never the view (the view
clamps max_tokens; benches talk to the serving stack directly, the
face_bench precedent). llama.cpp seats run one slot: never run two
candidates on one node concurrently.

Floor: DMF. No em dashes, no ellipses.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
ITEMS_DEFAULT = HERE / "math" / "items.jsonl"
RUNS_DIR = HERE / "runs"

PROMPT_TEMPLATE = (
    "Solve the following problem. Reason as much as you need, then end your "
    "reply with the final answer on its own line in the exact form:\n"
    "ANSWER: <value>\n"
    "Use an integer, a fraction like 3/4, or a decimal. No units, no words on "
    "that line.\n\nPROBLEM:\n{problem}"
)


# ---------- transport ----------

def chat(endpoint: str, prompt: str, max_tokens: int, timeout: int) -> dict:
    """POST /v1/chat/completions at temperature 0. Returns
    {text, prompt_tokens, completion_tokens, finish_reason, wall}."""
    body = {
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False,
    }
    req = urllib.request.Request(
        endpoint.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    # llama.cpp answers 503 "Loading model" from bind until the weights land;
    # a run must never grade a loading server (the 08-12 race). Retry 503s for
    # up to ten minutes; wall on such a read includes the wait, honestly.
    for attempt in range(40):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
            break
        except urllib.error.HTTPError as e:
            if e.code == 503 and attempt < 39:
                time.sleep(15)
                continue
            raise
    wall = time.time() - t0
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    text = msg.get("content") or ""
    reasoning = msg.get("reasoning_content")
    if reasoning and not text.strip():
        # A reasoner that spent the whole budget thinking: the reasoning IS
        # the transcript. Graded as-is; the stop stats carry the story.
        text = reasoning
    usage = data.get("usage") or {}
    return {
        "text": text,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "finish_reason": choice.get("finish_reason"),
        "wall": round(wall, 3),
    }


# ---------- extraction and grading ----------

THINK_RE = re.compile(r"</think>", re.IGNORECASE)
ANSWER_LINE_RE = re.compile(r"(?im)^\s*\**\s*(?:final\s+)?answer\s*[:=]\s*(.+?)\s*\**\s*$")
BOXED_RE = re.compile(r"\\boxed\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}")
NUMBER_TOKEN_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?(?:\s*/\s*-?\d[\d,]*)?")
FRAC_TEX_RE = re.compile(r"\\d?frac\{(-?[\d,]+)\}\{(-?[\d,]+)\}")


def strip_think(text: str) -> str:
    parts = THINK_RE.split(text)
    return parts[-1] if len(parts) > 1 else text


def extract_answer(text: str) -> tuple[str | None, str]:
    """Returns (raw_answer, method). Methods: answer-line, boxed, fallback, none."""
    visible = strip_think(text)
    hits = ANSWER_LINE_RE.findall(visible)
    if hits:
        return hits[-1].strip(), "answer-line"
    hits = BOXED_RE.findall(visible)
    if hits:
        return hits[-1].strip(), "boxed"
    lines = [l.strip() for l in visible.splitlines() if l.strip()]
    if lines:
        tokens = NUMBER_TOKEN_RE.findall(lines[-1])
        if tokens:
            return tokens[-1].strip(), "fallback"
    return None, "none"


def parse_value(raw: str | None):
    """Parse an extracted answer to Fraction (exact) or float. None if hopeless."""
    if raw is None:
        return None
    s = raw.strip()
    m = FRAC_TEX_RE.search(s)
    if m:
        num = m.group(1).replace(",", "")
        den = m.group(2).replace(",", "")
        try:
            return Fraction(int(num), int(den))
        except (ValueError, ZeroDivisionError):
            return None
    for junk in ("$", "%", "\u2248", "`", "*"):
        s = s.replace(junk, "")
    s = s.strip().rstrip(".").strip()
    frac = re.fullmatch(r"(-?[\d,]+)\s*/\s*(-?[\d,]+)", s)
    if frac:
        try:
            return Fraction(int(frac.group(1).replace(",", "")),
                            int(frac.group(2).replace(",", "")))
        except (ValueError, ZeroDivisionError):
            return None
    plain = s.replace(",", "")
    try:
        return Fraction(plain)
    except ValueError:
        pass
    tokens = NUMBER_TOKEN_RE.findall(s)
    if tokens:
        return parse_value(tokens[-1])
    return None


def parse_key(answer: str):
    return Fraction(answer)


def grade(item: dict, text: str) -> dict:
    raw, method = extract_answer(text)
    value = parse_value(raw)
    key = parse_key(item["answer"])
    tol = item.get("tol")
    correct = False
    if value is not None:
        if value == key:
            correct = True
        elif tol is not None:
            try:
                correct = abs(float(value) - float(key)) <= tol
            except (OverflowError, ValueError):
                correct = False
    return {
        "correct": correct,
        "extracted": raw,
        "value": str(value) if value is not None else None,
        "method": method,
        "format_adherent": method == "answer-line",
    }


# ---------- run ----------

def load_items(path: Path, ids=None, limit=None, sections=None) -> list[dict]:
    items = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    if sections:
        items = [i for i in items if i["section"] in sections]
    if ids:
        wanted = set(ids)
        items = [i for i in items if i["id"] in wanted]
    if limit:
        items = items[:limit]
    return items


def cmd_run(args) -> int:
    items = load_items(Path(args.items), args.ids, args.limit,
                       args.sections.split(",") if args.sections else None)
    if not items:
        print("no items selected")
        return 1
    RUNS_DIR.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    out = RUNS_DIR / f"math_bench_{args.candidate}_{ts}.jsonl"
    print(f"{args.candidate}: {len(items)} items x {args.reads} reads "
          f"at temperature 0, max_tokens {args.max_tokens}")
    n_done = 0
    with out.open("w") as fh:
        header = {
            "kind": "manifest",
            "candidate": args.candidate,
            "endpoint": args.endpoint,
            "reads": args.reads,
            "max_tokens": args.max_tokens,
            "temperature": 0,
            "items": len(items),
            "started": ts,
        }
        fh.write(json.dumps(header) + "\n")
        for it in items:
            for read_idx in range(args.reads):
                prompt = PROMPT_TEMPLATE.format(problem=it["problem"])
                try:
                    r = chat(args.endpoint, prompt, args.max_tokens, args.timeout)
                except Exception as e:
                    rec = {"kind": "error", "item": it["id"], "read": read_idx,
                           "error": str(e)[:300]}
                    fh.write(json.dumps(rec) + "\n")
                    fh.flush()
                    print(f"  {it['id']} r{read_idx}: ERROR {str(e)[:80]}")
                    continue
                g = grade(it, r["text"])
                rec = {
                    "kind": "read",
                    "item": it["id"],
                    "section": it["section"],
                    "domain": it["domain"],
                    "difficulty": it["difficulty"],
                    "read": read_idx,
                    **g,
                    "finish_reason": r["finish_reason"],
                    "completion_tokens": r["completion_tokens"],
                    "wall": r["wall"],
                    "text_len": len(r["text"]),
                }
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
                mark = "+" if g["correct"] else "-"
                print(f"  {it['id']} r{read_idx}: {mark} "
                      f"[{g['method']}] {g['extracted']!r} "
                      f"({r['completion_tokens']} tok, {r['wall']}s, "
                      f"{r['finish_reason']})")
                n_done += 1
                if args.sleep:
                    time.sleep(args.sleep)
    print(f"wrote {out} ({n_done} reads)")
    return 0


# ---------- report ----------

def pct(n, d):
    return f"{100.0 * n / d:.1f}%" if d else "n/a"


def cmd_report(args) -> int:
    by_candidate: dict[str, list[dict]] = {}
    manifests: dict[str, dict] = {}
    for pattern in args.runs:
        for path in sorted(Path().glob(pattern)) or [Path(pattern)]:
            if not path.exists():
                continue
            cand = None
            for line in path.read_text().splitlines():
                rec = json.loads(line)
                if rec.get("kind") == "manifest":
                    cand = rec["candidate"]
                    manifests[cand] = rec
                    by_candidate.setdefault(cand, [])
                elif rec.get("kind") == "read" and cand:
                    by_candidate[cand].append(rec)
    if not by_candidate:
        print("no run records found")
        return 1
    print("# Math bench report\n")
    print("Envelope: fit on these task families at temperature 0 under a fixed")
    print("token budget; not a general supremacy claim. Scores by section, the")
    print("A-minus-B delta reads memorization against skill. Cost beside")
    print("quality, never blended.\n")
    for cand, reads in sorted(by_candidate.items()):
        man = manifests.get(cand, {})
        items: dict[str, list[dict]] = {}
        for r in reads:
            items.setdefault(r["item"], []).append(r)
        first_reads = [rs[0] for rs in items.values()]
        n_items = len(items)
        print(f"## {cand} (budget {man.get('max_tokens')}, "
              f"{man.get('reads')} reads, {n_items} items)\n")
        solved = sum(1 for rs in items.values() if all(x["correct"] for x in rs))
        any_solved = sum(1 for rs in items.values() if any(x["correct"] for x in rs))
        print(f"- solved (all reads correct): {solved}/{n_items} "
              f"({pct(solved, n_items)}); any-read: {any_solved}/{n_items}")
        for axis in ("section", "domain", "difficulty"):
            groups: dict = {}
            for iid, rs in items.items():
                key = rs[0][axis]
                g = groups.setdefault(key, [0, 0])
                g[1] += 1
                if all(x["correct"] for x in rs):
                    g[0] += 1
            parts = ", ".join(f"{k} {v[0]}/{v[1]}" for k, v in sorted(groups.items()))
            print(f"- by {axis}: {parts}")
        agree = sum(1 for rs in items.values()
                    if len(rs) > 1 and len({x["value"] for x in rs}) == 1)
        multi = sum(1 for rs in items.values() if len(rs) > 1)
        print(f"- read agreement (same parsed value across reads): "
              f"{agree}/{multi} ({pct(agree, multi)})")
        adherent = sum(1 for r in reads if r["format_adherent"])
        print(f"- format adherence (ANSWER: line as instructed): "
              f"{adherent}/{len(reads)} ({pct(adherent, len(reads))})")
        walls = [r["wall"] for r in reads if r.get("wall")]
        toks = [r["completion_tokens"] for r in reads if r.get("completion_tokens")]
        budget_walls = sum(1 for r in reads if r.get("finish_reason") == "length")
        if walls and toks:
            tps = sum(toks) / sum(walls)
            print(f"- cost: {sum(toks)} completion tokens over {sum(walls):.0f}s "
                  f"({tps:.1f} tok/s); budget-wall stops: {budget_walls}/{len(reads)}")
        methods: dict[str, int] = {}
        for r in reads:
            methods[r["method"]] = methods.get(r["method"], 0) + 1
        print(f"- extraction methods: "
              + ", ".join(f"{k} {v}" for k, v in sorted(methods.items())))
        print()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    runp = sub.add_parser("run")
    runp.add_argument("--endpoint", required=True)
    runp.add_argument("--candidate", required=True)
    runp.add_argument("--reads", type=int, default=2)
    runp.add_argument("--max-tokens", type=int, default=16384)
    runp.add_argument("--items", default=str(ITEMS_DEFAULT))
    runp.add_argument("--ids", type=lambda s: s.split(","), default=None)
    runp.add_argument("--limit", type=int, default=None)
    runp.add_argument("--sections", default=None)
    runp.add_argument("--timeout", type=int, default=900)
    runp.add_argument("--sleep", type=float, default=0)
    repp = sub.add_parser("report")
    repp.add_argument("runs", nargs="+")
    args = ap.parse_args()
    if args.cmd == "run":
        return cmd_run(args)
    return cmd_report(args)


if __name__ == "__main__":
    sys.exit(main())
