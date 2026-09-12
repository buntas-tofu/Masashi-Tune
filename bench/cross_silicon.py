#!/usr/bin/env python3
"""Gate 1 of the E2B swap campaign: the bounded heat on every familiar silicon.

Directed by the operator 2026-08-04 evening. The rung 7 upset was measured on
a Blackwell card); reproducibility is a property of the silicon across
platforms (self-J differs by platform on identical weights), so the
board-wide E4B to E2B swap runs this gate first: the same frozen sample, the
same prompt, the same parser, paired arms per silicon.

The matrix is the seats' own homes: the GB10 twins, an AMD bar, and the 4090
(Ada). A redundant Ada point on another node costs nothing, so it is left
out.

DESIGN CHOICES, stated rather than implied:

- Remote arms run against a bench serve ON the target node, called from the
  control host over the configured network. Latency rows therefore include a few milliseconds
  of network, negligible against seconds of inference, and the quality axes
  (parse, self-consistency, grounding) are network-independent.
- The resident seats stay up on every node. That is deliberate: the swap
  deploys the E2B beside exactly those neighbours, so measuring beside them
  is the deployment condition, and the manifest declares them.
- Serves are eyeless (no mmproj), per the same evening's ruling: the
  synaptic layer carries no imagery, so the candidate is measured in the
  configuration it would actually serve.
- Instrument identity: the sample loader, prompt, parser, and normaliser are
  IMPORTED from setlist.py rather than reimplemented, so a row here is
  comparable to a row there. Only the transport differs, and ask() here
  takes a URL because the setlist's is bound to the local bench port.

Floor: DMF. No em dashes, no ellipses.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import setlist  # noqa: E402
import manifest as MF  # noqa: E402
import bench_config as BC  # noqa: E402

RUNS = BC.runs_dir()
PORT = 8099  # clear of every roster port on every node

ARMS = [
    ("e2b-ud", "gemma-4-e2b-ud", "gemma-4-E2B-it-UD-Q4_K_XL.gguf"),
    ("e4b-ud", "gemma-4-e4b-ud", "gemma-4-E4B-it-UD-Q4_K_XL.gguf"),
]

# Silicon workers are a deployment parameter: BENCH_WORKERS carries a JSON
# list (label, node or null for a local worker, ip, root, residents). The
# default is one local worker, so the instrument runs on a bare checkout
# against a local bench serve.
WORKERS = BC.workers()

REMOTE_START = r"""
. "${BENCH_PATH_ENV:-$HOME/.config/fleet/paths.env}" 2>/dev/null
L="${LLAMA_SERVER:-__LLAMA__}"
export LD_LIBRARY_PATH="$(dirname "$L")"
nohup "$L" -m __MODEL__ --host __IP__ --port __PORT__ \
  -ngl 99 -c 8192 --jinja --reasoning-format deepseek --metrics --threads 8 \
  > /tmp/xsil-serve.log 2>&1 &
