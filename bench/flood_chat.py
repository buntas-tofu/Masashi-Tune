#!/usr/bin/env python3
"""Chat-path flood: the governor must trim a client-shipped oversized
transcript before the serve edge, so the 08-20 400 class cannot recur.
Uses /api/chat (tools off, so no tool loop), asserts a 'context' event
naming the trim and a clean 'done'."""
import json
import time
import urllib.request

import bench_config as BC

WINDOW = 65_536
BUDGET = WINDOW - 2_048  # the governor's default reserve

# Ship a transcript that clears the budget by a wide margin (~80k tokens est
# after the view adds persona + warmth, budget is 63,488). The governor must
# trim oldest history, keep system + final turn, and name it.
msgs = [{"role": "system", "content": "You are a bench assistant."}]
for i in range(50):
    msgs.append({"role": "user", "content": f"history {i}: " + "the bar keeps its own ledger. " * 150})
    msgs.append({"role": "assistant", "content": f"reply {i}: " + "the keeper counts the tabs. " * 150})
msgs.append({"role": "user",
             "content": "The conversation above is long. Just say FLOOD_OK and nothing else."})
raw_chars = sum(len(m["content"]) for m in msgs)
print(f"shipping {raw_chars:,} chars (~{raw_chars//4:,} tokens est) against budget {BUDGET}")

body = json.dumps({"seat": BC.env("BENCH_SEAT", "bench-candidate"),
                   "messages": msgs, "tools": False}).encode()
req = urllib.request.Request(BC.env("BENCH_VIEW", "http://127.0.0.1:8088") + "/api/chat",
                             data=body,
                             headers={"Content-Type": "application/json"})
t0 = time.time()
context_ev = None
content = ""
done_ev = None
error_ev = None
cur = None
with urllib.request.urlopen(req, timeout=240) as resp:
    assert resp.status == 200, f"HTTP {resp.status}"
    for raw in resp:
        line = raw.decode("utf-8", "replace").strip()
        if line.startswith("event:"):
            cur = line[6:].strip()
            continue
        if not line.startswith("data:"):
            continue
        try:
            data = json.loads(line[5:].strip())
        except json.JSONDecodeError:
            continue
        if cur == "context":
            context_ev = data
        elif cur == "content":
            content += data.get("text", "")
        elif cur == "done":
            done_ev = data
        elif cur == "error":
            error_ev = data
dt = time.time() - t0
print(f"wire: HTTP 200, {dt:.1f}s")
assert error_ev is None, f"wire error: {error_ev}"
assert done_ev is not None, "no done event"
assert context_ev is not None, "governor never fired on the chat path (BAD)"
print(f"context event: trimmed={context_ev.get('trimmed')} "
      f"used_est={context_ev.get('used_tokens_est')} "
      f"budget={context_ev.get('budget_tokens')} "
      f"headroom={context_ev.get('headroom_tokens')}")
assert context_ev["used_tokens_est"] <= BUDGET, "governor left the assembly over budget"
assert context_ev["trimmed"] > 0, "no trim reported despite the flood"
print(f"answer: {content.strip()[:120]}")
print("CHAT-PATH FLOOD: PASS, the 400 class is closed")
