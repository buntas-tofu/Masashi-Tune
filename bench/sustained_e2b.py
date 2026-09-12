#!/usr/bin/env python3
"""The sustained run: E2B resident on the bench card through the night, and whether it holds.

Operator directive 2026-08-04 late: stage the overnight and keep an E2B on
the bench card for the full measurement set. The bounded heat gave the quality
verdict (rung 7 upset, gate 1 cross-silicon arms); this supplies the sustained
half: the same frozen 120 records looped serially at temperature 0 until a
wall-clock deadline, half-hour windows reported, so a latency or quality drift
over the night is the machine changing, never the work getting harder. Method
constraints inherited from sustained.py: one call in flight (llama.cpp one
slot law), the frozen sample, temperature 0.

The serve is EYELESS per the current serving ruling, on the bench card which
carries nothing else tonight, so this is the clean-card sustained condition. The
deployment-condition sustained run (the candidate beside live seats) belongs
to a later gate, where it is honest, and is deliberately not simulated here.

Resilience: five consecutive call failures trigger one serve restart; a second
run of five aborts with status ABORTED_ERRORS rather than looping on a corpse.

Usage: sustained_e2b.py [--until HH:MM]   (default 04:45)

Floor: DMF. No em dashes, no ellipses.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import setlist  # noqa: E402
import manifest as MF  # noqa: E402
import bench_config as BC  # noqa: E402

RUNS = BC.runs_dir()
PORT = int(BC.env("BENCH_PORT", "8089"))
HOST = BC.env("BENCH_HOST", "127.0.0.1")
MODEL_DIR = BC.models_dir() / "gemma-4-e2b-ud"
GGUF = "gemma-4-E2B-it-UD-Q4_K_XL.gguf"
PHASE = "e2b-ud@bench"


def serve():
    llama = str(BC.llama_server())
    env = {"CUDA_DEVICE_ORDER": "PCI_BUS_ID", "CUDA_VISIBLE_DEVICES": "0",
           "PATH": "/usr/bin:/bin", "LD_LIBRARY_PATH": str(Path(llama).parent)}
    return subprocess.Popen(
        [llama, "-m", str(MODEL_DIR / GGUF), "--host", HOST, "--port", str(PORT),
         "-ngl", "99", "-c", "8192", "--jinja", "--reasoning-format", "deepseek",
         "--metrics", "--threads", "8"],
        stdout=open("/tmp/sustained-serve.log", "w"), stderr=subprocess.STDOUT, env=env)


def up(tries=30):
    for _ in range(tries):
        try:
            with urllib.request.urlopen(f"http://{HOST}:{PORT}/v1/models", timeout=4) as r:
                if json.loads(r.read())["data"][0]["id"] == GGUF:
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False


def ask(content):
    body = json.dumps({"messages": [{"role": "user", "content": content}],
                       "max_tokens": setlist.MAX_TOKENS,
                       "temperature": setlist.TEMPERATURE,
                       "stream": False}).encode()
    req = urllib.request.Request(f"http://{HOST}:{PORT}/v1/chat/completions",
                                 data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read().decode(errors="replace"))
    msg = (d.get("choices") or [{}])[0].get("message", {}) or {}
    return msg.get("content") or "", time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", default="04:45")
    a = ap.parse_args()
    hh, mm = (int(x) for x in a.until.split(":"))
    end = dt.datetime.now().replace(hour=hh, minute=mm, second=0, microsecond=0)
    if end <= dt.datetime.now():
        end += dt.timedelta(days=1)

    records, digest = setlist.load_sample("operations")
    spec = setlist.TASKS["operations"]
    head = spec.get("head", setlist.HEAD_CHARS)
    tag = setlist.stamp()
    sink = RUNS / f"sustained_{tag}.jsonl"
    start_iso = subprocess.run(["date", "-Is"], capture_output=True, text=True).stdout.strip()

    proc = serve()
    if not up():
        print("serve never came up")
        return 1
    print(f"nestled: {GGUF} on GPU0 at {HOST}:{PORT}, until {end:%H:%M}, "
          f"digest {digest[:16]}", flush=True)

    calls = errs = consec = restarts = 0
    status = "COMPLETE"
    i = 0
    while dt.datetime.now() < end:
        rec = records[i % len(records)]
        i += 1
        row = {"phase": PHASE, "relpath": rec["id"], "pass": i // len(records),
               "task": "operations", "t": time.time()}
        try:
            text, secs = ask(spec["prompt"] % rec["text"][:head])
            parsed = setlist.parse_reply(text)
            row.update(ok=True, secs=round(secs, 3), parsed=parsed is not None,
                       fields=setlist.norm_fields(parsed) if parsed else None)
            calls += 1
            consec = 0
        except Exception as e:
            row.update(ok=False, error=f"{type(e).__name__}: {e}")
            errs += 1
            consec += 1
        with sink.open("a") as f:
            f.write(json.dumps(row) + "\n")
        if consec >= 5:
            if restarts == 0:
                print("five consecutive failures: one serve restart", flush=True)
                proc.terminate()
                time.sleep(3)
                proc = serve()
                restarts, consec = 1, 0
                if not up():
                    status = "ABORTED_ERRORS"
                    break
            else:
                status = "ABORTED_ERRORS"
                break
        if calls and calls % 500 == 0:
            print(f"  {calls} calls, {errs} errors", flush=True)

    proc.terminate()
    per = MF.summarise_jsonl(sink)
    summary = {"tag": tag, "run": "e2b-sustained", "status": status,
               "sample_digest": digest, "calls": calls, "errors": errs,
               "restarts": restarts, "phases": per}
    out = RUNS / f"sustained_{tag}_summary.json"
    out.write_text(json.dumps(summary, indent=1))
    MF.emit({"run": "e2b-sustained", "started": start_iso,
             "instrument": MF.instrument(__file__),
             "vessel": MF.vessel(str(MODEL_DIR), GGUF),
             "serving": {"gpu": f"device={BC.env('BENCH_GPU', '0')}", "port": PORT,
                         "eyeless": True, "co_tenants": "none, clean card"},
             "hardware": MF.hardware(), "raw": str(sink),
             "arms": [{"arm": PHASE, "result": {**summary["phases"].get(PHASE, {}),
                                                "status": status,
                                                "restarts": restarts}}]})
    print(f"wrote {out}; status {status}, {calls} calls, {errs} errors", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
