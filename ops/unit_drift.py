#!/usr/bin/env python3
"""
unit_drift.py: the smoke detector for the fabric's systemd layer.

WHY THIS EXISTS, 2026-08-03. The fabric runs roughly forty user units across five
nodes and, until this tool, versioned four pairs of them. Everything else was
hand-lit and lived only in a node's own ~/.config/systemd/user. An installed-only
unit is invisible to every migration that moves the repo, and this fleet
provisions nodes by copying units between boxes, so the gap compounds.

The class has now bitten three times:

  1. 2026-07-22, one node lost five units at once on a boot.
  2. Resident seats did not survive reboot because units were hand-lit as
     staged or disabled and came back dark. Both are in RUNTIME_CUTOVER_RUNBOOK.
  3. 2026-08-01, the chair moved to another node and one timer-driven unit did not
     follow, because there was nothing in the tree to follow it with. Nobody
     noticed for two days, because the old chair kept quietly doing the job.

Case three is the one that matters for design. It was silent. Nothing failed,
no probe went red, and the only tell was a doc annotation quietly regenerating
without its timer line. A gap that announces itself is a bug; a gap that does
not is a class, and a class needs an instrument.

WHAT IT DOES. Two modes over one contract.

  --capture   refresh the recorded fleet state under units/fleet/<node>/
  (default)   diff what is installed against what was recorded, report markdown

It reports four things, and the fourth is the one that catches the next
landmine rather than the last one:

  NEW       installed on a node, never recorded. The hand-lit unit.
  MISSING   recorded, no longer installed. The lost unit, or a deliberate
            retirement that nobody wrote down.
  DRIFT     recorded and installed, contents differ.
  PORTABILITY  a unit hardcoding an absolute home path. A fleet can run
            several username conventions across its nodes and the standing law
            is to always use the target's own $HOME. A hardcoded path
            works perfectly on the box it was written on and fails silently the
            first time it is copied, which is exactly how a fleet provisions.
            The recorder unit carried this on both twins until 2026-08-03.

CREDENTIAL POSTURE, and it is deliberate rather than incidental. Unit CONTENT is
recorded. Drop-in content is NEVER recorded, only its name and hash, because
a service drop-in can hold an external service's API key and the standing rule
is that the key is env-only in the unit and never in git. On top
of that policy a content guard runs on every capture: any unit whose body looks
like it carries a credential is refused and reported rather than written. The
policy is the design and the guard is the belt, because a rule that depends on
nobody ever putting a key in a .service file is a rule waiting to be broken.

Exit code is always 0. It reports, the operator judges, same contract as
family-drift.py.
"""

import argparse
import base64
import hashlib
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fleet_config as cfg  # noqa: E402

# The nodes to watch. Names are deployment values, not code: set FLEET_NODES
# to a comma-separated list reached by ssh alias. The local node is detected by
# hostname rather than named, so this file does not need editing when the chair
# moves again. That is the same mistake a hardcoded node map made elsewhere in
# the family and it is not repeated here.
NODES = cfg.nodes()

UNIT_DIR = cfg.env("FLEET_UNIT_DIR", cfg.DEFAULT_UNIT_DIR)
FLEET = cfg.units_record()

# Optional. When FLEET_ROSTER_DIR is unset the identity check is skipped and
# the report says so, so silence stays distinguishable from a check that ran.
ROSTER = cfg.roster_dir()

# A unit body that matches this is refused by the capture guard. Deliberately
# broad: a false positive costs one line of report, a false negative costs a key.
CRED = re.compile(
    r"(?i)(api[_-]?key|auth[_-]?token|access[_-]?token|secret|password|passwd|bearer\s)"
)

# An absolute home path in an ExecStart or similar. %h is the portable form.
HARDCODED_HOME = re.compile(r"/home/[A-Za-z0-9._-]+/")

# Config-as-identity: the seat and vessel declarations the view actually loads.

# The segment of a vessel key that discriminates one body from another: e2b,
# e4b, 26b, 30b, 300m, 86m. Sizes and variants are what distinguish vessels in
# practice, and the E4B-to-E2B flip proves they are also what goes stale in
# prose. A key with no such segment (nemotron-3-super) simply contributes no
# token and is never accused of anything.
VARIANT = re.compile(r"^e?\d+[bm]$")

# One round trip per node. Emits one line per unit as "U <name> <base64 body>"
# and one line per drop-in as "D <unit.d> <conf> <sha256>". base64 keeps unit
# bodies free of any delimiter collision; drop-ins never leave the node as text.
PROBE = r"""
cd ~/.config/systemd/user 2>/dev/null || exit 0
for f in *.service *.timer; do
  [ -e "$f" ] || continue
  printf 'U %s %s\n' "$f" "$(base64 -w0 < "$f")"
done
for d in *.d; do
  [ -d "$d" ] || continue
  for c in "$d"/*.conf; do
    [ -e "$c" ] || continue
    printf 'D %s %s %s\n' "$d" "$(basename "$c")" "$(sha256sum < "$c" | cut -d" " -f1)"
  done
done
for u in $(systemctl --user list-unit-files --state=enabled --no-legend 2>/dev/null | awk '{print $1}'); do
  printf 'E %s\n' "$u"
done
"""