echo $!
"""


def sh(cmd, timeout=60):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def ssh(node, script, timeout=60):
    return sh(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
               node, script], timeout=timeout)


def ask(url, content):
    body = json.dumps({
        "messages": [{"role": "user", "content": content}],
        "max_tokens": setlist.MAX_TOKENS,
        "temperature": setlist.TEMPERATURE,
        "stream": False,
    }).encode()
    req = urllib.request.Request(url + "/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read().decode(errors="replace"))
    ch = (d.get("choices") or [{}])[0]
    msg = ch.get("message", {}) or {}
    usage = dict(d.get("usage") or {}, finish_reason=ch.get("finish_reason"),
                 reasoning_chars=len(msg.get("reasoning_content") or ""))
    return msg.get("content") or "", time.time() - t0, usage


def wait_up(url, gguf, tries=40):
    for _ in range(tries):
        try:
            with urllib.request.urlopen(url + "/v1/models", timeout=4) as r:
                d = json.loads(r.read())
            if d["data"][0]["id"] == gguf:
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


def start_serve(w, model_path, gguf):
    if w["node"]:
        script = (REMOTE_START.replace("__MODEL__", model_path)
                  .replace("__IP__", w["ip"]).replace("__PORT__", str(PORT))
                  .replace("__LLAMA__", str(BC.llama_server())))
        rc, out, err = ssh(w["node"], script)
        pid = out.splitlines()[-1] if out else None
        return ("remote", pid)
    env = {"CUDA_DEVICE_ORDER": "PCI_BUS_ID", "CUDA_VISIBLE_DEVICES": "1",
           "PATH": "/usr/bin:/bin"}
    llama = str(BC.llama_server())
    env["LD_LIBRARY_PATH"] = str(Path(llama).parent)
    proc = subprocess.Popen(
        [llama, "-m", model_path, "--host", w["ip"], "--port", str(PORT),
         "-ngl", "99", "-c", "8192", "--jinja", "--reasoning-format",
         "deepseek", "--metrics", "--threads", "8"],
        stdout=open("/tmp/xsil-local.log", "w"), stderr=subprocess.STDOUT,
        env=env)
    return ("local", proc)


def stop_serve(w, handle):
    kind, h = handle
    if kind == "remote":
        if h:
            ssh(w["node"], f"kill {h} 2>/dev/null; sleep 1; kill -9 {h} 2>/dev/null; true")
    else:
        h.terminate()
        try:
            h.wait(timeout=10)
        except Exception:
            h.kill()


def run_worker(w, records, sink: Path, lock):
    url = f"http://{w['ip']}:{PORT}"
    results = []
    for arm, d, gguf in ARMS:
        model_path = f"{w['root']}/{d}/{gguf}"
        phase = f"{arm}@{w['label']}"
        handle = start_serve(w, model_path, gguf)
        if not wait_up(url, gguf):
            stop_serve(w, handle)
            results.append({"arm": phase, "status": "SERVE_FAILED"})
            print(f"[{w['label']}] {arm}: SERVE FAILED", flush=True)
            continue
        print(f"[{w['label']}] {arm}: serving, {len(records)} records x "
              f"{setlist.PASSES} passes", flush=True)
        ok = err = 0
        consec = 0
        for p in range(setlist.PASSES):
            for rec in records:
                prompt = setlist.TASKS["operations"]["prompt"] % rec["text"][:setlist.TASKS["operations"].get("head", setlist.HEAD_CHARS)]
                row = {"phase": phase, "relpath": rec["id"], "pass": p,
                       "task": "operations"}
                try:
                    text, secs, usage = ask(url, prompt)
                    parsed = setlist.parse_reply(text)
                    row.update(ok=True, secs=round(secs, 3),
                               parsed=parsed is not None,
                               fields=setlist.norm_fields(parsed) if parsed else None,
                               usage=usage, raw=text[:400])
                    ok += 1
                    consec = 0
                except Exception as e:
                    row.update(ok=False, error=f"{type(e).__name__}: {e}")
                    err += 1
                    consec += 1
                with lock:
                    with sink.open("a") as f:
                        f.write(json.dumps(row) + "\n")
                if consec >= 5:
                    break
            if consec >= 5:
                break
        status = "COMPLETE" if consec < 5 else "ABORTED_ERRORS"
        results.append({"arm": phase, "status": status, "ok": ok, "errors": err})
        print(f"[{w['label']}] {arm}: {status} ok={ok} err={err}", flush=True)
        stop_serve(w, handle)
        time.sleep(2)
    return results


def main() -> int:
    import threading
    records, digest = setlist.load_sample("operations")
    tag = setlist.stamp()
    RUNS.mkdir(exist_ok=True)
    sink = RUNS / f"cross_silicon_{tag}.jsonl"
    start_iso = subprocess.run(["date", "-Is"], capture_output=True,
                               text=True).stdout.strip()
    print(f"gate 1: {len(WORKERS)} silicon workers, {len(ARMS)} arms each, "
          f"sample digest {digest[:16]}")
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=len(WORKERS)) as ex:
        futs = {ex.submit(run_worker, w, records, sink, lock): w for w in WORKERS}
        all_results = []
        for f in futs:
            all_results.extend(f.result())

    per_phase = MF.summarise_jsonl(sink)
    summary = {"tag": tag, "gate": "e2b-swap-gate1-cross-silicon",
               "sample_digest": digest, "records": len(records),
               "passes": setlist.PASSES, "temperature": setlist.TEMPERATURE,
               "phases": per_phase, "statuses": all_results}
    out = RUNS / f"cross_silicon_{tag}_summary.json"
    out.write_text(json.dumps(summary, indent=1))
    print(f"\nwrote {out}")

    MF.emit({
        "run": "e2b-swap-gate1-cross-silicon",
        "started": start_iso,
        "instrument": MF.instrument(__file__),
        "vessels": {a: MF.vessel(f"{BC.models_dir()}/{d}", g)
                    for a, d, g in ARMS},
        "distribution_note": "remote copies sha-verified byte-identical to the "
                             "fingerprinted local copies at distribution",
        "serving": {"port": PORT, "eyeless": True,
                    "co_tenants": {w["label"]: w["residents"] for w in WORKERS},
                    "note": "resident seats deliberately left up: the "
                            "deployment condition, declared not ignored"},
        "hardware": MF.hardware(),
        "raw": str(sink),
        "arms": [{"arm": r["arm"], "result": {**r, **per_phase.get(r["arm"], {})}}
                 for r in all_results],
    })
    print("manifest emitted to the telemetry runs lane")

    for ph, s in sorted(per_phase.items()):
        print(f"{ph:28s} parse={s['parse_rate']} self-J={s['self_consistent']} "
              f"median={s['median_s']}s p95={s['p95_s']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
