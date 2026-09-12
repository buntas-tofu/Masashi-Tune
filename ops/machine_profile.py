#!/usr/bin/env python3
"""machine_profile.py: the fleet's build specs, captured rather than remembered.

Commissioned by the operator 2026-08-04, the session after the runs lane landed.
His directive, near verbatim: if the machine profiles do not have current build
specs for use in efficient model and process distribution, then that is
essential.

WHY THIS EXISTS. seats.toml binds every seat to a node by name, and nothing on
this fleet defines the node. Models have a registry, seats have a registry,
personas have a registry; machines have a table in the contract file and whatever the
last session remembered. The runs lane (2026-08-04) fingerprints every vessel a
measurement touched; the machine half of that join stops at what nvidia-smi
said in the moment. Casting decisions, setlist scheduling, and the bench
contract all reason over VRAM, PCIe, serving stacks, and store locations, and
until this tool those facts lived in prose that goes stale the day a driver
updates.

TWO LAYERS, one JSON per node under tools/machines/:

  build     what a probe can read and a distribution decision needs: silicon,
            VRAM, driver, CUDA, PCIe link, RAM, OS, arch, serving stacks,
            model stores, wired NIC speeds, tailscale address.
  snapshot  point-in-time context, excluded from drift: free disk, entry
            counts. Kept because a capture without context is a bare number.

The CURATED half lives beside the roster as nodes.toml: role, PSU wattage,
power-reporting caveats, measured physics with their receipt documents. A probe
cannot know a power supply's rating and a TOML cannot know today's driver.
Neither file repeats the other; that split is the whole design.

MODES, same contract as unit_drift.py:

  --capture [node ...]   refresh tools/machines/<node>.json (default all)
  (default)  [node ...]  re-probe and diff BUILD facts against the record

Exit code is always 0: it reports, the operator judges. A node that cannot be
reached is reported UNREACHABLE rather than skipped, and a diff against a
missing record says so plainly. Blind is never clean.

Floor: DMF. No em dashes, no ellipses.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fleet_config as cfg  # noqa: E402

# Nodes reached by ssh alias, each alias carrying its own per-node username.
# Local node detected by hostname, so the chair can move again without editing
# this file. Names come from FLEET_NODES.
NODES = cfg.nodes()

MACHINES = cfg.machines_dir()

# Model store conventions. The probe records the ones that exist on each node;
# absence is normal, not an error. Candidate paths come from FLEET_MODEL_STORES
# and are expanded on the node, so $HOME works per node.
STORE_CANDIDATES = cfg.csv_env("FLEET_MODEL_STORES", cfg.DEFAULT_MODEL_STORES)

# llama-server build globs to probe, from FLEET_LLAMA_GLOBS. Each is expanded
# on the node.
LLAMA_GLOBS = cfg.csv_env("FLEET_LLAMA_GLOBS", cfg.DEFAULT_LLAMA_GLOBS)

# Mounts the disk section reports, from FLEET_DISK_MOUNTS, expanded on the node.
DISK_MOUNTS = cfg.env("FLEET_DISK_MOUNTS", cfg.DEFAULT_DISK_MOUNTS)

# Per-node env file the probe sources last, from FLEET_PATH_ENV.
PATH_ENV = cfg.env("FLEET_PATH_ENV", cfg.DEFAULT_PATH_ENV)

# One round trip per node. Tab-separated tagged lines; every section soft-fails
# so a box missing a vendor tool still reports everything else it has.
PROBE = r"""
# /snap/bin explicitly. systemd user units and non-login ssh do not inherit the
# login PATH, so on a node where a tool is snap-installed the probe simply could
# not see it: one node's tailscale binary, found 2026-08-05 after the machine
# gate spent days reporting a tailscale address as a BUILD CHANGE while the
# tailnet was demonstrably up and carrying the whole board. Set here rather than
# per-tool so the next snap-installed probe target does not repeat it.
PATH="$PATH:/snap/bin:/usr/sbin:/usr/local/bin"
echo "@node	$(hostname)"
echo "@kernel	$(uname -r)"
echo "@arch	$(uname -m)"
. /etc/os-release 2>/dev/null && echo "@os	$PRETTY_NAME"
echo "@cpu	$(lscpu 2>/dev/null | sed -n 's/^Model name:[[:space:]]*//p' | head -1)"
echo "@cores	$(nproc 2>/dev/null)"
echo "@ram_b	$(free -b 2>/dev/null | awk '/^Mem:/{print $2}')"
echo "@python	$(python3 --version 2>/dev/null)"
if command -v tailscale >/dev/null 2>&1; then
  echo "@tailscale	$(tailscale ip -4 2>/dev/null | head -1)"
else
  echo "@tailscale	?unprobeable"
fi
nvidia-smi --query-gpu=index,name,uuid,memory.total,driver_version,pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current,pcie.link.width.max,power.limit --format=csv,noheader 2>/dev/null | while IFS= read -r l; do echo "@gpu_nv	$l"; done
nvidia-smi 2>/dev/null | sed -n 's/.*CUDA Version: \([0-9.]*\).*/@cuda	\1/p' | head -1
if command -v rocminfo >/dev/null 2>&1; then
  rocminfo 2>/dev/null | sed -n 's/^[[:space:]]*Name:[[:space:]]*\(gfx[0-9a-z]*\)$/@gpu_amd	\1/p' | head -1
