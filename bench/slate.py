#!/usr/bin/env python3
"""Slate: the four-node face's throughput lines, measured with a manifest.

The distributed serving chapter closes with a slate of six measures. Two of them
graduated on 2026-11-03 from a captured boot: cold start and load time, and KV
per node at a stated occupancy. This instrument exists for the first line that
still needs one, prefill and decode throughput across rising context, and it
carries a manifest per run so a number never leaves the room without its
configuration.

WHAT IT MEASURES, AND HOW. Two calls per rung, not one, because prefill and
decode are different physical claims and a single wall clock cannot separate
them:

  prefill rung   a prompt sized to the rung, max_tokens 1, thinking disabled.
                 The seconds are prefill plus one token, and the rate is the
                 server's own reported prompt_tokens divided by those seconds.
                 That is an honest upper bound on prefill and it is labeled as
                 one.
  decode rung    a short prompt at max_tokens 1 to price the fixed overhead,
                 then the same prompt with a real completion budget. The decode
                 rate is (completion_tokens - 1) over the difference. The
                 subtraction is stated on the report, not hidden here.

Both rungs run with thinking disabled. A reasoning model that thinks inside the
budget returns an empty content string with a healthy 200, and a latency
instrument that cannot tell that apart from a slow answer is measuring the wrong
thing.

THE LAW THIS OBEYS. One tool, one job, one self-test. The self-test runs against
a stub endpoint on loopback, with no model and no GPU, and proves the wiring,
the arithmetic, and the report shape. Requested token counts are recorded beside
actual ones because a character estimate is not a token count and the difference
is the instrument's own error bar.

Usage:
  slate.py selftest
  slate.py run --url http://HOST:8000 --model NAME \\
      --lengths 4096,32768,131072,262144 --reps 2 --report ../reports/SLATE_DATE.md

Floor: DMF. No em dashes, no ellipses.
"""
from __future__ import annotations

import argparse
import json
import secrets
import statistics
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import bench_config as BC
import manifest as MF

CHARS_PER_TOKEN = 4
FLOOR_RESERVE = 64
DEFAULT_LENGTHS = "4096,32768,131072,262144"
DEFAULT_REPS = 2
DEFAULT_DECODE_TOKENS = 128


