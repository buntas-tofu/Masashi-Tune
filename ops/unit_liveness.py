#!/usr/bin/env python3
"""
unit_liveness.py: does the fabric's systemd layer actually RUN?

WHY THIS EXISTS, 2026-08-16. A guard service on one node had been dead since
2026-08-08 21:51 and nothing on this fleet noticed for eight days. The unit was
installed DISABLED under the "staged until a consumer exists" policy, hand
started, and it did not survive the next reboot.

The root cause is not that policy. It is that the failure fell between the
fleet's two instruments and neither instrument was wrong:

  the board (/api/health)         watches ROSTER SEATS. The guard is
                                   deliberately not a roster seat, so the
                                   board is right to say nothing about it.
  unit_drift.py                    watches unit FILES: installed against
                                   recorded, drop-in hashes, portability.
                                   There is not one is-active check in it,
                                   by design and by name.

So the drift gate confirmed every morning for eight days that the unit file
existed and matched the record, which was true, while the service was dead.
Every non-seat service on this fleet had the same hole under it: the guard,
the escalate helper, the keeper, the recorder, ltm-gather, morning-report.

WHY A SIBLING RATHER THAN AN EXTENSION of unit_drift.py. Four reasons, and the
fourth is the one that decided it.

  1. Different contract. Drift OWNS the recorded fleet state and mutates it
     with --capture. Liveness only READS that record and never writes it, so
     the dependency runs one direction and stays legible.
  2. Different probe. Drift reads unit file BODIES and refuses any that look
     like they carry a credential. Liveness reads runtime STATE and never
     touches a body, so the credential guard has nothing to guard.
  3. The house pattern in morning-report.sh is one gate, one tool, one log.
     Six gates already run that way and the report reads them by name.
  4. Two questions inside one instrument is how this gap opened in the first
     place. A tool named for file drift that also half-answered liveness
     would have read as covered, which is the exact failure being fixed.

WHAT IT REPORTS. Five classes over the units recorded at units/fleet/<node>/.

  DOWN          enabled and not running. The headline failure class. A timer
                that is enabled and not active never fires; a long-running
                service that is enabled and not active is the reboot that ate
                it. A RESIDENT roster seat that is not running lands here too
                even when its unit file is disabled, because a resident seat
                is by definition expected up.
  DEAD TIMER    active, and never going to fire again. An active timer with no
                scheduled next elapse whose triggered unit is not running has
                nothing left to arm it. Judging a timer purely on ActiveState
                would have called the recorder healthy on two nodes while
                the odometer had not written in two days.
  FAILED RUN    the unit's last run ended in something other than success.
                This is how a nightly oneshot reports; a oneshot is inactive
                between runs and that is not a signal, but its Result is.
  ADVISORY      installed but DISABLED, non-seat services only. Never a
                failure: it is the legitimate staging posture. It is reported
                because it means "runs only until the next reboot", which is
                precisely the sentence nobody got to read about the guard.
  RESERVED      a seat down because the operator claimed its card. Never a
                fault, per the card posture ruling. Read from a per-node
                posture file, path from FLEET_POSTURE_FILE.

CRYING WOLF IS THE FAILURE MODE, so the exclusions are deliberate:

  oneshot services are never DOWN. Inactive between runs is their healthy
  state. A oneshot driven by a timer is judged by that timer; a oneshot with
  no timer is judged by nothing except its last Result. Type= is read from
  the RECORDED unit text, which is the versioned truth, with the live Type as
  fallback.
  lazy roster seats are never DOWN. Asleep is their declared posture. They
  are counted in the coverage line so silence stays distinguishable from a
  check that never ran.
  static units are never ADVISORY. A unit with no [Install] section cannot be
  enabled and reporting it as disabled would be an accusation about nothing.
  transitional states (activating, deactivating, reloading) are never DOWN.
  every candidate finding is CONFIRMED by a second read a few seconds later.
  A single read is not a measurement, house law, and here it also closes the
  microsecond window where a timer has fired and not yet re-armed.

COVERAGE BOUNDARY, stated rather than implied. This gate watches exactly the
units unit_drift.py has RECORDED. A hand-lit unit that has never been captured
is invisible here, and on the day this landed there was one: a service,
enabled on a node and unrecorded, which the drift gate reports as NEW. The two
gates compose in that order and only in that order. Drift finds the new unit,
a capture records it, and this gate watches it from the next morning. Reading
live units instead would have made liveness independent of the record, which
sounds better and is worse: it would report every stray and half-retired unit
on a node as fleet business, and the record is the fleet's own declaration of
what it means to run.

Exit code is always 0. It reports, the operator judges, same contract as
unit_drift.py and machine_profile.py. A node that cannot be reached is
UNREACHABLE and contributes no findings at all, never a pile of them.

Floor: DMF. No em dashes, no ellipses.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fleet_config as cfg  # noqa: E402

# Nodes reached by ssh alias, each alias carrying its own per-node username.
# The local node is detected by hostname rather than named, so the chair can
# move again without editing this file. Same posture as unit_drift.py and
# machine_profile.py. Names come from FLEET_NODES.
NODES = cfg.nodes()

FLEET = cfg.units_record()
POSTURE_FILE = cfg.env("FLEET_POSTURE_FILE", cfg.DEFAULT_POSTURE_FILE)
# Optional. Unset FLEET_ROSTER_DIR skips the roster-coupled seat checks and the
# report says so, so a skipped check never reads as a clean one.
ROSTER = cfg.roster_dir()

# How long an active timer with no scheduled next elapse may go without firing
# before it is called dead. The only two ways a timer reaches that state are
# (a) its triggered unit is running right now, which the triggered-unit check
# already excludes, and (b) it will never fire again. This floor is the belt
# on that check: it covers the instant between a triggered unit going inactive
# and systemd re-arming the timer. Fifteen minutes is generous against the
# shortest timer on the fleet (the recorder at 60s, so fourteen missed
# firings) and irrelevant to the long ones, which are OnCalendar and always
# carry a computed next elapse while active.
STALE_TRIGGER_S = 900

# Gap before the confirm read. A daily gate at 05:52 can afford it.
CONFIRM_DELAY_S = 5.0

# Sentinel age for a timer that has never fired at all.
NEVER_TRIGGERED = -1

# Unit names are interpolated into a shell command, so they are validated
# first. systemd's own legal set, no wildcards and no shell metacharacters.
SAFE_UNIT = re.compile(r"^[A-Za-z0-9@:_.-]+$")

# ActiveState values that mean "on its way somewhere", never a fault. A
# service bouncing under Restart=on-failure sits in activating/auto-restart
# and calling that down is how a gate earns being ignored.
TRANSITIONAL = {"activating", "deactivating", "reloading"}

# UnitFileState values that count as enabled at boot.
ENABLED_STATES = {"enabled", "enabled-runtime"}

# UnitFileState values where "disabled" is not a meaningful accusation.
# static has no [Install] at all; the empty string is a unit systemd could
# not find, which is unit_drift.py's MISSING class and not ours.
NOT_ENABLEABLE = {"static", "indirect", "generated", "transient", "alias", ""}

# The properties one round trip needs. All single-line scalars, so a line
# containing "=" is a property and a line without one is a sentinel.
PROPS = [
    "Id", "LoadState", "ActiveState", "SubState", "UnitFileState", "Type",
    "Result", "TriggeredBy", "Unit",
    "NextElapseUSecRealtime", "NextElapseUSecMonotonic", "LastTriggerUSec",
]

# One round trip per node.
#
# XDG_RUNTIME_DIR: a non-login ssh command inherits the user's session bus on
# this fleet (verified on three nodes, systemd 255), but the
# default is not guaranteed on a box with no active session, so it is set
# explicitly from the target's own uid. Never a hardcoded home and never
# another node's path; the fleet runs three username conventions.
#
# Timer ages are computed ON THE NODE with date(1) rather than parsed here.
# LastTriggerUSec comes back as human wall clock with a timezone abbreviation
# ("Sat 2026-08-15 01:22:13 EDT") and the node is the only thing that knows
# what that abbreviation meant at that instant.
PROBE = r"""
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
if [ -r "__POSTURE__" ]; then
  printf 'P %s\n' "$(base64 -w0 < "__POSTURE__")"