fi
lspci 2>/dev/null | grep -Ei 'vga|display|3d' | while IFS= read -r l; do echo "@pci_gpu	$l"; done
for n in /sys/class/net/*; do
  i=$(basename "$n")
  case "$i" in lo|docker*|veth*|br-*|tailscale*|virbr*) continue;; esac
  s=$(cat "$n/speed" 2>/dev/null)
  [ -n "$s" ] && [ "$s" -gt 0 ] 2>/dev/null && echo "@nic	$i	$s"
done
df -B1 --output=target,size,avail __MOUNTS__ 2>/dev/null | tail -n +2 | sort -u | while IFS= read -r l; do echo "@disk	$l"; done
for d in __STORES__; do
  e=$(eval echo "$d")
  [ -d "$e" ] && echo "@store	$e	$(ls "$e" 2>/dev/null | wc -l)"
done
# Three shapes, because a heterogeneous fleet genuinely has three. One node
# builds per flavour under an app tree (build/cuda/bin); appliance nodes keep
# their engines on a mounted tree by decision and build flat (build/bin, one
# level shallower), which a single app-tree glob missed on both counts and
# reported as an empty llama_cpp list rather than as an unlooked-at path.
# Whatever the per-node env file declares is included last and wins on merge,
# since that file is what the units actually execute: anchor to executed
# config, never to a guess about layout.
. "__PATH_ENV__" 2>/dev/null || true
_seen=""
for b in __LLAMA_GLOBS__ "${LLAMA_SERVER:-}"; do
  [ -n "$b" ] && [ -x "$b" ] || continue
  # paths.env usually names a binary a glob already found, so dedupe on the
  # resolved path. Counting one engine twice would read as a second build.
  r=$(readlink -f "$b")
  case " $_seen " in *" $r "*) continue;; esac
  _seen="$_seen $r"
  d=$(dirname "$(dirname "$b")")
  f=$(basename "$d")
  # A flat build (build/bin, the twins' layout) carries no flavour in its path.
  # Say "flat" rather than inventing one from the parent directory name.
  [ "$f" = "build" ] && f=flat
  v=$(LD_LIBRARY_PATH="$d/bin:$d/common" "$b" --version 2>&1 | grep -im1 version)
  echo "@llama	$f	$v"
done
command -v docker >/dev/null 2>&1 && echo "@docker	$(docker --version 2>/dev/null)"
docker images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null | grep -i vllm | head -5 | while IFS= read -r l; do echo "@vllm_image	$l"; done
""".replace("__STORES__", " ".join(f'"{s}"' for s in STORE_CANDIDATES)) \
   .replace("__LLAMA_GLOBS__", " ".join(LLAMA_GLOBS)) \
   .replace("__MOUNTS__", DISK_MOUNTS) \
   .replace("__PATH_ENV__", PATH_ENV)


def _sh(cmd, timeout=90):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.stdout
    except Exception:
        return ""


def local_hostname() -> str:
    return _sh(["hostname"]).strip()


def probe(node: str, local: str) -> dict | None:
    """One node's machine state, or None if unreachable."""
    if node == local:
        out = _sh(["bash", "-c", PROBE])
    else:
        out = _sh(["ssh", *cfg.ssh_opts(), node, PROBE], timeout=120)
    if not out.strip():
        return None
    return parse(node, out)


def parse(node: str, raw: str) -> dict:
    b: dict = {"gpus": [], "nics": [], "stacks": {"llama_cpp": [], "vllm_images": []},
               "model_stores": []}
    snap: dict = {"disks": [], "store_entries": {}}
    amd_gfx, pci_gpus = None, []
    for line in raw.splitlines():
        if not line.startswith("@"):
            continue
        parts = line.split("\t")
        tag = parts[0][1:]
        val = parts[1] if len(parts) > 1 else ""
        if tag in ("node", "kernel", "arch", "os", "cpu", "python", "tailscale", "cuda"):
            b[tag] = val
        elif tag == "cores":
            b["cores"] = int(val) if val.isdigit() else val
        elif tag == "ram_b":
            b["ram_gb"] = round(int(val) / 1e9, 1) if val.isdigit() else None
        elif tag == "gpu_nv":
            f = [x.strip() for x in val.split(",")]
            if len(f) >= 10:
                b["gpus"].append({
                    "vendor": "nvidia", "index": f[0], "name": f[1],
                    "uuid": f[2], "vram": f[3], "driver": f[4],
                    "pcie": {"gen_now": f[5], "gen_max": f[6],
                             "width_now": f[7], "width_max": f[8]},
                    "power_limit": f[9]})
        elif tag == "gpu_amd":
            amd_gfx = val
        elif tag == "pci_gpu":
            pci_gpus.append(val)
        elif tag == "nic" and len(parts) >= 3:
            b["nics"].append({"iface": parts[1], "speed_mbit": int(parts[2])})
        elif tag == "disk":
            f = val.split()
            if len(f) >= 3:
                snap["disks"].append({"mount": f[0],
                                      "size_gb": round(int(f[1]) / 1e9, 1),
                                      "avail_gb": round(int(f[2]) / 1e9, 1)})
        elif tag == "store" and len(parts) >= 3:
            b["model_stores"].append(parts[1])
            snap["store_entries"][parts[1]] = int(parts[2]) if parts[2].isdigit() else None
        elif tag == "llama" and len(parts) >= 3:
            b["stacks"]["llama_cpp"].append({"flavor": parts[1], "version": parts[2]})
        elif tag == "docker":
            b["stacks"]["docker"] = val
        elif tag == "vllm_image":
            b["stacks"]["vllm_images"].append(val)
    if amd_gfx:
        b["gpus"].append({"vendor": "amd", "gfx": amd_gfx,
                          "pci": pci_gpus[0] if pci_gpus else None})
    elif not b["gpus"] and pci_gpus:
        b["gpus"].append({"vendor": "unknown", "pci": pci_gpus[0]})
    # PCIe link state is load-dependent (idle downshift is ordinary), so the
    # CURRENT gen and width are context, not build identity. Max is identity.
    return {"node": node, "build": b, "snapshot": snap}


def _flatten(d, prefix=""):
    out = {}
    if isinstance(d, dict):
        for k, v in sorted(d.items()):
            out.update(_flatten(v, f"{prefix}{k}."))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            out.update(_flatten(v, f"{prefix}{i}."))
    else:
        out[prefix.rstrip(".")] = d
    return out


# Volatile leaves excluded from the drift comparison. pcie gen_now and
# width_now downshift at idle (observed on a node 2026-08-04, gen1 at idle on a
# gen4 x8 link), so only the max is compared.
VOLATILE = ("pcie.gen_now", "pcie.width_now")

# A probe that cannot run is not a hardware change, and conflating the two is how
# an instrument gap gets read as a finding for days. The probe emits this sentinel
# when the tool is absent, so the diff can say the instrument went dark rather
# than inventing a value change. Same doctrine as the zoo gate's coverage line:
# blind is a state to report, never a state to pass silently.
BLIND = "?unprobeable"


def drift(node: str, recorded: dict, live: dict) -> list[str]:
    a = _flatten(recorded.get("build", {}))
    c = _flatten(live.get("build", {}))
    lines = []
    for key in sorted(set(a) | set(c)):
        if any(key.endswith(v) for v in VOLATILE):
            continue
        if key not in c:
            lines.append(f"  MISSING  {key} (was: {a[key]})")
        elif key not in a:
            lines.append(f"  NEW      {key} = {c[key]}")
        elif a[key] != c[key]:
            if c[key] == BLIND:
                lines.append(f"  BLIND    {key}: probe could not run here. Last "
                             f"known {a[key]}. Instrument gap, not a hardware "
                             f"change.")
            elif a[key] == BLIND:
                lines.append(f"  RESOLVED {key}: now reads {c[key]}, was "
                             f"unprobeable when captured. Re-capture to bank it.")
            else:
                lines.append(f"  CHANGED  {key}: {a[key]} -> {c[key]}")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--capture", action="store_true",
                    help="refresh recorded profiles instead of diffing")
    ap.add_argument("nodes", nargs="*", default=None,
                    help="subset of nodes (default: whole fleet)")
    args = ap.parse_args()
    targets = args.nodes or NODES
    local = local_hostname()
    stamp = _sh(["date", "-Is"]).strip()

    unreachable, findings, captured = [], [], []
    for node in targets:
        live = probe(node, local)
        if live is None:
            unreachable.append(node)
            continue
        path = MACHINES / f"{node}.json"
        if args.capture:
            live["captured_at"] = stamp
            MACHINES.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(live, indent=1, sort_keys=True) + "\n")
            captured.append(node)
        else:
            if not path.is_file():
                findings.append(f"{node}: NO RECORDED PROFILE (run --capture)")
                continue
            recorded = json.loads(path.read_text())
            lines = drift(node, recorded, live)
            if lines:
                blind = sum(1 for ln in lines if ln.strip().startswith("BLIND"))
                parts = ([f"{len(lines) - blind} build drift"]
                         if len(lines) - blind else [])
                if blind:
                    parts.append(f"{blind} probe blind")
                findings.append(f"{node}: {', '.join(parts)}")
                findings.extend(lines)

    print(f"## Machine profiles ({stamp})")
    if args.capture:
        print(f"captured: {', '.join(captured) if captured else 'none'}")
    elif findings:
        print("\n".join(findings))
    else:
        checked = [n for n in targets if n not in unreachable]
        print(f"clean: {len(checked)} of {len(targets)} nodes match their "
              f"recorded build ({', '.join(checked)})")
    if unreachable:
        print(f"UNREACHABLE, state unknown: {', '.join(unreachable)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
