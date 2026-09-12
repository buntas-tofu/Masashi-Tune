#!/usr/bin/env python3
"""Storage reconciler, layer 3 of three.

Layer 1 (the collector) walks one node and says what is there. This reads every
node's inventory, compares it against the ledger (layer 2, ledger.example.toml),
and reports where intention and disk disagree.

WHY IT EXISTS, and it is a dated finding rather than a design preference.
2026-08-03: five rooms of the primary storage root were found living only on one
node, two days after the working chair moved elsewhere. One concern held 17,079
files that a downstream process was still working; others held business and
personal archives. A migration had carried the repos perfectly and carried a few
directories by hand. Everything else outside a repo was invisible to it.

That is the same class that hid two other things the same week. A timer unit was
installed-only and never versioned, so a repo move could not carry it. Some
memory raw layers were gitignored, so a repo move could not see them either.
Three flavors of one failure: content a repo-shaped migration cannot perceive.
git covers the repo room. The memory sink covers its own tree. Nothing covered
the primary storage root, and that is where the mass and the irreplaceable
material live.

SCOPE. Primarily the primary storage root (FLEET_STORAGE_ROOT), plus any room
explicitly declared against another root. A scope note once justified a
root-only reading with "the repo room is reconciled by git and its remotes."
That justification was false for the exact material this file's own history
section names: some memory raw layers are GITIGNORED, which is why a repo move
could not see them, so git never covered them and no instrument did. The scope
note asserted a coverage that the paragraph above it denies. Corrected
2026-08-03 by an audit that re-walked it.

So a concern may declare `root`, defaulting to the primary storage root. A
non-primary root is opt-in: only declared rooms there are watched, and the
undeclared class stays primary-root-only, because every other repo room
genuinely IS covered by git and reporting them all would be the noise the
original note rightly feared. Roots are written home-relative (~/place) and
resolved per node against that inventory's own home, because a fleet can run
several username conventions and a literal path is correct at exactly one
address.

Of the five classes the design notes plan, this implements the three that answer
"could we lose this": unbacked, declared-but-absent, and undeclared.
Redundancy-beyond-declaration and head drift are still open.

Design rules inherited from the collector, and rule 4 is the load-bearing one:
a blind node is UNKNOWN, never empty. A node that is down has not lost its files,
and a family drift gate once spent fifteen mornings calling a misconfiguration a
clean bill of health. Read-only, stdlib-only, exit 0 always. It reports; the
operator judges.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fleet_config as cfg  # noqa: E402

HERE = Path(__file__).resolve().parent
LEDGER = Path(cfg.env("FLEET_LEDGER", str(HERE / "ledger.example.toml"))).expanduser()
# The collector's path on a node depends on where that node keeps this toolkit.
# Set FLEET_COLLECTOR to one or more candidate paths; the first that exists on a
# node is used. Default is a single neutral path.
COLLECTOR_CANDIDATES = cfg.csv_env("FLEET_COLLECTOR", cfg.DEFAULT_COLLECTOR)
COLLECTOR = COLLECTOR_CANDIDATES[0]
REMOTE_COLLECT = ("for p in " + " ".join(COLLECTOR_CANDIDATES) +
                  "; do [ -f \"$p\" ] && exec python3 \"$p\"; done; "
                  "echo 'collector not found' >&2; exit 3")
# Node names come from FLEET_NODES.
NODES = cfg.nodes()
ROOT = cfg.env("FLEET_STORAGE_ROOT", "~/storage")


def collect(node, local_host):
    """One node's inventory. None means blind, which is not the same as empty."""
    local_path = next((c for c in COLLECTOR_CANDIDATES
                       if Path(c).expanduser().is_file()), COLLECTOR)
    # Local runs prefer the collector shipped beside this file, so the pair
    # works on a checkout with no configuration.
    sibling = HERE / "collector.py"
    if sibling.is_file():
        local_path = str(sibling)
    cmd = (["python3", str(Path(local_path).expanduser())] if node == local_host
           else ["ssh", *cfg.ssh_opts(), node,
                 REMOTE_COLLECT])
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        return json.loads(p.stdout) if p.stdout.strip() else None
    except Exception:
        return None


def resolve_root(spec, inv):
    """A declared root as it is spelled on THIS node.

    Roots are declared home-relative because the fleet runs three username
    conventions; a literal /home/... is correct at exactly one address. The
    inventory carries its own home, so expansion never guesses.
    """
    if spec.startswith("~"):
        return inv.get("home", "") + spec[1:]
    return spec


def rooms_of(inv, root=ROOT):
    """The rooms of one root in one inventory, minus filesystem furniture.

    Returns None for a blind node (unknown), {} when the node simply has no
    such root, which is a real answer and not blindness.
    """
    if not inv:
        return None
    want = resolve_root(root, inv)
    for r in inv.get("roots", []):
        if r.get("path") == want:
            return {k: v for k, v in r.get("rooms", {}).items()
                    if k not in ("(root)", "lost+found")}
    return {}