fi
systemctl --user show __PROPS__ __UNITS__ 2>/dev/null
for u in __TIMERS__; do
  lt=$(systemctl --user show -p LastTriggerUSec --value "$u" 2>/dev/null)
  if [ -z "$lt" ] || [ "$lt" = "n/a" ]; then printf 'A %s never\n' "$u"; continue; fi
  e=$(date -d "$lt" +%s 2>/dev/null) || continue
  [ -n "$e" ] || continue
  printf 'A %s %s\n' "$u" "$(( $(date +%s) - e ))"
done
printf 'PROBE_OK\n'
"""


def probe(node, local_host, units):
    """Read one node's runtime unit state.

    Returns a dict {"units": {name: props}, "ages": {timer: seconds},
    "posture": raw or None} or None when the node could not be read at all.
    None means UNREACHABLE and produces no findings anywhere downstream.
    """
    units = [u for u in units if SAFE_UNIT.match(u)]
    if not units:
        return {"units": {}, "ages": {}, "posture": None}
    timers = [u for u in units if u.endswith(".timer")]

    script = (PROBE
              .replace("__POSTURE__", POSTURE_FILE)
              .replace("__PROPS__", " ".join(f"-p {p}" for p in PROPS))
              .replace("__UNITS__", " ".join(units))
              .replace("__TIMERS__", " ".join(timers) if timers else "''"))

    cmd = ["bash", "-c", script] if node == local_host else [
        "ssh", *cfg.ssh_opts(), node, script
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if "PROBE_OK" not in out.stdout:
        # Either ssh never landed or the probe died partway. A partial read is
        # reported as unreachable rather than as findings, because a truncated
        # unit list reads as a pile of missing services.
        return None

    parsed, ages, posture, block = {}, {}, None, {}
    for line in out.stdout.splitlines():
        if line == "PROBE_OK":
            continue
        if not line.strip():
            if block.get("Id"):
                parsed[block["Id"]] = block
            block = {}
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            block[k] = v
            continue
        parts = line.split(" ")
        if parts[0] == "P" and len(parts) >= 2:
            try:
                posture = base64.b64decode(parts[1]).decode("utf-8", "replace")
            except Exception:
                posture = None
        elif parts[0] == "A" and len(parts) >= 3:
            # NEVER_TRIGGERED is distinct from a missing key. A missing key
            # means the node could not parse its own timestamp, and that
            # accuses nothing; "never" is a fact about the timer.
            if parts[2] == "never":
                ages[parts[1]] = NEVER_TRIGGERED
                continue
            try:
                ages[parts[1]] = int(parts[2])
            except ValueError:
                continue
    if block.get("Id"):
        parsed[block["Id"]] = block
    return {"units": parsed, "ages": ages, "posture": posture}


def recorded_units(node):
    """Unit names recorded for a node, with their recorded bodies."""
    d = FLEET / node
    if not d.is_dir():
        return {}
    return {f.name: f.read_text(errors="replace") for f in sorted(d.glob("*"))
            if f.is_file() and f.name != "DROPINS.sha256"
            and (f.name.endswith(".service") or f.name.endswith(".timer"))}


def recorded_type(body):
    """Type= as the REPO records it. The versioned text is the truth about
    what a unit is meant to be; the live value is only the fallback, and it is
    a fallback rather than the primary read because a node whose unit body
    drifted is unit_drift.py's finding, not a reason to re-classify here."""
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("Type="):
            return s.split("=", 1)[1].strip()
    return ""


