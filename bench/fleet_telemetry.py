#!/usr/bin/env python3
"""Fleet telemetry sampler: sustained draw, clocks, and thermals under real load.

Written 2026-08-02. The extraction bench measures a request. This measures the machine
underneath it over hours, because the two questions are different and only one of them
was instrumented.

WHY A SAMPLER AND NOT A DASHBOARD. Single-shot latency cannot show whether a card holds
its clocks through a long campaign, where it thermally throttles, or what a phase costs
in joules. Those only appear in a time series taken WHILE real work is running, and they
cannot be recovered afterward from a stream that never sampled. The night this was
written, a stage 4 backlog was scheduled to run about seven hours on a twin node, which is
free sustained-load data if something is watching.

WHAT IT DEFENDS AGAINST. One persistent SSH per node running a remote loop, rather than
one SSH per sample. At a 30 second interval over eight hours, per-sample connections
would be several thousand handshakes for no added information, and the handshake cost
would land inside the thing being measured.

READING THE NUMBERS, and two of these will mislead if taken at face value:

  GB10 class (unified memory)  PCIe fields are meaningless. Grace-Blackwell puts CPU and
                              GPU on one package over NVLink-C2C with coherent unified
                              memory, so there is no PCIe hop between host and device to
                              report and nvidia-smi answers gen 1 x1 as a placeholder.
                              Memory fields answer [N/A] for the same reason: the GPU's
                              memory IS system memory. Reported draw also appears to
                              cover less of the module than a discrete board's does, so
                              do not compare GB10 watts against a 5090's directly.
  discrete card (PCIe)         PCIe link gen drops to 1 at idle. That is ASPM power
                              saving, not a fault, and it trains up under load. LINK
                              WIDTH is the real constraint and it does not change:
                              the primary node runs x8/x8 out of x16 by bifurcation.

Usage:
  python3 fleet_telemetry.py <out.jsonl> [interval_s] [duration_h]
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time

import bench_config as BC

# node -> (ssh target or None for the local node, vendor). Configured via
# BENCH_NODES (names), BENCH_VENDORS (nvidia or amd, one per node), and
# BENCH_LOCAL_NODES (names reached locally rather than over ssh).
_LOCAL = {x.strip() for x in BC.env("BENCH_LOCAL_NODES", "").split(",") if x.strip()}
NODES = {n: (None if n in _LOCAL else n, v)
         for n, v in zip(BC.nodes(), BC.vendors())}

NVIDIA_Q = ("index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,"
            "power.draw,power.limit,clocks.sm,pcie.link.gen.current,"
            "pcie.link.width.current")

# amd-smi's json is large and its shape moves between releases. The three fields that
# matter here are available from the terse metric call, and a parse failure on one node
# must not take the sampler down, so the remote side emits raw and the parse is local.
# The trailing `echo` is load-bearing. `tr -d '\n'` strips the final newline too, so
# without it the collapsed JSON and the `---` delimiter arrive on ONE line and the reader
# never sees a sample boundary. Caught 2026-08-02 when four nodes reported and one node
# silently did not.
#
# Known gap, measured the same night: on an AMD bar amd-smi answers "N/A" to both
# socket_power and usage, so the bar contributes temperature and memory but NO power or
# utilisation. It is sampled anyway rather than dropped, because a node absent from the
# series reads as a node that was off.
AMD_CMD = "/opt/rocm/bin/amd-smi metric -g 0 --json 2>/dev/null | tr -d '\\n'; echo"


def remote_loop(vendor: str, interval: int) -> str:
    if vendor == "nvidia":
        inner = f"nvidia-smi --query-gpu={NVIDIA_Q} --format=csv,noheader,nounits"
    else:
        inner = AMD_CMD
    # `echo ---` delimits one sample, so a multi-GPU node's rows stay grouped.
    return f"while true; do {inner}; echo '---'; sleep {interval}; done"


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def parse_nvidia(block: str) -> list[dict]:
    out = []
    for line in block.strip().splitlines():
        f = [x.strip() for x in line.split(",")]
        if len(f) < 11:
            continue
        out.append({
            "index": f[0], "name": f[1],
            "util": _num(f[2]),
            "vram_used_mb": _num(f[3]), "vram_total_mb": _num(f[4]),
            "temp_c": _num(f[5]),
            "power_w": _num(f[6]), "power_limit_w": _num(f[7]),
            "clock_sm_mhz": _num(f[8]),
            "pcie_gen": _num(f[9]), "pcie_width": _num(f[10]),
        })
    return out


def parse_amd(block: str) -> list[dict]:
    try:
        data = json.loads(block.strip())
    except json.JSONDecodeError:
        return []
    gpus = data.get("gpu_data") if isinstance(data, dict) else data
    out = []
    for i, g in enumerate(gpus or []):
        if not isinstance(g, dict):
            continue
        def n(d, k):
            v = (d or {}).get(k)
            if isinstance(v, dict):
                v = v.get("value")
            return _num(v) if not isinstance(v, (int, float)) else v
        out.append({
            "index": str(i), "name": g.get("name") or "amd gpu",
            "util": n(g, "usage"),
            "vram_used_mb": n(g.get("mem_usage"), "used_vram"),
            "vram_total_mb": n(g.get("mem_usage"), "total_vram"),
            "temp_c": n(g.get("temperature"), "edge"),
            "power_w": n(g.get("power"), "socket_power"),
            "power_limit_w": n(g.get("power"), "power_limit"),
            "clock_sm_mhz": None, "pcie_gen": None, "pcie_width": None,
        })
    return out


def watch(node: str, target: str | None, vendor: str, interval: int,
          out_path: str, lock: threading.Lock, stop: threading.Event):
    loop = remote_loop(vendor, interval)
    cmd = ["bash", "-lc", loop] if target is None else [
        "ssh", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=30", target, loop]
    while not stop.is_set():
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, text=True)
        except OSError as e:
            print(f"  {node}: spawn failed {e}", flush=True)
            stop.wait(30)
            continue
        block = []
        try:
            for line in proc.stdout:
                if stop.is_set():
                    break
                if line.strip() == "---":
                    raw = "\n".join(block)
                    block = []
                    devs = parse_nvidia(raw) if vendor == "nvidia" else parse_amd(raw)
                    rec = {"ts": round(time.time(), 1), "node": node,
                           "vendor": vendor, "devices": devs}
                    if devs:
                        rec["power_w_total"] = round(
                            sum(d["power_w"] for d in devs
                                if d.get("power_w") is not None), 1)
                    with lock:
                        with open(out_path, "a", encoding="utf-8") as fh:
                            fh.write(json.dumps(rec) + "\n")
                else:
                    block.append(line.rstrip())
        finally:
            proc.kill()
        if not stop.is_set():
            # A dropped SSH is a fact about the link, not a reason to stop watching.
            print(f"  {node}: stream ended, reconnecting", flush=True)
            stop.wait(15)


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    out_path = sys.argv[1]
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    duration_h = float(sys.argv[3]) if len(sys.argv) > 3 else 8.0
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    lock, stop = threading.Lock(), threading.Event()
    threads = []
    for node, (target, vendor) in NODES.items():
        t = threading.Thread(target=watch, args=(node, target, vendor, interval,
                                                 out_path, lock, stop), daemon=True)
        t.start()
        threads.append(t)
    print(f"sampling {len(NODES)} nodes every {interval}s for {duration_h}h -> {out_path}",
          flush=True)

    def handle(_sig, _frm):
        stop.set()
    signal.signal(signal.SIGTERM, handle)
    signal.signal(signal.SIGINT, handle)
    stop.wait(duration_h * 3600)
    stop.set()
    print("sampling complete", flush=True)


if __name__ == "__main__":
    main()
