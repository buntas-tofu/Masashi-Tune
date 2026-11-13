#!/usr/bin/env python3
"""Project the masashi-tune bench tapes down to a publishable spine.

Read-only over the tapes, writes only its own output. Built 2026-11-13 for c-0054
on the operator's ruling.

Where the tapes actually are, measured: `besaid/memory/operational/bench/runs`,
54 jsonl files, 29M, 48,035 rows. They used to be cited at
`local/spira/bench/runs`, which no longer exists, and `memory/operational/bench/`
is gitignored by the besaid repo (line 86), so the tapes are untracked working
material rather than repository content. That is why the card asked for a spine
rather than a push of the directory.

The tapes are not one shape. Twenty distinct key sets appear across 48,035 rows,
and 25,846 rows carry `relpath`, which carries real document names including
personal surnames. So this cannot be a column drop on a single schema: it is a
whitelist applied per row, and anything not on the whitelist is omitted whether
or not this pass understands it.

Included: measurement, identity of the seat, phase and pass, synthetic anchors,
and hashes.
Excluded on purpose: `relpath`, `raw`, `parsed`, `fields`, `candidate`, `read`,
and `error` (an error string is free text and routinely carries a filesystem
path). Dropping `error` costs a failure class, so the presence of a failure is
kept as the boolean in `ok`/`parse_ok`; the message is not.

Usage:
    python3 bench/spine/build_spine.py --out bench/spine/bench_spine_2026-11-13.jsonl
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from collections import Counter
from pathlib import Path

TAPES = Path(os.environ.get("MASASHI_TAPES")
             or Path.home() / "besaid/memory/operational/bench/runs")

WHITELIST = (
    "seat", "phase", "pass", "kind", "task", "anchor", "anchor_set", "anchor_sha256",
    "seconds", "secs", "wall", "ttft", "ttft_s", "t", "i",
    "prompt_chars", "out_chars", "prompt_tokens", "completion_tokens",
    "target_tokens", "tg_tok_s", "tokens", "finish",
    "parse_ok", "ok", "n_fields", "n", "qdepth", "lateness_s",
    "node", "vendor", "devices", "power_w_total", "ts",
)
# kept as a named list so the exclusion is auditable rather than implied
DENYLIST = ("relpath", "raw", "parsed", "fields", "candidate", "read", "error")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="bench/spine/bench_spine.jsonl")
    ap.add_argument("--source", default=str(TAPES))
    args = ap.parse_args()

    src = Path(args.source)
    files = sorted(glob.glob(str(src / "*.jsonl")))
    if not files:
        raise SystemExit(f"no tapes under {src}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = kept = 0
    dropped = Counter()
    shapes = Counter()
    with out_path.open("w", encoding="utf-8") as fh:
        for path in files:
            for line in open(path, encoding="utf-8", errors="replace"):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rows += 1
                shapes[tuple(sorted(row))] += 1
                spine = {k: row[k] for k in WHITELIST if k in row}
                for k in DENYLIST:
                    if k in row:
                        dropped[k] += 1
                if not spine:
                    continue
                spine["_source"] = os.path.basename(path)
                fh.write(json.dumps(spine, sort_keys=True) + "\n")
                kept += 1

    # prove the exclusion rather than claim it. Check KEYS on a re-read of the
    # written file: a substring search over the text also matches a VALUE that
    # happens to be the word "read" or "error", which is a false positive and
    # says nothing about whether a dangerous column survived.
    leaked_keys = set()
    for line in out_path.open(encoding="utf-8"):
        row = json.loads(line)
        leaked_keys |= set(row) & set(DENYLIST)
    if leaked_keys:
        out_path.unlink()
        raise SystemExit(f"denylisted keys leaked into the spine: {sorted(leaked_keys)}")

    print(f"source      {src}")
    print(f"files       {len(files)}")
    print(f"rows read   {rows}")
    print(f"rows kept   {kept}")
    print(f"row shapes  {len(shapes)}")
    print(f"size        {out_path.stat().st_size / 1024:.0f} KiB -> {out_path}")
    print("dropped on purpose (rows carrying the key):")
    for k, n in dropped.most_common():
        print(f"  {k:<10} {n:6d}")
    print(f"verified    no denylisted key appears in the output")


if __name__ == "__main__":
    main()