def seat_map():
    """(node, unit_filename) -> {"key", "name", "lazy"} for every roster seat
    that declares both a unit and a node.

    Anchored to the roster because the roster is EXECUTED config: the registry
    loads it and the view serves from it, so it cannot rot quietly. Same
    reasoning as unit_drift.identity(). When FLEET_ROSTER_DIR is unset there is
    no roster to read, and the caller reports that as a skipped check rather
    than as a clean fleet."""
    if ROSTER is None:
        return {}, "FLEET_ROSTER_DIR is unset, seat checks skipped"
    try:
        import tomllib
        seats = tomllib.loads((ROSTER / "seats.toml").read_text()).get("seats", {})
    except Exception:
        return {}, "roster unreadable"
    out = {}
    for key, s in seats.items():
        unit, node = s.get("unit"), s.get("node")
        if not (unit and node):
            continue
        out[(node, f"{unit}.service")] = {
            "key": key,
            "name": s.get("name", key),
            # staged and lazy both mean "not expected to be running". The
            # roster keeps them separate (staged has no serve path proven
            # yet, lazy wakes on summon) and liveness does not care which.
            "lazy": bool(s.get("lazy", False) or s.get("staged", False)),
        }
    return out, ""


def reserved_keys(posture_raw):
    """Seat keys rested by a live card claim. A seat down because the operator
    took its card is RESERVED, never a fault, per the 2026-08-09 card posture
    ruling. An unreadable claim file reserves nothing and says so by returning
    the error, because guessing here would hide a real down seat."""
    if not posture_raw:
        return set(), ""
    try:
        raw = json.loads(posture_raw)
    except (ValueError, TypeError) as e:
        return set(), f"posture.json unreadable: {e}"
    keys = set()
    for claim in (raw.get("claims") or {}).values():
        for k in (claim.get("rested") or []):
            keys.add(k)
    return keys, ""


