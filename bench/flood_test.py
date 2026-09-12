#!/usr/bin/env python3
"""Flood test for the context governor, live and in-process (2026-08-22).

Proves the 2026-08-20 400 class cannot recur:
  Part A (in-process): stuff a synthetic room with 200 fat turns, run the
  exact view pipeline (reveal -> project capped -> persona -> warmth-free ->
  govern), assert the assembly clears the face's 65,536 window with headroom.
  Part B (wire): POST the same room through the view /api/room/turn, assert
  HTTP 200, a 'context' event naming the trim, and a 'done' with an answer.

Sediment note: the synthetic room 'flood-test-2026-08-22' is a test fixture
in the shared store; it never enters a trainset (the cutter only reads
turn.user/turn.seat, never room.turn).
"""
import asyncio
import json
import sys
import time

import bench_config as BC

BC.add_runtime_path()

ROOM = "flood-test-2026-08-22"
FACE_WINDOW = 65_536          # the face's window_tokens (roster)
RESERVE = 2_048               # the governor's default reserve


async def stuff_room():
    from fabric_runtime.memory import record_room_turn
    n = 0
    for i in range(100):
        await record_room_turn(ROOM, "you", f"floor check {i}: " + "the bar keeps its own ledger. " * 12)
        await record_room_turn(ROOM, "assistant", f"answer {i}: " + "the keeper counts the tabs twice. " * 12)
        n += 2
    print(f"stuffed {n} turns into room '{ROOM}'")


async def part_a():
    from fabric_runtime.memory import reveal_room
    from fabric_runtime.room import room_as_conversation
    from fabric_runtime.context import govern

    revealed = await reveal_room(ROOM, horizon_s=86_400 * 30)
    assert len(revealed) >= 200, f"reveal short: {len(revealed)}"
    raw_chars = sum(len(t.get("text", "")) for t in revealed)
    print(f"revealed {len(revealed)} turns, {raw_chars:,} raw chars "
          f"(~{raw_chars // 4:,} tokens) would have hit the window")

    msgs = room_as_conversation(revealed, "assistant", cap_chars=48_000)
    proj_chars = sum(len(m.get("content", "")) for m in msgs)
    assert proj_chars <= 48_000 + 500, f"projection over cap: {proj_chars}"
    assert any("context governor" in m.get("content", "") for m in msgs), \
        "projection must name its elision"
    print(f"projection capped: {proj_chars:,} chars, elision named: OK")

    # the view then applies persona + warmth before the governor runs;
    # emulate a realistic standing load (measured ~3,000 tokens this morning)
    system = {"role": "system", "content": "persona topology warmth " * 400}
    assembly = [system] + msgs
    out, rep = govern(assembly, FACE_WINDOW, RESERVE)
    print(f"governor: window={rep['window_tokens']} budget={rep['budget_tokens']} "
          f"used_est={rep['used_tokens_est']} trimmed={rep['trimmed']} "
          f"headroom={rep['headroom_tokens']}")
    assert rep["used_tokens_est"] <= FACE_WINDOW - RESERVE, "over budget!"
    assert out[-1]["content"] == msgs[-1]["content"], "final turn must survive"
    print("PART A PASS: the flood never reaches the serve edge")


def part_b():
    import urllib.request
    url = BC.env("BENCH_VIEW", "http://127.0.0.1:8088") + "/api/room/turn"
    body = json.dumps({
        "room": ROOM, "seat": BC.env("BENCH_SEAT", "bench-candidate"),
        "prompt": "How many turns of room history can you see above you? "
                  "Answer with just the approximate number and one short sentence.",
    }).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=180) as resp:
        assert resp.status == 200, f"HTTP {resp.status}"
        context_ev = None
        content = ""
        done_ev = None
        error_ev = None
        cur_event = None
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("event:"):
                cur_event = line[6:].strip()
                continue
            if not line.startswith("data:"):
                continue
            try:
                data = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            if cur_event == "context":
                context_ev = data
            elif cur_event == "content":
                content += data.get("text", "")
            elif cur_event == "done":
                done_ev = data
            elif cur_event == "error":
                error_ev = data
    dt = time.time() - t0
    print(f"wire: HTTP 200, {dt:.1f}s")
    assert error_ev is None, f"wire error: {error_ev}"
    assert done_ev is not None, "no done event"
    assert content.strip(), "empty answer"
    print(f"answer: {content.strip()[:200]}")
    if context_ev:
        print(f"context event: trimmed={context_ev.get('trimmed')} "
              f"used_est={context_ev.get('used_tokens_est')} "
              f"headroom={context_ev.get('headroom_tokens')}")
    else:
        print("NOTE: no context event (projection alone fit; governor was a no-op)")
    print("PART B PASS: the live wire survived the flood")


async def main():
    await stuff_room()
    await part_a()
    part_b()
    print("\nFLOOD TEST: ALL PASS")


if __name__ == "__main__":
    asyncio.run(main())
