#!/usr/bin/env python3
"""zoo_drift.py: the model-card gate.

Commissioned by the operator 2026-08-03, watching a diff pass close three gaps in
one morning: "we should have something like this for HF model cards. Community
progress has a direct impact to our system and potential efficiency leveraging."

WHY IT EARNS ITS PLACE. The casting dossier was built on 3,178 model cards read
on one day, and a card is not a fixed object. Licenses change. Quants get pulled
because they were broken. Base models get relabelled. Pathologies get documented
by people with more users than us. Every casting decision has a shelf life and
nothing measured that shelf life.

The concrete case is already in the record. The extraction bench reproduced a
Gemma 4 QAT degeneration across three silicon families, and the field already had
it, with a sharper mechanism and better numbers. Watching that card would have
said so BEFORE the bench rather than after. That is the standing rule
check-novelty-contribute-upstream, given an instrument.

CHEAPNESS IS THE DESIGN, not a nice property. The operator asked for RSS to avoid
calling out at all. HuggingFace publishes no per-repo feed (verified 2026-08-03:
/commits/main.atom is 404 on an ungated repo, and the 401s on a gated one are
gating rather than absence). But the API carries ETags and honors If-None-Match,
and a 304 costs zero bytes of body against 7,917 for a full GET. So a quiet day
across the whole watchlist is a few kilobytes of headers, which is lighter than
polling feeds would have been. ETags are cached in state.json and only a moved
ETag triggers any parsing at all.

IT DOES NOT SWAP ANYTHING. Operator, same day: "this is not an auto swap
classifier, I would still want to gate that action." It reports that a card moved
and what moved in it. Choosing to act is a ruling, and rulings are Tier 1. Same
contract as every other gate here: exit 0 always, it reports, the operator judges.

TWO QUESTIONS, and the second completes the loop the operator asked for.
  1. Did upstream change?  ETag, then a diff of the fields that carry decisions:
     license, base_model, the file list (a quant appearing or disappearing), and
     gated/disabled.
  2. Does our local copy still match what upstream says it is?  The hf downloader
     records the upstream commit and the blob sha256 beside every file it pulls,
     under .cache/huggingface/download/*.metadata. Comparing those against the
     repo's current LFS hashes catches a truncated pull and a silently replaced
     quant, which is what "we have to be able to trust the seats" actually needs.

NETWORK POSTURE, labeled because everything else here is sovereign by
construction: outbound to huggingface.co, read-only public metadata, no auth, no
payload. Nothing about this fabric leaves. Model weights are the one class of
thing here that is re-fetchable rather than irreplaceable.

Usage:
    zoo_drift.py              diff the watchlist against upstream, markdown out
    zoo_drift.py --discover   derive repo ids from disk by confirming that a
                              candidate's commit matches the one we recorded,
                              and print watchlist entries to paste
    zoo_drift.py --integrity  local blob hashes against upstream, the second half
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
WATCHLIST = HERE / "watchlist.toml"
STATE = HERE / "state.json"
API = "https://huggingface.co/api/models/"
# Where local model copies live. FLEET_MODEL_STORES matches the shared ops
# convention (fleet_config.py): a comma-separated list of candidate paths. The
# default is the neutral example set, so a fresh clone scans nothing real and
# the discovery and integrity passes report that rather than guessing.
def _stores():
    spec = os.environ.get("FLEET_MODEL_STORES", "$HOME/models,~/storage/models")
    return [Path(p.strip()).expanduser() for p in spec.split(",") if p.strip()]


STORES = _stores()
UA = "model-card-drift/1.0 (model-card gate; read-only metadata)"

# The fields a change in which can change a casting decision. Everything else on
# a card is prose, and prose churn is not a finding.
DECISIVE = ["license", "base_model", "pipeline_tag"]


def get(url, etag=None):
    """Returns (status, json_or_none, etag). 304 means nothing changed."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    if etag:
        req.add_header("If-None-Match", etag)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read()), r.headers.get("ETag")
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return 304, None, etag
        return e.code, None, etag
    except Exception:
        return 0, None, etag


def local_meta(d: Path):
    """{filename: (commit, sha256)} as recorded by hf at download time."""
    out = {}
    for m in (d / ".cache/huggingface/download").glob("*.metadata"):
        try:
            lines = m.read_text().split("\n")
            out[m.name[: -len(".metadata")]] = (lines[0].strip(), lines[1].strip())
        except Exception:
            continue
    return out