def probe(node, local_host):
    """Read one node's unit state. Returns (units, dropins, enabled) or None."""
    cmd = ["bash", "-c", PROBE] if node == local_host else [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", node, PROBE
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return None
    if out.returncode != 0 and not out.stdout.strip():
        return None

    units, dropins, enabled = {}, {}, set()
    for line in out.stdout.splitlines():
        parts = line.split(" ")
        if parts[0] == "U" and len(parts) >= 3:
            try:
                units[parts[1]] = base64.b64decode(parts[2]).decode("utf-8", "replace")
            except Exception:
                continue
        elif parts[0] == "D" and len(parts) >= 4:
            dropins.setdefault(parts[1], {})[parts[2]] = parts[3]
        elif parts[0] == "E" and len(parts) >= 2:
            enabled.add(parts[1])
    return units, dropins, enabled


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def capture(state):
    """Write the recorded fleet state. Refuses any unit the guard flags."""
    written, refused = 0, []
    for node, s in state.items():
        if s is None:
            continue
        units, dropins, _ = s
        d = FLEET / node
        d.mkdir(parents=True, exist_ok=True)
        for stale in d.glob("*"):
            if stale.is_file() and stale.name not in units and stale.name != "DROPINS.sha256":
                stale.unlink()
        for name, body in sorted(units.items()):
            if CRED.search(body):
                refused.append(f"{node}/{name}")
                continue
            (d / name).write_text(body)
            written += 1
        # Drop-ins are recorded as name and hash only. Never their content.
        lines = [
            f"{h}  {unit}/{conf}"
            for unit, confs in sorted(dropins.items())
            for conf, h in sorted(confs.items())
        ]
        (d / "DROPINS.sha256").write_text(
            "# Drop-in fingerprints. Names and hashes only, never content:\n"
            "# A drop-in can carry an external service's API key and the\n"
            "# standing rule is env-only, never in git.\n"
            + "\n".join(lines) + ("\n" if lines else "")
        )
    return written, refused


def _tokens(key: str) -> set:
    return {p for p in key.lower().split("-") if VARIANT.match(p)}


def identity():
    """The third edge of the triangle: does the RECORDED unit still describe what
    the ROSTER declares the seat serves?

    The other checks here compare installed against recorded, which structurally
    cannot catch a unit whose prose went stale, because both copies go stale
    together. That is precisely what happened to the four familiars: the
    2026-08-05 E2B flip moved the roster, the serve script and the running
    process, and left every Description reading "Gemma 4 E4B chat+vision" on a
    seat that is now an eyeless E2B. Installed matched recorded perfectly for the
    entire time the record was wrong.

    Anchored to the roster on purpose, and never the other way round. The roster
    is EXECUTED config: the registry loads it, the view serves from it, and
    /api/health reflects it, so a wrong roster shows up as a wrong board within
    one restart and cannot rot quietly. A Description is prose nobody executes.
    Checking prose against executed config is the only direction of that
    comparison that stays honest without a second gate to watch this one.

    Returns (findings, checked, skipped). Coverage travels with the verdict for
    the same reason the zoo gate's does: silence has to be distinguishable from
    a check that never ran. When FLEET_ROSTER_DIR is unset the roster is not
    available and the check is skipped, reported as such rather than passing
    silently.
    """
    if ROSTER is None:
        return [("roster", "not configured",
                 "FLEET_ROSTER_DIR is unset, so the identity check is skipped")], 0, 0
    try:
        import tomllib
        seats = tomllib.loads((ROSTER / "seats.toml").read_text()).get("seats", {})
        vessels = tomllib.loads((ROSTER / "vessels.toml").read_text()).get("vessels", {})
    except Exception as e:
        return [("roster", "unreadable", f"cannot load roster at {ROSTER}: {e}")], 0, 0

    every = set().union(*(_tokens(v) for v in vessels)) if vessels else set()
    found, checked, skipped = [], 0, 0

    for key, seat in sorted(seats.items()):
        unit, node = seat.get("unit"), seat.get("node")
        vkey = seat.get("vessel")
        if not (unit and node and vkey):
            skipped += 1
            continue
        path = FLEET / node / f"{unit}.service"
        if not path.is_file():
            skipped += 1
            continue
        desc = ""
        for line in path.read_text().splitlines():
            if line.startswith("Description="):
                desc = line.split("=", 1)[1]
                break
        if not desc:
            skipped += 1
            continue
        checked += 1
        low = desc.lower()
        words = set(re.findall(r"[a-z0-9]+", low))

        # Only a token belonging to some OTHER vessel is an accusation. Shared
        # tokens (three vessels are 14b) and prose naming no vessel stay silent.
        wrong = sorted((words & every) - _tokens(vkey))
        if wrong:
            found.append((node, unit, f"describes `{', '.join(wrong)}` but the "
                                      f"roster declares `{vkey}`"))

        has_eyes = bool(vessels.get(vkey, {}).get("vision", False))
        if not has_eyes and "vision" in words:
            found.append((node, unit, f"claims vision, but `{vkey}` declares none"))
        elif has_eyes and "eyeless" in words:
            found.append((node, unit, f"claims eyeless, but `{vkey}` declares vision"))

    return found, checked, skipped


def report(state):
    """Markdown to stdout. Exit 0 always: it reports, the operator judges."""
    out = ["# Unit drift gate", ""]
    unreachable = [n for n, s in state.items() if s is None]
    reachable = [n for n, s in state.items() if s is not None]

    if not FLEET.exists():
        out += ["**GATE BLIND.** No recorded fleet state at `tools/units/fleet/`.",
                "Run `unit_drift.py --capture` to establish a baseline.", ""]
        print("\n".join(out))
        return

    new, missing, drift, portability, dropin_drift = [], [], [], [], []

    for node in reachable:
        units, dropins, enabled = state[node]
        d = FLEET / node
        recorded = {f.name: f.read_text() for f in d.glob("*")
                    if f.is_file() and f.name != "DROPINS.sha256"} if d.exists() else {}

        for name, body in sorted(units.items()):
            if name not in recorded:
                new.append((node, name, "enabled" if name in enabled else "not enabled"))
            elif sha(body) != sha(recorded[name]):
                drift.append((node, name))
            for m in HARDCODED_HOME.findall(body):
                portability.append((node, name, m))
        for name in sorted(recorded):
            if name not in units:
                missing.append((node, name))

        fp = d / "DROPINS.sha256"
        if fp.exists():
            was = {ln.split("  ", 1)[1]: ln.split("  ", 1)[0]
                   for ln in fp.read_text().splitlines() if "  " in ln and not ln.startswith("#")}
            now = {f"{u}/{c}": h for u, cs in dropins.items() for c, h in cs.items()}
            for k in sorted(set(was) | set(now)):
                if was.get(k) != now.get(k):
                    dropin_drift.append((node, k, "new" if k not in was else
                                         "gone" if k not in now else "changed"))

    ident, id_checked, id_skipped = identity()
    verdict = (f"{len(new)} new, {len(missing)} missing, {len(drift)} drift, "
               f"{len(portability)} portability, {len(dropin_drift)} drop-in, "
               f"{len(ident)} identity")
    out += [f"**Verdict: {verdict}.** "
            f"{len(reachable)} of {len(NODES)} nodes reachable.", ""]
    if unreachable:
        out += [f"Unreachable, reporting nothing about them rather than "
                f"inferring: {', '.join(unreachable)}.", ""]

    def section(title, rows, fmt, empty):
        out.append(f"## {title}")
        out.append("")
        out.extend([f"- {fmt(r)}" for r in rows] if rows else [empty])
        out.append("")

    section("NEW, installed but never recorded", new,
            lambda r: f"`{r[0]}` **{r[1]}** ({r[2]}). Hand-lit and unversioned.",
            "None. Every installed unit is recorded.")
    section("MISSING, recorded but no longer installed", missing,
            lambda r: f"`{r[0]}` **{r[1]}**. Lost, or retired without a note.",
            "None.")
    section("DRIFT, recorded and installed differ", drift,
            lambda r: f"`{r[0]}` **{r[1]}**.",
            "None. Installed matches recorded on every node.")
    section("PORTABILITY, hardcoded home path", portability,
            lambda r: f"`{r[0]}` **{r[1]}** carries `{r[2]}`. Should be `%h/`. "
                      f"Works where written, fails the first time it is copied.",
            "None. Every unit is home-relative.")
    section("DROP-IN fingerprints changed", dropin_drift,
            lambda r: f"`{r[0]}` **{r[1]}** {r[2]}. Content is never recorded, "
                      f"only the hash; inspect on the node.",
            "None.")
    section(f"IDENTITY, recorded unit contradicts the roster "
            f"({id_checked} seats checked, {id_skipped} without a recorded unit)",
            ident,
            lambda r: f"`{r[0]}` **{r[1]}** {r[2]}. The roster is what the view "
                      f"serves; the Description is prose. Correct the prose.",
            "None. Every recorded unit agrees with the seat it serves.")

    print("\n".join(out))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--capture", action="store_true",
                    help="refresh the recorded fleet state instead of diffing it")
    args = ap.parse_args()

    local = subprocess.run(["hostname"], capture_output=True, text=True).stdout.strip()
    state = {n: probe(n, local) for n in NODES}

    if args.capture:
        written, refused = capture(state)
        reachable = [n for n, s in state.items() if s is not None]
        print(f"captured {written} units across {len(reachable)} nodes "
              f"({', '.join(reachable)})")
        for n, s in state.items():
            if s is None:
                print(f"  WARN: unreachable, left as recorded: {n}")
        for r in refused:
            print(f"  REFUSED, body looks like it carries a credential: {r}")
    else:
        report(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
