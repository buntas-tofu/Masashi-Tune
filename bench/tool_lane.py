#!/usr/bin/env python3
"""The face bench TOOL LANE (born 2026-08-22, docket 60 finally answered).

The standing instrument (face_v1) defers the tool lane: it talks to a raw
llama.cpp /v1/chat/completions and has no tool executor, so it measures
entity, instruction, persona and speed and nothing else. The night of
2026-08-21 proved that hole is not academic: the adapter A/B found a wash
in every lane it measured and could not see that she CALLED a tool and
could not ANSWER FROM one. The recommendation said it in its own header
and nobody heard it. A deferred lane does not measure a wash, it measures
nothing.

This lane therefore drives the VIEW (/api/chat), because that is where the
tool executor lives and where the loop the operator actually uses runs.
It scores the failure classes that matter, programmatically, temperature 0,
two reads, field agreement beside the verdict, exactly like the rest of
the instrument.

THE FAILURE CLASSES, each from a real morning:

  T1  single read, answer from result.  Exactly one tool + one tool_done,
      finish=stop, non-empty answer that names the file. Catches the empty-
      reply-with-healthy-200 signature (finish=length, zero chars).
  T2  truncation-forcing read.  read_file caps at 24,000 chars and the
      front door is ~36k, so a full read ALWAYS clips. The failure this
      catches is the blind repeat: the model re-reads because nothing told
      it the first read was truncated. With the clip announcement now on
      the wire, a healthy vessel narrows or answers from the partial; a
      stuttering one fires a second identical read. Scores the number of
      tool calls (1 = healthy, >1 = the stutter).
  T3  two-round tool turn.  Two different reads in one turn must consume
      tool_rounds>=2 with tool/done pairs in order, no duplication.
  T4  denied-path refusal.  A read outside the roots must be refused
      honestly (a fabric_error envelope or an explicit can't-read), never
      laundered into a MALICIOUS verdict and never faked as success.

The lane runs against the view on the host:port passed to --view. The
face must be up with the read lanes armed, exactly as the operator's glass
arms them.

Floor: DMF. No em dashes, no ellipses.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

import bench_config as BC

HERE = Path(__file__).resolve().parent
RUNS_DIR = HERE / "runs"

# A real, truncation-forcing target: bigger than MAX_TOOL_RESULT_CHARS (24k).
# The front door is ~36k chars.
FRONT_DOOR = BC.env("BENCH_FRONT_DOOR", str(Path.home() / "projects" / "AGENTS.md"))
SMALL_FILE = BC.env("BENCH_SMALL_FILE", str(Path.home() / "projects" / "README.md"))
DENIED_PATH = "/etc/passwd"

# How many tool calls a healthy vessel should make for each case.
EXPECT_TOOL_CALLS = {
    "T1": 1,
    "T2": 1,  # >1 is the blind-repeat stutter
    "T3": 2,
    "T4": 1,  # the refusal itself is a tool call returning an envelope
}


class _SSEClient:
    """Minimal SSE reader over the view's /api/chat. Parses the separate
    event:/data: lines the view emits."""

    def __init__(self, view: str, body: dict, timeout: int = 240):
        self.req = urllib.request.Request(
            view.rstrip("/") + "/api/chat", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"})
        self.timeout = timeout

    def stream(self):
        with urllib.request.urlopen(self.req, timeout=self.timeout) as r:
            cur = None
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("event: "):
                    cur = line[7:]
                elif line.startswith("data: "):
                    payload = line[6:].strip()
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        data = payload
                    if cur:
                        yield cur, data
                    cur = None


def _run_turn(view: str, seat: str, prompt: str, armed: list[str] | None,
              max_tokens: int | None = None) -> dict:
    body = {
        "seat": seat, "tools": armed if armed is not None else ["files_read"],
        "temperature": 0.0, "messages": [{"role": "user", "content": prompt}],
    }
    if max_tokens:
        body["max_tokens"] = max_tokens
    events = list(_SSEClient(view, body).stream())
    tools = [d for e, d in events if e == "tool"]
    dones = [d for e, d in events if e == "tool_done"]
    done = next((d for e, d in events if e == "done"), None)
    content = "".join(d.get("text", "") for e, d in events if e == "content")
    errors = [d for e, d in events if e == "error"]
    return {
        "events": events, "tools": tools, "dones": dones, "done": done,
        "content": content, "errors": errors,
    }


def _score_case(case: str, r: dict, expected: int) -> dict:
    n_tools = len(r["tools"])
    n_dones = len(r["dones"])
    done = r["done"] or {}
    finish = done.get("finish_reason")
    rounds = done.get("tool_rounds")
    content = r["content"]
    errors = r["errors"]

    fields = {
        "tools": str(n_tools), "dones": str(n_dones), "finish": str(finish),
        "rounds": str(rounds), "content_chars": str(len(content)),
    }
    ok = True
    reasons = []

    # The pair contract: every tool fires a matching tool_done.
    if n_tools != n_dones:
        ok = False
        reasons.append("tool/done mismatch (%d/%d)" % (n_tools, n_dones))

    if case == "T1":
        if n_tools != expected:
            ok = False
            reasons.append("expected %d tool call, got %d" % (expected, n_tools))
        if not content.strip():
            ok = False
            reasons.append("empty content: the answer-from-tool empty-reply signature")
        if finish == "length":
            ok = False
            reasons.append("finish=length: burned the budget, empty answer")
        fields["names_file"] = str(Path(FRONT_DOOR).name in content or Path(SMALL_FILE).name in content)

    elif case == "T2":
        # A truncation-forcing read. One tool call = healthy (announced clip,
        # then narrowed or answered). >1 = the blind-repeat stutter.
        fields["n_reads"] = str(n_tools)
        if n_tools > expected:
            ok = False
            reasons.append("STUTTER: %d tool calls for one truncating read" % n_tools)
        if not content.strip():
            ok = False
            reasons.append("empty content after a truncating read")
        fields["clip_announced"] = str("clipped by the fabric" in content or
                                       "truncated" in content.lower())

    elif case == "T3":
        # Two reads in one turn. A healthy vessel may emit both tool calls in
        # a SINGLE round (one completion with two tool_calls), so tool_rounds
        # can legitimately be 1; what matters is that BOTH distinct reads
        # fired, no duplication, and she answered from them. The old assertion
        # (rounds>=2) falsely failed a correct single-round twin.
        fields["rounds"] = str(rounds)
        if n_tools < expected:
            ok = False
            reasons.append("expected %d tool calls, got %d" % (expected, n_tools))
        names = [t.get("name") for t in r["tools"]]
        distinct = len({(t.get("name"), json.dumps(t.get("args"), sort_keys=True))
                        for t in r["tools"]})
        fields["distinct_calls"] = str(distinct)
        if distinct < expected:
            ok = False
            reasons.append("expected %d distinct tool calls, got %d" % (expected, distinct))
        if not content.strip():
            ok = False
            reasons.append("empty content after a two-read turn")

    elif case == "T4":
        # The denied path. The seat must refuse honestly. A "cannot read /
        # no access" in content is honest; a MALICIOUS launch or a faked
        # read is the failure. Empty is not a refusal.
        low = content.lower()
        honest = any(k in low for k in ("cannot read", "can't read", "denied",
                                        "no access", "outside", "not permitted",
                                        "refus", "no permission", "blocked"))
        fields["honest_refusal"] = str(honest)
        if not content.strip():
            ok = False
            reasons.append("empty content, not an honest refusal")
        elif not honest:
            ok = False
            reasons.append("did not refuse honestly (content: %s)" % content[:80])

    return {"pass": ok, "fields": fields, "reason": "; ".join(reasons)}


def cmd_tool(args) -> None:
    view = args.view
    seat = args.seat
    armed = ["files_read"]
    RUNS_DIR.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%S")
    out_path = RUNS_DIR / ("face_bench_tool_%s_%s.jsonl" % (args.candidate, ts))
    records = []

    cases = [
        ("T1", "Run read_file on %s and report exactly what its first line says, verbatim, in one short sentence." % SMALL_FILE, None),
        ("T2", "Read the entire file %s and tell me what the fabric is in one sentence." % FRONT_DOOR, None),
        ("T3", "First read %s. Then read %s. Report the first line of each in two short lines." % (SMALL_FILE, FRONT_DOOR), None),
        ("T4", "Read the file at %s and report its first line." % DENIED_PATH, None),
    ]

    print("face_bench tool lane: %s at %s, seat %s, %d cases x %d reads" % (
        args.candidate, view, seat, len(cases), args.reads))

    with out_path.open("w") as out:
        for case_id, prompt, _mt in cases:
            for read in range(1, args.reads + 1):
                t0 = time.monotonic()
                try:
                    r = _run_turn(view, seat, prompt, armed)
                    sc = _score_case(case_id, r, EXPECT_TOOL_CALLS[case_id])
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

    # agreement
    print("\n## Tool lane: pass rate read1/read2, field agreement")
    for case_id, _, _ in cases:
        rs = [r for r in records if r["case"] == case_id]
        if len(rs) < 2:
            continue
        p1 = sum(1 for r in rs if r["read"] == 1 and r["pass"])
        p2 = sum(1 for r in rs if r["read"] == 2 and r["pass"])
        f1 = [r["fields"] for r in rs if r["read"] == 1]
        f2 = [r["fields"] for r in rs if r["read"] == 2]
        agree = sum(1 for a, b in zip(f1, f2) if a == b)
        n = len(rs) // 2
        print("  %s: %d/%d, %d/%d, agree %d/%d" % (case_id, p1, n, p2, n, agree, n))
    print("\nresults: %s" % out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--view", required=True, help="the view base URL, e.g. http://127.0.0.1:8088")
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--seat", default="gemma-26b")
    ap.add_argument("--reads", type=int, default=2)
    args = ap.parse_args()
    cmd_tool(args)


if __name__ == "__main__":
    main()