def check_integrity(name, m, blobs, integrity, unchecked):
    """Question 2: does our local copy still match what upstream says it is?

    Reads the cached upstream blob map rather than a live response body, so a 304
    is checked exactly like a 200. That is sound rather than a shortcut: a 304
    means upstream has not moved, so the digests it last published ARE the
    current ones. Returns True only when a real comparison happened, because the
    caller reports coverage and an uncounted skip is the whole defect below.
    """
    if not blobs:
        unchecked.append((name, "no cached upstream blob map yet"))
        return False
    d = Path(m["path"])
    if not d.is_dir():
        unchecked.append((name, f"not on this node (`{d}`)"))
        return False
    meta = local_meta(d)
    if not meta:
        integrity.append((name, "(no download metadata)", "-", "CANNOT VERIFY"))
        return True
    present = set(blobs.get("present", []))
    digest = blobs.get("digest", {})
    for fn, (_, sha) in sorted(meta.items()):
        if fn not in present:
            integrity.append((name, fn, sha[:12], "ABSENT UPSTREAM"))
        elif fn in digest and digest[fn] and digest[fn] != sha:
            integrity.append((name, fn, sha[:12], digest[fn][:12]))
    return True


def local_dirs():
    for store in STORES:
        if store.is_dir():
            for d in sorted(store.iterdir()):
                if d.is_dir():
                    yield d


def discover():
    """Confirm a repo id rather than guessing it: search by slug, then require
    that a candidate's commit match the one recorded beside our own files."""
    print("# Discovered repo ids\n")
    print("Each line below is CONFIRMED: the candidate repo's current commit, or")
    print("one of its file hashes, matches what hf recorded when we pulled.\n")
    for d in local_dirs():
        meta = local_meta(d)
        if not meta:
            print(f"# {d.name}: no download metadata, cannot confirm")
            continue
        commits = {c for c, _ in meta.values()}
        hashes = {h for _, h in meta.values()}
        st, results, _ = get(
            f"https://huggingface.co/api/models?search={d.name}&limit=10")
        hit = None
        for cand in (results or []):
            rid = cand.get("id")
            st2, info, _ = get(f"{API}{rid}?blobs=true")
            if not info:
                continue
            if info.get("sha") in commits:
                hit = (rid, "commit match")
                break
            up = {s.get("lfs", {}).get("oid") for s in info.get("siblings", [])
                  if isinstance(s.get("lfs"), dict)}
            if up & hashes:
                hit = (rid, "blob hash match")
                break
        if hit:
            print(f'[model."{d.name}"]\nrepo = "{hit[0]}"  # confirmed by {hit[1]}\n'
                  f'path = "{d}"\n')
        else:
            print(f"# {d.name}: no candidate confirmed, declare by hand\n")
    return 0


def load():
    if not WATCHLIST.exists():
        return {}
    return tomllib.loads(WATCHLIST.read_text()).get("model", {})


