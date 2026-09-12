#!/usr/bin/env python3
"""Storage collector: one node's storage, tallied and reported.

Read-only, stdlib-only, deterministic. It steps through a node's storage,
lights up what is actually there, and tallies it without judgement or mercy.

Layer 1 of three (collector, ledger, reconciler). This is the collector: it runs
ON a node and emits one JSON inventory of that node's storage to stdout. It reads
metadata only, never file contents, unless you explicitly ask for hashes.

Design rules, inherited from a family drift gate and from a 2026-07-26 map
sweep that found every stale path in a front door:

1. Derived from disk, never from a map. A declared path that does not exist is a
   finding, not a silent absence.
2. Read-only. Nothing here writes, moves, or deletes. Ever.
3. Deterministic and stdlib-only, so it runs free on any node with no venv, no
   model, and no network.
4. Loud when blind. Anything unreadable or unwalkable lands in `blind`, and the
   reconciler must treat a blind node as unknown, never as empty. A node that is
   down has not lost its files.

Usage:
    python3 collector.py            inventory this node, JSON to stdout
    python3 collector.py --hash-under 1048576 also sha256 files under N bytes (slow, exact)
    python3 collector.py --pretty   human-readable summary instead of JSON

Floor: DMF. No em dashes, no ellipses.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fleet_config import csv_env, DEFAULT_STORAGE_ROOTS  # noqa: E402

SCHEMA = "storage-inventory/1"

# Directory names never descended into. Build and VCS internals are noise: they
# are large, they are reproducible, and they would drown the dedup signal.
SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".mypy_cache", ".ruff_cache",
    ".pytest_cache", ".dart_tool", ".gradle", "lost+found", ".cache",
}

# Candidate storage roots, from FLEET_STORAGE_ROOTS. Only those that exist on
# this node are walked, because a fleet is deliberately not uniform: "we
# generally want a near-similar storage structure, reality might require usage
# of open space" (operator, 2026-07-26). $HOME and ~ are expanded per node.
def candidate_roots() -> list[Path]:
    roots = [Path(os.path.expandvars(os.path.expanduser(r)))
             for r in csv_env("FLEET_STORAGE_ROOTS", DEFAULT_STORAGE_ROOTS)]
    media = Path("/media") / os.environ.get("USER", "")
    if media.is_dir():
        roots.extend(p for p in sorted(media.iterdir()) if p.is_dir())
    for mnt in (Path("/mnt"), Path("/srv")):
        if mnt.is_dir():
            roots.extend(p for p in sorted(mnt.iterdir()) if p.is_dir())
    return [r for r in roots if r.is_dir()]


def mounts() -> list[dict]:
    """Filesystems and their pressure, from df. Never inferred."""
    # -P and --output are mutually exclusive on some coreutils builds (one node
    # refused the pair and the collector silently reported no mounts at all on
    # its first run, which is exactly the blind-but-quiet failure rule 4
    # forbids). Ask without -P, and surface the failure instead of swallowing it.
    out: list[dict] = []
    try:
        proc = subprocess.run(
            ["df", "-B1", "--output=source,fstype,size,used,avail,pcent,target"],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            return [{"error": f"df failed: {proc.stderr.strip()[:200]}"}]
        raw = proc.stdout.splitlines()[1:]
    except Exception as e:
        return [{"error": f"df unavailable: {e}"}]
    for line in raw:
        f = line.split(None, 6)
        if len(f) != 7 or f[1] in {"tmpfs", "devtmpfs", "squashfs", "overlay", "efivarfs"}:
            continue
        out.append({
            "source": f[0], "fstype": f[1], "bytes": int(f[2]), "used": int(f[3]),
            "avail": int(f[4]), "pct_used": f[5], "mount": f[6],
        })
    return out


def git_repo(path: Path) -> dict | None:
    """Identity of a repo: where it points, where its head is, how dirty."""
    def g(*args: str) -> str:
        try:
            r = subprocess.run(["git", "-C", str(path), *args],
                               capture_output=True, text=True, timeout=20)
            return r.stdout.strip() if r.returncode == 0 else ""
        except Exception:
            return ""
    head = g("rev-parse", "--short", "HEAD")
    if not head:
        return None
    remotes = {}
    for line in g("remote", "-v").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] not in remotes:
            remotes[parts[0]] = parts[1]
    porcelain = g("status", "--porcelain")
    return {
        "head": head,
        "branch": g("rev-parse", "--abbrev-ref", "HEAD"),
        "remotes": remotes,
        "dirty": len([x for x in porcelain.splitlines() if x.strip()]),
        "last_commit": g("log", "-1", "--format=%cI"),
    }


def walk_root(root: Path, hash_under: int, blind: list[str]) -> dict:
    """One storage root, tallied. Metadata only unless hash_under is set."""
    files = 0
    total = 0
    newest = ""
    # Cross-node dedup key: (basename, size). Cheap, comparable between machines,
    # and good enough to surface CANDIDATE duplicates. Confirming a candidate is
    # the reconciler's job with --hash-under, because equal name and size is not
    # proof of equal bytes. Never report a candidate as a confirmed duplicate.
    fingerprints: dict[str, int] = {}
    hashes: dict[str, str] = {}
    repos: dict[str, dict] = {}
    rooms: dict[str, dict] = {}

    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: blind.append(str(e))):
        d = Path(dirpath)
        if ".git" in dirnames:
            info = git_repo(d)
            if info:
                repos[str(d)] = info
        dirnames[:] = [x for x in sorted(dirnames) if x not in SKIP_DIRS]

        # Room = first level under the root, the unit the ledger declares against.
        try:
            rel = d.relative_to(root)
        except ValueError:
            continue
        room = rel.parts[0] if rel.parts else "(root)"
        r = rooms.setdefault(room, {"files": 0, "bytes": 0, "newest": ""})

        for name in filenames:
            p = d / name
            try:
                st = p.lstat()
            except OSError as e:
                blind.append(f"{p}: {e.strerror}")
                continue
            if not (st.st_mode & 0o170000) == 0o100000:  # regular files only
                continue
            files += 1
            total += st.st_size
            r["files"] += 1
            r["bytes"] += st.st_size
            mt = st.st_mtime
            iso = __import__("datetime").datetime.fromtimestamp(mt).isoformat(timespec="seconds")
            if iso > newest:
                newest = iso
            if iso > r["newest"]:
                r["newest"] = iso
            key = f"{name}\x00{st.st_size}"
            fingerprints[key] = fingerprints.get(key, 0) + 1
            if hash_under and st.st_size <= hash_under:
                try:
                    h = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
                    hashes[str(p)] = h
                except OSError as e:
                    blind.append(f"{p}: {e.strerror}")

    return {
        "path": str(root), "files": files, "bytes": total, "newest": newest,
        "rooms": rooms, "repos": repos,
        "fingerprints": fingerprints, "hashes": hashes,
    }


def collect(hash_under: int = 0) -> dict:
    blind: list[str] = []
    roots = candidate_roots()
    inv = {
        "schema": SCHEMA,
        "node": socket.gethostname(),
        "user": os.environ.get("USER", ""),
        "home": str(Path.home()),
        # No wall-clock narration anywhere: the stamp is recorded, never inferred.
        "collected_at": subprocess.run(["date", "-Is"], capture_output=True,
                                       text=True).stdout.strip(),
        "mounts": mounts(),
        "roots": [walk_root(r, hash_under, blind) for r in roots],
        "blind": blind,
    }
    # A mount probe that failed is blindness, not an absence of filesystems.
    blind.extend(m["error"] for m in inv["mounts"] if "error" in m)
    inv["totals"] = {
        "files": sum(r["files"] for r in inv["roots"]),
        "bytes": sum(r["bytes"] for r in inv["roots"]),
        "repos": sum(len(r["repos"]) for r in inv["roots"]),
        "blind_entries": len(blind),
    }
    return inv


def human(n: int) -> str:
    for unit in ("B", "K", "M", "G", "T"):
        if abs(n) < 1024 or unit == "T":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024.0
    return str(n)


def pretty(inv: dict) -> None:
    print(f"# Storage inventory: {inv['node']} ({inv['collected_at']})")
    print()
    t = inv["totals"]
    print(f"{t['files']:,} files, {human(t['bytes'])}, {t['repos']} git repos.")
    if t["blind_entries"]:
        print(f"**BLIND on {t['blind_entries']} paths.** Unknown, not empty.")
    print()
    print("| mount | size | used | avail | pct |")
    print("|---|---:|---:|---:|---:|")
    for m in inv["mounts"]:
        print(f"| {m['mount']} | {human(m['bytes'])} | {human(m['used'])} "
              f"| {human(m['avail'])} | {m['pct_used']} |")
    for root in inv["roots"]:
        if not root["files"]:
            continue
        print()
        print(f"## {root['path']}  ({root['files']:,} files, {human(root['bytes'])})")
        print()
        print("| room | files | bytes | newest |")
        print("|---|---:|---:|---|")
        for name, r in sorted(root["rooms"].items(), key=lambda kv: -kv[1]["bytes"]):
            if r["files"]:
                print(f"| {name} | {r['files']:,} | {human(r['bytes'])} | {r['newest'][:10]} |")


def main() -> int:
    ap = argparse.ArgumentParser(description="Storage collector: one node's storage, tallied.")
    ap.add_argument("--hash-under", type=int, default=0, metavar="BYTES",
                    help="also sha256 files at or under this size (slow, exact)")
    ap.add_argument("--pretty", action="store_true", help="human summary, not JSON")
    args = ap.parse_args()
    inv = collect(args.hash_under)
    if args.pretty:
        pretty(inv)
    else:
        json.dump(inv, sys.stdout, separators=(",", ":"))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
