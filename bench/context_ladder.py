#!/usr/bin/env python3
"""Context ladder: how much context can this serve actually hold?

The unseat's decisive metric was proven context, and the standing method is
n_tokens_max: feed prompts of increasing size until the serve stops
accepting, and record the largest prompt that returns finish=stop with
correct recall from the top of the context. Two reads per rung, field
agreement beside the verdict (house law).

This instrument is model-agnostic: point it at any llama.cpp serve with
--url and it walks the ladder. The needle is a unique marker string placed
at the TOP of the prompt, and the question at the bottom asks for it, so a
correct answer proves recall from the top, not just "it didn't error".

Rung spacing is coarse first (fast), then binary-searches the boundary once
a fail is found. Temperature 0, max_tokens small (we only need the marker).

Usage: context_ladder.py --url http://127.0.0.1:8090 --low 32768 --high 262144
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request


def build_prompt(target_tokens: int, needle: str) -> str:
    """A prompt of approximately target_tokens tokens, needle on top.

    Filler is repetitive but not trivially compressible to the tokenizer in a
    way that breaks length estimates: ~4 chars/token is the house estimate,
    so we size in chars. The needle rides the very first line; the question
    rides the very last.
    """
    filler_unit = (
        "The keeper counts the tabs twice and the ledger keeps its own "
        "rhythm across the long counter of the bar. "
    )
    # ~4 chars per token, leave ~200 tokens for needle + question
    filler_chars = max(0, (target_tokens - 200) * 4)
    repeats = filler_chars // len(filler_unit) + 1
    filler = (filler_unit * repeats)[:filler_chars]
    return (
        f"MARKER-AT-TOP: {needle}\n\n"
        f"{filler}\n\n"
        f"Question: what was the exact MARKER-AT-TOP string at the very "
        f"beginning of this message? Reply with only the marker text."
    )


def probe(url: str, prompt: str, max_tokens: int = 64) -> dict:
    """One completion. Returns {ok, finish, content, tokens_prompt, err}."""
    body = json.dumps({
        "model": "bench",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/v1/chat/completions",
        data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            code = resp.status
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode("utf-8", "replace")[:300]
        return {"ok": False, "finish": None, "content": "",
                "tokens_prompt": 0, "err": f"HTTP {e.code}: {body_txt}",
                "secs": time.time() - t0}
    except Exception as e:
        return {"ok": False, "finish": None, "content": "",
                "tokens_prompt": 0, "err": f"{type(e).__name__}: {e}",
                "secs": time.time() - t0}
    choice = (data.get("choices") or [{}])[0]
    usage = data.get("usage") or {}
    content = (choice.get("message") or {}).get("content") or ""
    return {
        "ok": code == 200,
        "finish": choice.get("finish_reason"),
        "content": content.strip(),
        "tokens_prompt": usage.get("prompt_tokens", 0),
        "err": None,
        "secs": time.time() - t0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8090")
    ap.add_argument("--low", type=int, default=32_768,
                    help="starting prompt size in tokens")
    ap.add_argument("--high", type=int, default=262_144,
                    help="maximum prompt size to attempt")
    ap.add_argument("--step", type=int, default=16_384,
                    help="coarse rung spacing")
    ap.add_argument("--reads", type=int, default=2,
                    help="reads per rung (house law: a single read is not a measurement)")
    args = ap.parse_args()

    needle = f"LEDGER-{int(time.time())}-KEEPS-ITS-OWN-TABS"
    print(f"# context ladder against {args.url}")
    print(f"# needle: {needle}")
    print(f"# range: {args.low} .. {args.high} tokens, coarse step {args.step}")
    print()

    results = []
    last_ok_tokens = 0
    first_fail_tokens = None

    # coarse ascent
    rung = args.low
    while rung <= args.high:
        prompt = build_prompt(rung, needle)
        reads = [probe(args.url, prompt) for _ in range(args.reads)]
        oks = [r for r in reads if r["ok"] and r["finish"] == "stop"
               and needle in r["content"]]
        agree = len({r["content"] for r in reads}) == 1
        max_prompt_tokens = max(r["tokens_prompt"] for r in reads) if reads else 0
        status = "PASS" if len(oks) == len(reads) else "FAIL"
        print(f"rung ~{rung:>7,} tok | prompt_tokens={max_prompt_tokens:>7,} | "
              f"{status} ({len(oks)}/{len(reads)}) | agree={agree} | "
              f"{reads[0]['secs']:.1f}s | {reads[0]['err'] or reads[0]['content'][:50]}")
        results.append({"rung": rung, "prompt_tokens": max_prompt_tokens,
                        "status": status, "reads": reads})
        if status == "PASS":
            last_ok_tokens = max_prompt_tokens or rung
            rung += args.step
        else:
            first_fail_tokens = rung
            break

    # binary search the boundary if we found a fail
    if first_fail_tokens is not None:
        lo, hi = max(args.low, first_fail_tokens - args.step), first_fail_tokens
        print(f"\n# boundary search between {lo:,} and {hi:,}")
        while hi - lo > 2048:
            mid = (lo + hi) // 2
            prompt = build_prompt(mid, needle)
            reads = [probe(args.url, prompt) for _ in range(args.reads)]
            oks = [r for r in reads if r["ok"] and r["finish"] == "stop"
                   and needle in r["content"]]
            max_prompt_tokens = max(r["tokens_prompt"] for r in reads) if reads else 0
            status = "PASS" if len(oks) == len(reads) else "FAIL"
            print(f"  mid {mid:>7,} | prompt_tokens={max_prompt_tokens:>7,} | "
                  f"{status} ({len(oks)}/{len(reads)}) | {reads[0]['err'] or reads[0]['content'][:40]}")
            if status == "PASS":
                lo = mid
                last_ok_tokens = max_prompt_tokens or mid
            else:
                hi = mid
        print(f"\n# boundary: last PASS prompt_tokens = {last_ok_tokens:,}")

    print()
    print(f"VERDICT: largest proven context = {last_ok_tokens:,} tokens")
    if first_fail_tokens is None:
        print(f"  (never failed up to {args.high:,}; the ceiling was not reached)")


if __name__ == "__main__":
    main()