def no_next_elapse(p):
    """True when an active timer has nothing scheduled. Measured on systemd
    255: an armed OnCalendar timer reports a date in NextElapseUSecRealtime
    and 0 monotonic; a timer with nothing left reports an empty realtime and
    monotonic infinity."""
    rt = p.get("NextElapseUSecRealtime", "").strip()
    mono = p.get("NextElapseUSecMonotonic", "").strip()
    return rt in ("", "n/a") and mono in ("infinity", "")


def advisory_note(filestate, kind):
    """The advisory line's second half. A masked unit gets its own sentence:
    "runs only until the next reboot" is true of a hand-started disabled unit
    and flatly false of a masked one, which cannot start at all. One wrong
    sentence in a daily report is how a gate stops being read."""
    if filestate.startswith("masked"):
        return (f"MASKED. This {kind} cannot start at all until it is "
                f"unmasked, which is a decision somebody made on the node "
                f"and nowhere else.")
    return (f"Legitimate for a staged {kind}, and it means it runs only "
            f"until the next reboot.")


def judge(node, recorded, live, seats, reserved):
    """Classify one node's recorded units. Returns lists of finding tuples
    plus the coverage counts, so silence stays distinguishable from a check
    that never ran."""
    down, dead_timer, failed, advisory, held, absent = [], [], [], [], [], []
    checked = lazy_skipped = 0

    props = live["units"]
    ages = live["ages"]

    for name, body in recorded.items():
        p = props.get(name)
        if p is None or p.get("LoadState") == "not-found":
            # unit_drift.py already owns this as MISSING. Counted, not
            # re-accused: two gates shouting the same finding teaches the
            # reader to skim both.
            absent.append((node, name))
            continue

        state = p.get("ActiveState", "")
        filestate = p.get("UnitFileState", "")
        result = p.get("Result", "success")
        enabled = filestate in ENABLED_STATES
        active = state == "active"
        seat = seats.get((node, name))
        utype = recorded_type(body) or p.get("Type", "")
        is_timer = name.endswith(".timer")

        if seat and seat["lazy"]:
            lazy_skipped += 1
            continue

        checked += 1
        if seat and seat["key"] in reserved and not active:
            held.append((node, name, seat["name"]))
            continue

        if result and result != "success":
            failed.append((node, name, result, p.get("SubState", "")))

        if is_timer:
            if active and no_next_elapse(p):
                # Unit= on a timer is the service it triggers. If that service
                # is running right now, the timer is simply between firings
                # and re-arms when it finishes; that is health, not a fault.
                trig = p.get("Unit", "").strip()
                trig_active = props.get(trig, {}).get("ActiveState", "") == "active"
                age = ages.get(name)
                stale = age is not None and (age == NEVER_TRIGGERED
                                             or age > STALE_TRIGGER_S)
                if not trig_active and stale:
                    dead_timer.append((node, name, trig or "its service", age))
            elif not active and state not in TRANSITIONAL:
                if enabled:
                    down.append((node, name, filestate, state,
                                 "timer, so it never fires"))
                elif filestate not in NOT_ENABLEABLE:
                    advisory.append((node, name, filestate, state,
                                     advisory_note(filestate, "timer")))
            continue

        # Services from here down.
        if utype == "oneshot":
            # Never DOWN. Inactive between runs is the healthy state of a
            # oneshot, and the thing that would actually be wrong (the timer
            # stopped, or the last run failed) is reported by the two classes
            # that can see it. A oneshot with no timer at all is judged by
            # nothing except its Result, which is honest: nothing on this
            # fleet declares when it should have run.
            continue

        if not active and state not in TRANSITIONAL:
            if enabled:
                down.append((node, name, filestate, state,
                             f"resident seat {seat['name']}" if seat
                             else "service"))
            elif seat:
                # A resident seat that is not running is worth reporting even
                # when its unit file is disabled, because the roster is the
                # declaration that it should be up.
                down.append((node, name, filestate, state,
                             f"resident seat {seat['name']}, unit not enabled"))
            elif filestate not in NOT_ENABLEABLE:
                advisory.append((node, name, filestate, state,
                                 advisory_note(filestate, "service")))
        elif active and not enabled and not seat and filestate not in NOT_ENABLEABLE:
            # The guard-service shape while it is still up: hand started, will
            # not come back after the next reboot.
            advisory.append((node, name, filestate, state,
                             advisory_note(filestate, "service")))

    return {
        "down": down, "dead_timer": dead_timer, "failed": failed,
        "advisory": advisory, "held": held, "absent": absent,
        "checked": checked, "lazy": lazy_skipped,
    }


