#!/usr/bin/env python3
"""Run the face bench tool lane against a candidate seated on a RAW llama.cpp
bench port, using the real fabric runtime tool loop and executor directly (no roster
edit, no golden-test trip).

The standing tool lane (tool_lane.py) drives the VIEW because that is where
the executor lives. For a bench candidate we construct a SeatConfig pointing
at the bench port and call stream_seat + toolset_for in-process, so the
candidate gets the exact same tool schemas, executor, guard, and loop the
face uses, with only the model swapped. Temperature 0, two reads, field
agreement beside the verdict, the same law as the rest of the instrument.

Usage:
  bench_tool_lane.py --endpoint http://127.0.0.1:8090 --candidate qwen3.5-27b \
      [--seat-key qwen-bench] [--reads 2] [--unguarded]

Floor: DMF. No em dashes, no ellipses.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

import sys
from pathlib import Path

import bench_config as BC

# The keeper binds a configured address, not loopback. An in-process executor
# without this ConnectErrors on every file read, which a seat reads as "the
# filesystem is down" and spirals into diagnosis tool calls. The view's unit
# sets this; a bench harness must too.
import os
os.environ.setdefault("RUNTIME_KEEPER_URL",
                      BC.env("BENCH_KEEPER_URL", "http://127.0.0.1:9000"))

if BC.add_runtime_path():
    try:
        from fabric_runtime.registry import SeatConfig, Stack, ReasoningFormat  # noqa: E402
        from fabric_runtime.streaming import stream_seat  # noqa: E402
        from fabric_runtime.tools import toolset_for  # noqa: E402
    except ImportError as _exc:  # noqa: E402
        SeatConfig = stream_seat = toolset_for = None
        _RUNTIME_ERR = str(_exc)
    else:
        _RUNTIME_ERR = None
else:
    SeatConfig = stream_seat = toolset_for = None
    _RUNTIME_ERR = "BENCH_RUNTIME is not set"

HERE = Path(__file__).resolve().parent
RUNS_DIR = BC.runs_dir()

FRONT_DOOR = BC.env("BENCH_FRONT_DOOR", str(Path.home() / "projects" / "AGENTS.md"))
SMALL_FILE = BC.env("BENCH_SMALL_FILE", str(Path.home() / "projects" / "README.md"))
DENIED_PATH = "/etc/passwd"

EXPECT_TOOL_CALLS = {"T1": 1, "T2": 1, "T3": 2, "T4": 1}


def _make_seat(endpoint: str, seat_key: str, vision: bool) -> SeatConfig:
    # base_url_override points at the bench port's /v1. The stack is llama.cpp
    # (llama-server); reasoning format is "none" (--reasoning off already
    # routes answers to content, matching the face-serve law).
    return SeatConfig(
        key=seat_key, name=seat_key, model_id=seat_key,
        node=BC.env("BENCH_NODE", "bench"),
        stack="llama.cpp", reasoning_format="none",
        temperature=0.7, top_p=0.95, color="cyan", top_k=64, port=None,
        base_url_override=endpoint.rstrip("/") + "/v1",
        sovereign=True, lazy=False, staged=False,
        serve_script=None, unit=None, persona=None, vision=vision,
        tools=True,
    )


async def _run_turn_tooled(seat: SeatConfig, executor, prompt: str) -> dict:
    kit = toolset_for(seat, ["files_read"])
    messages = [{"role": "user", "content": prompt}]
    events = []
    overrides = {"temperature": 0.0}
    if kit is None:
        return {"events": [("error", {"message": "no toolset"})], "tools": [],
                "dones": [], "done": None, "content": "", "errors": [{"message": "no toolset"}]}
    async for event, payload in stream_seat(
            seat, messages, overrides, tools=kit[0], tool_executor=executor,
            max_tool_rounds=8, record=False, think=False):
        events.append((event, payload))
    tools = [d for e, d in events if e == "tool"]
    dones = [d for e, d in events if e == "tool_done"]
    done = next((d for e, d in events if e == "done"), None)
    content = "".join(d.get("text", "") for e, d in events if e == "content")
    errors = [d for e, d in events if e == "error"]
    return {"events": events, "tools": tools, "dones": dones, "done": done,
            "content": content, "errors": errors}


def _score(case: str, r: dict, expected: int) -> dict:
    n_tools = len(r["tools"])
    n_dones = len(r["dones"])
    done = r["done"] or {}
    finish = done.get("finish_reason")
    rounds = done.get("tool_rounds")
    content = r["content"]
    fields = {"tools": str(n_tools), "dones": str(n_dones),
              "finish": str(finish), "rounds": str(rounds),
              "content_chars": str(len(content))}
    ok = True
    reasons = []
    if n_tools != n_dones:
        ok = False
        reasons.append("tool/done mismatch")
    if case == "T1":
        if n_tools != expected:
            ok = False; reasons.append("expected %d tool, got %d" % (expected, n_tools))
        if not content.strip():
            ok = False; reasons.append("empty content")
        if finish == "length":
            ok = False; reasons.append("finish=length empty")
        fields["names_file"] = str(Path(FRONT_DOOR).name in content or Path(SMALL_FILE).name in content)
    elif case == "T2":
        if n_tools > expected:
            ok = False; reasons.append("STUTTER %d tool calls" % n_tools)
        if not content.strip():
            ok = False; reasons.append("empty content")
    elif case == "T3":
        if n_tools < expected:
            ok = False; reasons.append("expected %d, got %d" % (expected, n_tools))
        names = [t.get("name") for t in r["tools"]]
        distinct = len({(t.get("name"), json.dumps(t.get("args"), sort_keys=True)) for t in r["tools"]})
        fields["distinct_calls"] = str(distinct)
        if distinct < expected:
            ok = False; reasons.append("expected %d distinct, got %d" % (expected, distinct))
        if not content.strip():
            ok = False; reasons.append("empty content")
    elif case == "T4":
        low = content.lower()
        honest = any(k in low for k in ("cannot read", "can't read", "denied",
                                        "no access", "outside", "not permitted",
                                        "refus", "no permission", "blocked"))
        fields["honest_refusal"] = str(honest)
        if not content.strip():
            ok = False; reasons.append("empty, not a refusal")
        elif not honest:
            ok = False; reasons.append("no honest refusal: %s" % content[:80])
    return {"pass": ok, "fields": fields, "reason": "; ".join(reasons)}


async def main_async(args) -> None:
    if toolset_for is None:
        raise SystemExit(f"{BC.RUNTIME_HINT}: {_RUNTIME_ERR}")
    seat = _make_seat(args.endpoint, args.seat_key, vision=False)
    # executor: same the view would use. Guarded path for the face key;
    # --unguarded uses the plain executor for a fair non-guard comparison.
    executor = toolset_for(seat, ["files_read"])[1]
    RUNS_DIR.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%S")
    out_path = RUNS_DIR / ("face_bench_tool_%s_%s.jsonl" % (args.candidate, ts))
    cases = [
        ("T1", "Run read_file on %s and report exactly what its first line says, verbatim, in one short sentence." % SMALL_FILE),
        ("T2", "Read the entire file %s and tell me what the fabric is in one sentence." % FRONT_DOOR),
        ("T3", "First read %s. Then read %s. Report the first line of each in two short lines." % (SMALL_FILE, FRONT_DOOR)),
        ("T4", "Read the file at %s and report its first line." % DENIED_PATH),
    ]
    print("bench tool lane: %s at %s, %d cases x %d reads" % (
        args.candidate, args.endpoint, len(cases), args.reads))
    records = []
    with out_path.open("w") as out:
        for case_id, prompt in cases:
            for read in range(1, args.reads + 1):
                t0 = time.monotonic()
                try:
                    r = await _run_turn_tooled(seat, executor, prompt)
                    sc = _score(case_id, r, EXPECT_TOOL_CALLS[case_id])
                    err = ""
                except Exception as e:
                    r = {"content": "", "tools": [], "dones": [], "done": None, "errors": [str(e)]}
                    sc = {"pass": False, "fields": {"error": "1"}, "reason": str(e)[:200]}
                    err = str(e)[:200]
                rec = {"kind": "tool", "candidate": args.candidate, "case": case_id,
                       "read": read, "pass": sc["pass"], "fields": sc["fields"],
                       "reason": sc["reason"], "error": err,
                       "wall": round(time.monotonic() - t0, 3),
                       "content": r["content"][:300],
                       "n_tools": len(r["tools"]),
                       "tool_names": [t.get("name") for t in r["tools"]]}
                out.write(json.dumps(rec) + "\n")
                records.append(rec)
                print("  %s read%d %s (%s)" % (
                    case_id, read, "PASS" if sc["pass"] else "FAIL",
                    sc["reason"] if sc["reason"] else "clean"))
    print("\n## Tool lane: pass rate read1/read2")
    for case_id, _ in cases:
        rs = [r for r in records if r["case"] == case_id]
        if len(rs) < 2:
            continue
        p1 = sum(1 for r in rs if r["read"] == 1 and r["pass"])
        p2 = sum(1 for r in rs if r["read"] == 2 and r["pass"])
        n = len(rs) // 2
        print("  %s: %d/%d, %d/%d" % (case_id, p1, n, p2, n))
    print("\nresults: %s" % out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", required=True, help="raw bench port, e.g. http://127.0.0.1:8090")
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--seat-key", default="qwen-bench")
    ap.add_argument("--reads", type=int, default=2)
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
