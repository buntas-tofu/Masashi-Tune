#!/usr/bin/env python3
"""ledger_check.py: the disposition gate over ledger.toml.

One question, asked by a timer rather than remembered: is anything still
waiting on purpose? staged-for-bench entries carry review_by; past-due means
the heat did not run and the staging is going stale, which is exactly how the
fleet grew vessels nobody could name (the 08-10 Mistral surprise). Same
contract as every gate here: it reports, exit 0 always, and acting on a line
is a Tier 1 ruling.
"""

import collections
import datetime
import pathlib
import sys

LEDGER = pathlib.Path(__file__).parent / "ledger.toml"


def main() -> int:
    try:
        import tomllib
    except ImportError:
        print("ledger_check: python 3.11+ wanted (tomllib); reporting nothing")
        return 0
    if not LEDGER.exists():
        print(f"ledger_check: no ledger at {LEDGER}")
        return 0
    data = tomllib.loads(LEDGER.read_text())
    artifacts = data.get("artifact", {})
    today = datetime.date.today()
    counts = collections.Counter()
    past_due = []
    malformed = []
    for key, entry in artifacts.items():
        tag = entry.get("tag", "MISSING-TAG")
        counts[tag] += 1
        if tag == "staged-for-bench":
            review_by = entry.get("review_by")
            if review_by is None:
                malformed.append(key)
                continue
            if isinstance(review_by, str):
                review_by = datetime.date.fromisoformat(review_by)
            if review_by < today:
                past_due.append((review_by, key, entry.get("heat", "unnamed heat")))
    total = sum(counts.values())
    summary = ", ".join(f"{tag} {n}" for tag, n in sorted(counts.items()))
    print(f"ledger: {total} entries: {summary}")
    for review_by, key, heat in sorted(past_due):
        print(f"  PAST DUE {key}: staged for {heat}, review_by {review_by}")
    for key in malformed:
        print(f"  MALFORMED {key}: staged-for-bench without review_by")
    if not past_due and not malformed:
        print("  all staged entries inside their review window")
    return 0


if __name__ == "__main__":
    sys.exit(main())
