#!/usr/bin/env python3
"""Run manifests: the join that currently only exists in prose.

Commissioned by the operator 2026-08-04, ahead of recursive self-improvement
runs. His framing: as the assessments get more advanced we have to properly
contextualise and store the data, not just produce it.

THE GAP THIS CLOSES. We generate measurements well. What we do not store is the
JOIN between a measurement and the exact configuration that produced it. Today
that join lives in commit messages and markdown prose, which is excellent for a
person reading it next week and useless to a program asking "what have we
changed, and what happened when we did".

Concretely, after last night's setlist nothing on disk could answer:
  - which exact bytes were loaded, as opposed to which directory name
  - what serving flags the phase actually ran with
  - which physical GPU it landed on
  - which telemetry samples cover that window
  - what the anchor set was, by digest rather than by filename
Every one of those was known at the moment of the run and recoverable only from
my own narration afterwards. A manifest is that knowledge written down while it
is still true.

DELIBERATELY SMALL. The telemetry card says the compounding edge is hours on
telemetry and lineup re-assessment, and never over-engineered. So this is one
JSON object per run, appended to a date-addressed file in the room that already
holds the instrument tape. No database, no service, no schema registry. It rides
the existing convention: telemetry/<lane>/YYYY-MM-DD, same as inference/ and
odometer/.

WHAT MAKES A GOOD MANIFEST. Identity that survives renaming. A directory name is
not identity: the two E4B builds we compared live in directories that differ only
by suffix and their weights differ by 2,144 bytes. A vessel is therefore
fingerprinted by size plus content sampled at five offsets, and carries whatever
provenance SOURCE.txt recorded at download. The five offsets are not decoration;
see the note on SAMPLE_POINTS for the pair that defeated the first design.

Floor: DMF. No em dashes, no ellipses.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import bench_config as BC

RUNS_LANE = BC.runs_lane()
SCHEMA = "run-manifest/1"

# Sampled at five offsets rather than two. Head-plus-tail was the first design
# and it FAILED on its first real use: the two 26B builds differ by 79MB in the
# middle of the file and produced identical head and tail digests, so they were
# separated only by happening to differ in size. Two builds of equal size with a
# mid-file change would have collided silently, which is the exact failure this
# whole fingerprint exists to prevent. Five samples of 1MB costs nothing.
SAMPLE_BYTES = 1024 * 1024
SAMPLE_POINTS = (0.0, 0.25, 0.5, 0.75, 1.0)


def _sh(cmd, cwd=None, timeout=30):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, cwd=cwd)
        return p.stdout.strip() if p.returncode == 0 else ""
    except Exception:
        return ""


def now_iso():
    """Recorded, never inferred. The clock is asked, not narrated."""
    return _sh(["date", "-Is"])


def fingerprint(path) -> dict:
    """Identity of a weights file that survives being moved or renamed.

    Size plus five 1MB samples rather than a whole-file hash: a 15.8G digest
    costs real time on every run, and this separates every pair on disk here.
    The E4B pair differs only in the first 8MB, the 26B pair only in the middle
    79MB, so any scheme reading just the ends is blind to one of them.
    """
    p = Path(path)
    if not p.is_file():
        return {"path": str(p), "present": False}
    size = p.stat().st_size
    digests = []
    with p.open("rb") as f:
        for frac in SAMPLE_POINTS:
            off = min(int(size * frac), max(0, size - SAMPLE_BYTES))
            f.seek(off)
            digests.append(hashlib.sha256(f.read(SAMPLE_BYTES)).hexdigest()[:12])
    composite = hashlib.sha256(
        (str(size) + "".join(digests)).encode()).hexdigest()[:24]
    return {"path": str(p), "present": True, "bytes": size,
            "sample_points": list(SAMPLE_POINTS),
            "sha256_samples": digests,
            "fingerprint": composite}


def vessel(model_dir, gguf) -> dict:
    """A vessel: its bytes, and whatever upstream provenance we recorded."""
    d = Path(model_dir)
    out = {"dir": d.name, "weights": fingerprint(d / gguf)}
    src = d / "SOURCE.txt"
    if src.is_file():
        prov = {}
        for line in src.read_text().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                prov[k.strip()] = v.strip()
        out["upstream"] = prov
    return out


def hardware() -> list:
    """What silicon was present. Asked of the driver, never assumed."""
    raw = _sh(["nvidia-smi",
               "--query-gpu=index,name,memory.total,driver_version,pcie.link.gen.current",
               "--format=csv,noheader"])
    out = []
    for line in raw.splitlines():
        f = [x.strip() for x in line.split(",")]
        if len(f) >= 4:
            out.append({"index": f[0], "name": f[1], "vram": f[2],
                        "driver": f[3],
                        "pcie_gen": f[4] if len(f) > 4 else None})
    return out


def instrument(script_path) -> dict:
    """Which version of which tool. A result without its instrument is a rumour."""
    p = Path(script_path).resolve()
    repo = p
    while repo != repo.parent and not (repo / ".git").is_dir():
        repo = repo.parent
    sha = _sh(["git", "rev-parse", "--short", "HEAD"], cwd=str(repo))
    dirty = _sh(["git", "status", "--porcelain", str(p)], cwd=str(repo))
    return {"name": p.name, "git": sha or None,
            "uncommitted": bool(dirty),
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest()[:16]
            if p.is_file() else None}


def emit(manifest: dict, lane: Path = RUNS_LANE) -> Path:
    """Append one manifest to the day's file. Date-addressed, like every lane.

    A manifest whose raw rows are missing, or whose arms carry no result, is
    marked INCOMPLETE rather than written as though it were whole. The first
    backfill emitted four arms of nulls because the raw path was wrong by one
    suffix, and it looked exactly like a finished record. Silence that resembles
    data is the failure mode this fleet has spent the week closing.
    """
    manifest = {"schema": SCHEMA, "recorded_at": now_iso(), **manifest}
    problems = []
    raw = manifest.get("raw")
    if raw and not Path(raw).is_file():
        problems.append(f"raw rows absent at {raw}")
    empty = [a.get("arm") for a in manifest.get("arms", []) if not a.get("result")]
    if empty:
        problems.append("arms with no result: " + ", ".join(map(str, empty)))
    if problems:
        manifest["INCOMPLETE"] = problems
    day = (manifest.get("started") or manifest["recorded_at"])[:10]
    lane.mkdir(parents=True, exist_ok=True)
    path = lane / f"{day}.jsonl"
    with path.open("a") as f:
        f.write(json.dumps(manifest, sort_keys=True) + "\n")
    return path


def telemetry_window(start_iso, end_iso, telemetry_file) -> dict:
    """Which samples cover this run, so the physical half can be rejoined.

    A pointer plus a time range rather than a copy. The telemetry file is
    gitignored bulk by convention and duplicating it into the manifest would
    make the lane enormous for no gain.
    """
    p = Path(telemetry_file) if telemetry_file else None
    return {"file": str(p) if p else None,
            "present": bool(p and p.is_file()),
            "from": start_iso, "to": end_iso}


def summarise_jsonl(path, phase_key="phase") -> dict:
    """Headline numbers per arm, so a manifest answers without opening the raw."""
    import statistics
    rows = []
    p = Path(path)
    if not p.is_file():
        return {}
    for line in p.open():
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    by = {}
    for r in rows:
        by.setdefault(r.get(phase_key, "?"), []).append(r)
    out = {}
    for k, rs in by.items():
        ok = [r for r in rs if r.get("ok")]
        lat = sorted(r["secs"] for r in ok if r.get("secs") is not None)
        pairs = {}
        for r in ok:
            pairs.setdefault(r.get("relpath"), {})[r.get("pass")] = r.get("fields")
        both = [v for v in pairs.values() if 0 in v and 1 in v]
        same = sum(1 for v in both if v[0] == v[1] and v[0] is not None)
        out[k] = {
            "calls": len(rs), "ok": len(ok), "errors": len(rs) - len(ok),
            "parse_rate": round(sum(1 for r in ok if r.get("parsed")) / len(ok), 4)
            if ok else None,
            "self_consistent": round(same / len(both), 4) if both else None,
            "median_s": round(statistics.median(lat), 3) if lat else None,
            "p95_s": round(lat[min(len(lat) - 1, int(len(lat) * 0.95))], 3)
            if lat else None,
        }
    return out


if __name__ == "__main__":
    print(json.dumps({"lane": str(RUNS_LANE), "schema": SCHEMA,
                      "hardware": hardware(),
                      "example_instrument": instrument(__file__)}, indent=1))