def confirm(results, local_host, recorded_all, seats):
    """Second read of the candidate units only. A single read is not a
    measurement (house law), and here it also closes the window between a
    timer's triggered unit going inactive and systemd re-arming the timer.
    Only findings that reproduce survive."""
    candidates = {}
    for node, r in results.items():
        names = {f[1] for f in r["down"]} | {f[1] for f in r["dead_timer"]} \
            | {f[1] for f in r["failed"]}
        if names:
            candidates[node] = names
    if not candidates:
        return results, 0, 0

    time.sleep(CONFIRM_DELAY_S)
    dropped = 0
    for node, names in candidates.items():
        # Re-probe the whole recorded set for that node: a timer's verdict
        # depends on its triggered unit's state, so a narrowed probe would
        # have to guess which companions to include.
        again = probe(node, local_host, list(recorded_all[node]))
        if again is None:
            # Went unreachable between the reads. Keep the first verdict and
            # say nothing new; dropping it would hide a real finding behind a
            # transient network.
            continue
        res, _ = reserved_keys(again["posture"])
        second = judge(node, recorded_all[node], again, seats, res)
        for cls in ("down", "dead_timer", "failed"):
            keep = {f[1] for f in second[cls]}
            before = len(results[node][cls])
            results[node][cls] = [f for f in results[node][cls] if f[1] in keep]
            dropped += before - len(results[node][cls])
    return results, len(candidates), dropped