def human(b):
    for u in ("B", "K", "M", "G", "T"):
        if b < 1024 or u == "T":
            return f"{b:.0f}{u}" if u == "B" else f"{b:.1f}{u}"
        b /= 1024


def main():
    ap = argparse.ArgumentParser(description="Storage reconciler, layer 3 of three")
    ap.add_argument("--json", action="store_true", help="emit raw findings as JSON")
    args = ap.parse_args()

    local = subprocess.run(["hostname"], capture_output=True, text=True).stdout.strip()
    invs = {n: collect(n, local) for n in NODES}
    blind = sorted(n for n, i in invs.items() if i is None)
    seen = {n: i for n, i in invs.items() if i is not None}

    ledger = {}
    if LEDGER.exists():
        ledger = tomllib.loads(LEDGER.read_text()).get("concern", {})

    # concern -> {node: stats}, derived from disk, never from the ledger.
    # The primary storage root first: every room found there becomes a concern
    # whether or not it is declared, which is what makes the undeclared class
    # possible at all.
    concerns: dict[str, dict] = {}
    for node, inv in seen.items():
        for name, stats in (rooms_of(inv, ROOT) or {}).items():
            concerns.setdefault(name, {})[node] = stats

    # Other roots are opt-in and declaration-driven: watch only the rooms the
    # ledger names. Everything else under the repo room genuinely is covered by
    # git,
    # and sweeping it in would be the noise the original scope note feared.
    for name, dec in ledger.items():
        root = dec.get("root", ROOT)
        if root == ROOT:
            continue
        room = dec.get("room", name)
        for node, inv in seen.items():
            stats = (rooms_of(inv, root) or {}).get(room)
            if stats:
                concerns.setdefault(name, {})[node] = stats

    # Design rule 1: a declared path that does not exist is a finding, not a
    # silent absence. A concern on zero readable nodes must still reach the
    # declared-but-absent check, so give it an entry to be checked against.
    for name in ledger:
        concerns.setdefault(name, {})

    unbacked, absent, undeclared = [], [], []
    for name, holders in sorted(concerns.items()):
        dec = ledger.get(name)
        if dec is None:
            undeclared.append((name, sorted(holders)))
            continue
        for n in dec.get("mirror", []) + ([dec["head"]] if dec.get("head") else []):
            if n not in holders and n not in blind:
                absent.append((name, n))
        if len(holders) == 1 and not dec.get("single_home_ok", False):
            unbacked.append((name, next(iter(holders)), holders))
    # Undeclared rooms still get the unbacked check; that is the whole point.
    for name, holders in undeclared:
        if len(holders) == 1:
            unbacked.append((name, holders[0], concerns[name]))

    if args.json:
        print(json.dumps({"blind": blind, "unbacked": unbacked,
                          "absent": absent, "undeclared": undeclared}, indent=2))
        return 0

    out = ["# Storage reconciler", ""]
    if not LEDGER.exists():
        out += ["**GATE BLIND.** No ledger file. Reporting what is on disk with no "
                "declaration to check it against. Author the ledger to enable the "
                "declared-but-absent and redundancy classes.", ""]
    out += [f"**Verdict: {len(unbacked)} unbacked, {len(absent)} declared-but-absent, "
            f"{len(undeclared)} undeclared.** {len(seen)} of {len(NODES)} nodes read.", ""]
    if blind:
        out += [f"Blind, and reported as UNKNOWN rather than empty: {', '.join(blind)}. "
                "A node that is down has not lost its files.", ""]

    out += ["## UNBACKED, a concern living on exactly one node", ""]
    if unbacked:
        for name, node, holders in unbacked:
            b = holders[node]["bytes"] if isinstance(holders.get(node), dict) else 0
            f = holders[node]["files"] if isinstance(holders.get(node), dict) else 0
            out.append(f"- **{name}** on `{node}` only. {human(b)}, {f:,} files. "
                       f"One disk failure from gone.")
    else:
        out.append("None. Every concern is held on more than one node or declared "
                   "single-home on purpose.")
    out.append("")

    out += ["## DECLARED BUT ABSENT, the ledger says a node holds it and disk disagrees", ""]
    out.extend([f"- **{n}** declares `{name}` and does not have it." for name, n in absent]
               or ["None."])
    out.append("")

    out += ["## UNDECLARED, on disk with no entry in the ledger", ""]
    out.extend([f"- **{name}** on {', '.join(f'`{h}`' for h in holders)}. "
                f"Present by accident or by an intention nobody wrote down."
                for name, holders in undeclared] or ["None."])
    out.append("")

    out += ["## Holdings", "", "| concern | " + " | ".join(NODES) + " |",
            "|---|" + "---|" * len(NODES)]
    for name in sorted(concerns):
        cells = []
        for n in NODES:
            if n in blind:
                cells.append("?")
            elif n in concerns[name]:
                cells.append(human(concerns[name][n]["bytes"]))
            else:
                cells.append("-")
        out.append(f"| {name} | " + " | ".join(cells) + " |")
    out.append("")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