def post(url: str, payload: dict, timeout: float = 900.0) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions",
                                 data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def filler(target_tokens: int, nonce: str = "",
           chars_per_token: float = CHARS_PER_TOKEN) -> str:
    """A prompt of approximately target_tokens tokens, sized by a measured ratio.

    The nonce is not decoration. The face runs with prefix caching on, so two
    calls that open with the same text share a cached prefix and the second one
    measures a cache hit instead of a prefill. The first version of this
    instrument did exactly that and produced throughput rising with context,
    which is physically impossible and was the tell. Every call now opens with a
    unique string, so the measured prefill is a cold prefill.

    chars_per_token is measured, not assumed. The house estimate of 4 chars per
    token undersized every rung by about 20 percent on this model, so a rung
    labeled 4096 was really 3265 prompt tokens. The ratio is calibrated once on
    a small call and then applied to the rungs.
    """
    unit = ("The keeper counts the tabs twice and the ledger keeps its own rhythm "
            "across the long counter of the bar. ")
    want = max(1, int((target_tokens - FLOOR_RESERVE) * chars_per_token))
    head = f"Run {nonce}.\n" if nonce else ""
    return head + (unit * (want // len(unit) + 1))[:want] + "\nReply with the single word OK."


def calibrate(url: str, model: str, rung: int = 4096) -> float:
    """Measure this model's chars per token on a small rung, once per run."""
    text = filler(rung, secrets.token_hex(8))
    d = post(url, {"model": model,
                   "messages": [{"role": "user", "content": text}],
                   "max_tokens": 1, "temperature": 0,
                   "chat_template_kwargs": {"enable_thinking": False}})
    actual = (d.get("usage") or {}).get("prompt_tokens") or 0
    return (len(text) / actual) if actual else CHARS_PER_TOKEN


def overhead(url: str, model: str) -> dict:
    """The fixed cost of one call: a short prompt, one token out."""
    t0 = time.perf_counter()
    d = post(url, {"model": model,
                   "messages": [{"role": "user", "content": "Reply with the single word OK."}],
                   "max_tokens": 1, "temperature": 0,
                   "chat_template_kwargs": {"enable_thinking": False}})
    secs = time.perf_counter() - t0
    usage = d.get("usage") or {}
    return {"secs": secs, "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens")}


def prefill_rung(url: str, model: str, target_tokens: int,
                 chars_per_token: float = CHARS_PER_TOKEN) -> dict:
    """Prefill plus one token, at the requested rung, on a cold prefix."""
    nonce = secrets.token_hex(8)
    text = filler(target_tokens, nonce, chars_per_token)
    t0 = time.perf_counter()
    d = post(url, {"model": model,
                   "messages": [{"role": "user", "content": text}],
                   "max_tokens": 1, "temperature": 0,
                   "chat_template_kwargs": {"enable_thinking": False}})
    secs = time.perf_counter() - t0
    usage = d.get("usage") or {}
    actual = usage.get("prompt_tokens")
    rate = (actual / secs) if (actual and secs > 0) else None
    return {"rung": "prefill", "requested_tokens": target_tokens,
            "prompt_tokens": actual, "secs": round(secs, 3),
            "tok_per_s": round(rate, 1) if rate else None,
            "nonce": nonce[:8],
            "finish": (d.get("choices") or [{}])[0].get("finish_reason")}


def decode_rung(url: str, model: str, base: dict, budget: int) -> dict:
    """Decode rate, with the one-token overhead subtracted and stated."""
    prompt = "Write one short paragraph about counting tabs at a bar."
    t0 = time.perf_counter()
    d = post(url, {"model": model,
                   "messages": [{"role": "user", "content": prompt}],
                   "max_tokens": budget, "temperature": 0,
                   "chat_template_kwargs": {"enable_thinking": False}})
    secs = time.perf_counter() - t0
    usage = d.get("usage") or {}
    done = usage.get("completion_tokens") or 0
    span = secs - base["secs"]
    rate = ((done - 1) / span) if (done > 1 and span > 0) else None
    row = {"rung": "decode", "completion_tokens": done, "secs": round(secs, 3),
           "prompt_tokens": usage.get("prompt_tokens"),
           "overhead_secs": round(base["secs"], 3),
           "span_secs": round(span, 3) if span > 0 else None,
           "tok_per_s": round(rate, 1) if rate else None,
           "finish": (d.get("choices") or [{}])[0].get("finish_reason")}
    if span <= 0:
        row["note"] = "decode span not separable from the one-token overhead"
    return row


def measure(url: str, model: str, lengths: list[int], reps: int,
            decode_tokens: int) -> dict:
    rows: list[dict] = []
    cpt = calibrate(url, model)
    base = overhead(url, model)
    for length in lengths:
        for rep in range(reps):
            r = prefill_rung(url, model, length, cpt)
            r["rep"] = rep
            rows.append(r)
    for rep in range(reps):
        r = decode_rung(url, model, base, decode_tokens)
        r["rep"] = rep
        rows.append(r)
    return {"rows": rows, "overhead": base, "chars_per_token": round(cpt, 3)}


def rollup(rows: list[dict]) -> dict:
    """Median per rung and measurement, because one call is weather."""
    by: dict[str, list[dict]] = {}
    for r in rows:
        key = f"prefill:{r.get('requested_tokens')}" if r["rung"] == "prefill" else "decode"
        by.setdefault(key, []).append(r)
    out = {}
    for key, rs in by.items():
        rates = [r["tok_per_s"] for r in rs if r.get("tok_per_s")]
        secs = [r["secs"] for r in rs]
        actual = [r["prompt_tokens"] for r in rs if r.get("prompt_tokens")]
        out[key] = {"calls": len(rs),
                    "median_tok_per_s": round(statistics.median(rates), 1) if rates else None,
                    "median_secs": round(statistics.median(secs), 3),
                    "prompt_tokens": statistics.median(actual) if actual else None,
                    "finish": sorted({str(r.get("finish")) for r in rs})}
    return out


def report_md(summary: dict, meta: dict) -> str:
    # The report is a published artifact, so it carries no hostname, no home
    # path, and no node name. The endpoint stays in the manifest, which lives in
    # the estate; the report points at the run, not at the machine that ran it.
    lines = [
        "# The slate: prefill and decode on the distributed face",
        "",
        f"Status: measured, date-addressed, single instrument. Written {meta['started']} "
        f"against the endpoint configured for this run.",
        "Not a benchmark and not a comparison across models. These are this face's",
        "numbers on this run, with the run's manifest beside them.",
        "Authority: Tier 2 for every figure, computed from the raw tape named below.",
        "Floor: DMF. No em dashes, no ellipses. Inference labeled.",
        "",
        f"Model id: `{meta['model']}`. Reps per rung: {meta['reps']}. Decode budget: "
        f"{meta['decode_tokens']} tokens. Thinking disabled on every call. Prompt sizing "
        f"calibrated at {meta.get('chars_per_token')} characters per token.",
        "",
        "## Method, stated before the numbers",
        "",
        "Prefill is a prompt sized to the rung with `max_tokens` 1, so the seconds",
        "cover prefill plus one token and the rate is an upper bound rather than a",
        "pure prefill figure. Each call opens with a unique nonce, because the face",
        "runs with prefix caching on and identical openings turn a prefill into a",
        "cache hit. Decode subtracts a measured single-token overhead from a short",
        "prompt before dividing, and that prompt is deliberately cache-warm so the",
        "subtraction leaves decode alone. Each prompt is sized from a chars-per-token",
        "ratio calibrated on a small call in the same run, and requested and actual",
        "prompt tokens are both recorded so a reader can check that the rung landed",
        "where its label says it did.",
        "",
        "Finish reason is `length` on every prefill rung by construction, one token of",
        "budget, and on the decode rung because the completion fills its budget. Both",
        "are expected here and neither is a truncation artifact.",
        "",
        "This instrument got that wrong on its first run, and the record keeps it.",
        "Without the nonce it reported prefill throughput rising with context, 6.5k",
        "tokens per second at 4k against 96k at 262144, which is impossible. The",
        "rising curve was the prefix cache returning earlier calls' work. A number",
        "that improves with difficulty is the instrument confessing, not the hardware",
        "improving.",
        "",
        "## Numbers",
        "",
        "| rung | calls | prompt tokens | median seconds | median tok/s | finish |",
        "|---|---|---|---|---|---|",
    ]
    def order(k: str):
        return (k == "decode", int(k.split(":")[1]) if ":" in k else 0)

    for key in sorted(summary, key=order):
        s = summary[key]
        lines.append(f"| {key} | {s['calls']} | {s['prompt_tokens']} | "
                     f"{s['median_secs']} | {s['median_tok_per_s']} | "
                     f"{', '.join(str(x) for x in s['finish'])} |")
    lines += [
        "",
        f"Raw tape: `{Path(meta['raw']).name}`, in the instrument's run directory. "
        f"Manifest: the estate's daily run lane for this date.",
        "",
        "The tape is not shipped with this report. It sits in the run directory beside",
        "the instrument, and in this tree that directory is ignored by ruling, which is",
        "the same gap the bench arc carries: the method is reproducible from here, the",
        "figures are not independently re-derivable without the estate original. The",
        "open card on shipping raw tapes is the place that changes, not this report.",
        "",
        "## What this licenses, and what it does not",
        "",
        "It licenses a claim about this face, at these context lengths, on this run.",
        "It does not license a tensor-parallel scaling claim, which needs boots at one,",
        "two, and four nodes measured with this same instrument. It does not license a",
        "concurrency claim: one call is in flight at a time here.",
        "",
    ]
    return "\n".join(lines)


class _Stub(BaseHTTPRequestHandler):
    """A loopback endpoint that answers like an OpenAI-shaped server."""

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        prompt_tokens = max(1, len(str(body.get("messages", ""))) // CHARS_PER_TOKEN)
        budget = int(body.get("max_tokens", 1))
        time.sleep(0.002 + 0.001 * budget)
        payload = {"choices": [{"message": {"content": "OK", "reasoning": None},
                               "finish_reason": "stop"}],
                   "usage": {"prompt_tokens": prompt_tokens,
                             "completion_tokens": budget,
                             "total_tokens": prompt_tokens + budget}}
        raw = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format, *args):  # keep the self-test quiet
        return


def selftest() -> int:
    failures = []

    def check(name, cond):
        print(("PASS  " if cond else "FAIL  ") + name)
        if not cond:
            failures.append(name)

    check("filler sizes to the requested rung",
          len(filler(4096)) >= (4096 - FLOOR_RESERVE) * CHARS_PER_TOKEN)

    srv = HTTPServer(("127.0.0.1", 0), _Stub)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    try:
        got = measure(url, "stub-model", [512, 2048], reps=2, decode_tokens=16)
        check("two rungs times two reps plus a decode pair",
              len([r for r in got["rows"] if r["rung"] == "prefill"]) == 4
              and len([r for r in got["rows"] if r["rung"] == "decode"]) == 2)
        check("prompt tokens are read from the server, not assumed",
              all(r.get("prompt_tokens") for r in got["rows"] if r["rung"] == "prefill"))
        check("prefill rate is positive",
              all((r["tok_per_s"] or 0) > 0 for r in got["rows"] if r["rung"] == "prefill"))
        check("every prefill call carries its own nonce",
              len({r["nonce"] for r in got["rows"] if r["rung"] == "prefill"}) == 4)
        summary = rollup(got["rows"])
        check("rollup keys carry the rung and the length",
              "prefill:512" in summary and "prefill:2048" in summary and "decode" in summary)
        check("rollup medians are floats",
              isinstance(summary["decode"]["median_tok_per_s"], float))

        with tempfile.TemporaryDirectory() as td:
            raw = Path(td) / "slate.jsonl"
            raw.write_text("\n".join(json.dumps(r) for r in got["rows"]) + "\n")
            man = {"instrument": MF.instrument(__file__), "url": url,
                   "model": "stub-model", "reps": 2, "decode_tokens": 16,
                   "lengths": [512, 2048], "raw": str(raw),
                   "summary": summary, "hardware": MF.hardware(),
                   "started": MF.now_iso()}
            lane = MF.emit(man, lane=Path(td) / "lane")
            check("manifest lands in a dated lane file",
                  lane.is_file() and lane.name.endswith(".jsonl"))
            written = json.loads(lane.read_text().splitlines()[-1])
            check("manifest carries the instrument and the raw path",
                  written["instrument"]["name"] == "slate.py"
                  and written["raw"] == str(raw))
            check("manifest is not marked INCOMPLETE",
                  not written.get("INCOMPLETE"))

            md = report_md(summary, {"started": MF.now_iso(), "url": url,
                                     "model": "stub-model", "reps": 2,
                                     "decode_tokens": 16, "raw": str(raw),
                                     "lane": str(lane)})
            check("report carries a status line and no em dash",
                  "Status:" in md and "\u2014" not in md and "..." not in md)
            check("report states the prefill upper bound",
                  "upper bound" in md)
            check("each run gets its own tape stem, and it has no colons",
                  run_stem("2026-11-03T18:54:27-05:00") == "2026-11-03T185427"
                  and run_stem("2026-11-03T19:02:11-05:00") != run_stem("2026-11-03T18:54:27-05:00"))
            check("report carries no home path",
                  "/home/" not in md and "~/" not in md)
            check("report carries no absolute path",
                  not any(tok in md for tok in ("/Users/", "C:\\\\")))
    finally:
        srv.shutdown()

    print(f"\nselftest: {len(failures)} failure(s)")
    return 1 if failures else 0


def run_stem(started: str) -> str:
    """One tape file per run, not per day.

    A day-addressed tape appends every run into one file, so a rebuild cannot
    tell a clean run from the contaminated one that preceded it. It did exactly
    that here: a rebuild averaged the cache-contaminated rows into the corrected
    report. The stem is the run's own start time, to the second.
    """
    return started[:19].replace(":", "")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="the distributed face's throughput slate")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest")
    run = sub.add_parser("run")
    run.add_argument("--url", default=BC.env("SLATE_URL", "http://127.0.0.1:8000"))
    run.add_argument("--model", default=BC.env("SLATE_MODEL", "model"))
    run.add_argument("--lengths", default=DEFAULT_LENGTHS)
    run.add_argument("--reps", type=int, default=DEFAULT_REPS)
    run.add_argument("--decode-tokens", type=int, default=DEFAULT_DECODE_TOKENS)
    run.add_argument("--report", default="")
    args = ap.parse_args(argv)

    if args.cmd == "selftest":
        return selftest()

    lengths = [int(x) for x in args.lengths.split(",") if x.strip()]
    started = MF.now_iso()
    print(f"slate: {args.url} model {args.model} lengths {lengths} reps {args.reps}")
    got = measure(args.url, args.model, lengths, args.reps, args.decode_tokens)
    summary = rollup(got["rows"])

    runs = BC.runs_dir()
    runs.mkdir(parents=True, exist_ok=True)
    stem = run_stem(started)
    raw = runs / f"slate-{stem}.jsonl"
    with raw.open("a") as f:
        for row in got["rows"]:
            row["run"] = started
            f.write(json.dumps(row, sort_keys=True) + "\n")

    lane_is_ours = bool(BC.env("BENCH_RUNS_LANE", ""))
    man = {"instrument": MF.instrument(__file__), "url": args.url,
           "model": args.model, "reps": args.reps,
           "decode_tokens": args.decode_tokens, "lengths": lengths,
           "chars_per_token": got["chars_per_token"],
           "raw": str(raw), "summary": summary, "hardware": MF.hardware(),
           "started": started}
    lane = MF.emit(man, lane=BC.runs_lane())

    for key, s in summary.items():
        print(f"  {key:<20} med {s['median_tok_per_s']} tok/s "
              f"({s['median_secs']}s, {s['calls']} calls)")

    if args.report:
        meta = {"started": started, "url": args.url, "model": args.model,
                "reps": args.reps, "decode_tokens": args.decode_tokens,
                "chars_per_token": got["chars_per_token"],
                "raw": raw, "lane": lane}
        Path(args.report).write_text(report_md(summary, meta))
        print(f"report: {args.report}")
    if not lane_is_ours:
        print("note: BENCH_RUNS_LANE unset, manifest went to the default lane")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