def report(results, unreachable, unrecorded, node_count, roster_err,
           posture_errs, dropped):
    """Markdown to stdout. Exit 0 always: it reports, the operator judges."""
    agg = {k: [] for k in ("down", "dead_timer", "failed", "advisory",
                           "held", "absent")}
    checked = lazy = 0
    for r in results.values():
        for k in agg:
            agg[k].extend(r[k])
        checked += r["checked"]
        lazy += r["lazy"]

    out = ["# Unit liveness gate", ""]
    out += [f"**Verdict: {len(agg['down'])} down, "
            f"{len(agg['dead_timer'])} dead timer, "
            f"{len(agg['failed'])} failed run, "
            f"{len(agg['advisory'])} advisory.** "
            f"{node_count - len(unreachable) - len(unrecorded)} of "
            f"{node_count} nodes judged, "
            f"{checked} units judged, {lazy} lazy seats skipped as expected "
            f"asleep, {len(agg['absent'])} recorded units not installed "
            f"(unit_drift.py owns those).", ""]
    if dropped:
        out += [f"{dropped} candidate finding(s) did not reproduce on the "
                f"confirm read and were dropped. A single read is not a "
                f"measurement.", ""]
    if unreachable:
        out += [f"UNREACHABLE, contributing no findings rather than a pile of "
                f"them: {', '.join(unreachable)}.", ""]
    if unrecorded:
        out += [f"NOT JUDGED, nothing recorded at `units/fleet/<node>/` so "
                f"there was nothing to check against: {', '.join(unrecorded)}. "
                f"Run `unit_drift.py --capture` to give this gate something "
                f"to watch.", ""]
    if roster_err:
        out += [f"**Roster not read ({roster_err}).** Every seat is being "
                f"judged as a plain service, so lazy seats will read as down.",
                ""]
    for node, msg in posture_errs:
        out += [f"**`{node}` {msg}.** Card claims cannot be read there, so a "
                f"reserved seat would report as down.", ""]

    def section(title, rows, fmt, empty):
        out.append(f"## {title}")
        out.append("")
        out.extend([f"- {fmt(r)}" for r in rows] if rows else [empty])
        out.append("")

    section("DOWN, enabled but not running", agg["down"],
            lambda r: f"`{r[0]}` **{r[1]}** is `{r[3]}` with unit file "
                      f"`{r[2]}` ({r[4]}). Expected up and it is not.",
            "None. Everything enabled is running.")
    def since(secs):
        if secs == NEVER_TRIGGERED:
            return "and it has never triggered"
        return (f"{secs // 3600}h{(secs % 3600) // 60:02d}m since it last "
                f"triggered")

    section("DEAD TIMER, active but never firing again", agg["dead_timer"],
            lambda r: f"`{r[0]}` **{r[1]}** is active with no next elapse, "
                      f"{since(r[3])} {r[2]}, which is not running. It will "
                      f"not fire again without a restart.",
            "None. Every active timer has a next elapse scheduled.")
    section("FAILED RUN, last invocation did not succeed", agg["failed"],
            lambda r: f"`{r[0]}` **{r[1]}** Result=`{r[2]}` (sub `{r[3]}`). "
                      f"Read the journal on the node.",
            "None. Every unit's last run ended in success.")
    section("ADVISORY, installed but not enabled (non-seat)", agg["advisory"],
            lambda r: f"`{r[0]}` **{r[1]}** unit file `{r[2]}`, currently "
                      f"`{r[3]}`. {r[4]}",
            "None. Every non-seat unit is enabled or static.")
    section("RESERVED, seat rested by a card claim", agg["held"],
            lambda r: f"`{r[0]}` **{r[1]}** ({r[2]}) is down because the "
                      f"operator holds its card. Reserved, not a fault.",
            "None. No card is claimed.")

    print("\n".join(out))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("nodes", nargs="*", help="limit to these nodes (default all)")
    ap.add_argument("--no-confirm", action="store_true",
                    help="skip the confirm read; faster, and less honest")
    args = ap.parse_args()

    targets = args.nodes or NODES
    unknown = [n for n in targets if n not in NODES]
    if unknown:
        print(f"unknown node(s): {', '.join(unknown)}", file=sys.stderr)
        return 0

    if not FLEET.exists():
        print("# Unit liveness gate\n\n**GATE BLIND.** No recorded fleet state "
              "at `tools/units/fleet/`. Run `unit_drift.py --capture` first: "
              "this gate reads that record and never writes it.")
        return 0

    local = subprocess.run(["hostname"], capture_output=True, text=True).stdout.strip()
    seats, roster_err = seat_map()

    recorded_all = {n: recorded_units(n) for n in targets}
    results, unreachable, unrecorded, posture_errs = {}, [], [], []
    for node in targets:
        rec = recorded_all[node]
        if not rec:
            # Blind is never clean. A node with nothing recorded was never
            # probed, and absorbing it into the reachable count would make
            # the verdict read as coverage it does not have.
            unrecorded.append(node)
            continue
        live = probe(node, local, list(rec))
        if live is None:
            unreachable.append(node)
            continue
        res, perr = reserved_keys(live["posture"])
        if perr:
            posture_errs.append((node, perr))
        results[node] = judge(node, rec, live, seats, res)

    dropped = 0
    if not args.no_confirm:
        results, _, dropped = confirm(results, local, recorded_all, seats)

    report(results, unreachable, unrecorded, len(targets), roster_err,
           posture_errs, dropped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