def main():
    ap = argparse.ArgumentParser(description="model-card drift gate")
    ap.add_argument("--discover", action="store_true")
    ap.add_argument("--integrity", action="store_true")
    args = ap.parse_args()
    if args.discover:
        return discover()

    models = load()
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    out = ["# Zoo drift gate", ""]

    if not models:
        out += ["**GATE BLIND.** No `watchlist.toml`. Run `zoo_drift.py --discover` "
                "to derive confirmed repo ids from disk, then declare them.", ""]
        print("\n".join(out))
        return 0

    changed, quiet, unreachable, integrity, first = [], 0, [], [], 0
    unchecked, checked = [], 0
    # A repo can answer 200 with an unchanged body when the server rotates its
    # ETag. That is genuinely unchanged, but it is not a 304, and counting only
    # 304s left it in no bucket at all: observed 2026-08-03 as "14 unchanged, 15
    # repos watched" on a run whose neighbours both read 15. Nothing was missed,
    # yet the verdict stopped summing, and a verdict that does not close cannot
    # be told apart from one that lost a repo.
    revalidated = 0
    for name, m in sorted(models.items()):
        repo = m["repo"]
        prev = state.get(repo, {})
        # A 304 answers question 1 for free, but it carries no body, so this loop
        # used to answer question 2 by skipping it in silence. Integrity coverage
        # then tracked upstream ETag rotation rather than our own disk. Observed
        # 2026-08-05: two runs a minute apart, nothing touched between them, and
        # the second printed "None. Every comparable blob matches upstream"
        # having compared zero files, with a known e4b-ud mismatch sitting on
        # disk the whole time. Same silent-pass class as the oid/sha256 defect
        # fixed on 08-03, one layer out, and it survived that fix.
        # The repair: cache the blob map beside the ETag, so a 304 checks against
        # the digests upstream last published, which is precisely what a 304
        # asserts is still true. Costs no extra request. A repo with no cached
        # map predates this fix, so drop its ETag once and let the gate heal
        # itself on the next run.
        etag_req = prev.get("etag")
        if args.integrity and not prev.get("blobs"):
            etag_req = None
        st, info, etag = get(f"{API}{repo}?blobs=true", etag_req)
        if st == 304:
            quiet += 1
            if args.integrity:
                checked += check_integrity(name, m, prev.get("blobs"),
                                           integrity, unchecked)
            state[repo] = {**prev, "etag": etag}
            continue
        if not info:
            unreachable.append((name, repo, st))
            if args.integrity:
                unchecked.append((name, f"upstream unreachable, HTTP {st}"))
            continue

        card = info.get("cardData") or {}
        now = {
            "sha": info.get("sha"),
            "gated": info.get("gated", False),
            "disabled": info.get("disabled", False),
            "files": sorted(s["rfilename"] for s in info.get("siblings", [])),
            **{k: card.get(k) for k in DECISIVE},
        }
        if not prev.get("seen"):
            first += 1
        else:
            deltas = []
            for k in DECISIVE + ["gated", "disabled"]:
                if prev["seen"].get(k) != now[k]:
                    deltas.append(f"{k}: `{prev['seen'].get(k)}` to `{now[k]}`")
            added = set(now["files"]) - set(prev["seen"].get("files", []))
            gone = set(prev["seen"].get("files", [])) - set(now["files"])
            for f in sorted(added):
                deltas.append(f"file ADDED `{f}`")
            for f in sorted(gone):
                deltas.append(f"file REMOVED `{f}`, a pulled quant is usually a defect")
            if prev["seen"].get("sha") != now["sha"] and not deltas:
                deltas.append("commit moved, no decisive field changed (card text or "
                              "config; read the repo if it matters)")
            if deltas:
                changed.append((name, repo, deltas))
            else:
                revalidated += 1
        # The LFS block keys the digest "sha256". An earlier version of this read
        # "oid", got None for every file, and the truthiness guard then skipped
        # every comparison and printed "every hash matches upstream" having
        # compared nothing. A check that silently passes is worse than no check,
        # and it is the same silent-failure class this whole family of gates
        # exists to catch. Fixed 2026-08-03, on the first live run.
        # Three states, not two. Only LFS entries carry a content digest, so
        # small text files (config.json, README, .gitattributes) exist upstream
        # and are simply not comparable. Treating "no digest" as "absent" made
        # every one of them a false positive on the first run.
        sib = info.get("siblings", [])
        blobs = {
            "present": sorted(s["rfilename"] for s in sib),
            "digest": {s["rfilename"]: s["lfs"].get("sha256") or s["lfs"].get("oid")
                       for s in sib if isinstance(s.get("lfs"), dict)
                       and (s["lfs"].get("sha256") or s["lfs"].get("oid"))},
        }
        state[repo] = {"etag": etag, "seen": now, "blobs": blobs}

        if args.integrity:
            checked += check_integrity(name, m, blobs, integrity, unchecked)

    STATE.write_text(json.dumps(state, indent=1, sort_keys=True))

    accounted = len(changed) + quiet + revalidated + first + len(unreachable)
    out += [f"**Verdict: {len(changed)} changed, {quiet + revalidated} unchanged "
            f"({quiet} via 304, {revalidated} revalidated), {first} first seen, "
            f"{len(unreachable)} unreachable.** {len(models)} repos watched.", ""]
    if accounted != len(models):
        out += [f"**GATE ARITHMETIC BROKEN.** {accounted} of {len(models)} repos "
                "landed in a bucket. A repo fell out of every category, so this "
                "verdict is incomplete and must not be read as a clean bill of "
                "health. Fix the counting before trusting the line above.", ""]
    out += ["## Changed", ""]
    if changed:
        for name, repo, deltas in changed:
            out.append(f"- **{name}** (`{repo}`)")
            out.extend([f"  - {d}" for d in deltas])
    else:
        out.append("None. Every watched card is where we last saw it.")
    out.append("")
    if unreachable:
        out += ["## Unreachable, reported as unknown rather than unchanged", ""]
        out.extend([f"- **{n}** (`{r}`) HTTP {s}" for n, r, s in unreachable] + [""])
    if args.integrity:
        out += ["## Local integrity, our copy against upstream", ""]
        # Coverage is printed before any verdict, and deliberately. "None, every
        # comparable blob matches upstream" is indistinguishable from "I opened
        # nothing" unless the count sits beside it, which is exactly how the 304
        # defect hid. If a later change starts skipping repos again, this line
        # says so on the morning it happens instead of never.
        out += [f"**Coverage: {checked} of {len(models)} watched repos compared "
                f"against upstream blob hashes.**", ""]
        if unchecked:
            out += ["Not compared, and why. A gate reporting clean on repos it "
                    "never opened is the failure this section exists to prevent.",
                    ""]
            out.extend([f"- **{n}**: {why}" for n, why in unchecked] + [""])
        gloss = {
            "CANNOT VERIFY": "no hf download metadata beside these files, so the "
                             "local copy cannot be checked against upstream at all",
            "ABSENT UPSTREAM": "we hold a file the repo no longer publishes: renamed, "
                               "reorganized, or withdrawn",
        }
        out.extend([f"- **{n}** `{f}` " +
                    (gloss[b] if b in gloss
                     else f"local `{a}` upstream `{b}`. Our copy is not the file "
                          f"upstream now publishes under that name.")
                    for n, f, a, b in integrity]
                   or [f"None among the {checked} compared. Every comparable blob "
                       "matches upstream."])
        out.append("")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
