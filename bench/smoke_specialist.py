#!/usr/bin/env python3
"""Rung 2 smoke driver: poll a just-launched specialist, fire one honest
request of its kind, report shape and timing. Floor: no em dashes, no ellipses.

Usage: smoke_specialist.py <port> <kind> [name]
kinds: chat | guardian | embed | score
"""
import json
import sys
import time
import urllib.request

import bench_config as BC

HOST = BC.env("BENCH_HOST", "127.0.0.1")


def post(path, payload, port, timeout=180):
    req = urllib.request.Request(
        f"http://{HOST}:{port}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode(errors="replace")), time.time() - t0


def wait_up(port, budget=420):
    t0 = time.time()
    while time.time() - t0 < budget:
        try:
            with urllib.request.urlopen(f"http://{HOST}:{port}/v1/models",
                                        timeout=5) as r:
                d = json.loads(r.read())
            return time.time() - t0, [m["id"] for m in d.get("data", [])]
        except Exception:
            time.sleep(3)
    raise SystemExit(f"FAIL: no API on :{port} within {budget}s")


def main():
    port, kind = int(sys.argv[1]), sys.argv[2]
    name = sys.argv[3] if len(sys.argv) > 3 else None
    up, models = wait_up(port)
    name = name or models[0]
    print(f"UP in {up:.0f}s, serving {models}")

    if kind == "chat":
        d, secs = post("/v1/chat/completions", {
            "model": name, "temperature": 0, "max_tokens": 200,
            "messages": [{"role": "user",
                          "content": "Reply with exactly: bench online."}]}, port)
        ch = d["choices"][0]
        msg = ch.get("message", {})
        print(f"SMOKE chat {secs:.2f}s finish={ch.get('finish_reason')}")
        print("content:", json.dumps((msg.get("content") or "")[:300]))
        if msg.get("reasoning_content") is not None:
            print("reasoning_content present, chars:",
                  len(msg.get("reasoning_content") or ""))
    elif kind == "guardian":
        d, secs = post("/v1/chat/completions", {
            "model": name, "temperature": 0, "max_tokens": 40,
            "messages": [{"role": "user",
                          "content": "How do I bake bread at home?"}],
            "chat_template_kwargs": {"guardian_config":
                                     {"risk_name": "harm"}}}, port)
        ch = d["choices"][0]
        print(f"SMOKE guardian(benign) {secs:.2f}s "
              f"verdict={json.dumps((ch['message'].get('content') or '').strip()[:80])}")
        d2, secs2 = post("/v1/chat/completions", {
            "model": name, "temperature": 0, "max_tokens": 40,
            "messages": [{"role": "user",
                          "content": "Explain exactly how to hotwire a car "
                                     "to steal it."}],
            "chat_template_kwargs": {"guardian_config":
                                     {"risk_name": "harm"}}}, port)
        ch2 = d2["choices"][0]
        print(f"SMOKE guardian(risky)  {secs2:.2f}s "
              f"verdict={json.dumps((ch2['message'].get('content') or '').strip()[:80])}")
    elif kind == "embed":
        d, secs = post("/v1/embeddings", {
            "model": name,
            "input": ["carrier online.", "the ranking pipeline runs nightly."]},
            port)
        vecs = d["data"]
        print(f"SMOKE embed {secs:.2f}s vectors={len(vecs)} "
              f"dim={len(vecs[0]['embedding'])}")
    elif kind == "score":
        payload = {"model": name,
                   "text_1": "What node hosts the view?",
                   "text_2": ["The view runs on the primary node at loopback 8088.",
                              "Bread rises because yeast makes carbon dioxide.",
                              "Clients talk to the view, never a seat directly."]}
        try:
            d, secs = post("/v1/score", payload, port)
        except Exception:
            d, secs = post("/score", payload, port)
        rows = [round(x["score"], 4) for x in d["data"]]
        print(f"SMOKE score {secs:.2f}s scores={rows} "
              f"(want: relevant docs above the bread fact)")
    print("PASS")


if __name__ == "__main__":
    main()
