#!/usr/bin/env python3
"""Extraction bench: latency and self-consistency across the fabric, one seat at a time.

Written 2026-08-02. The routing law says fit is empirical and never inferred from
parameter count, and it names bounded extraction as the work the small fast seats win.
That claim has been measured once, in passing, on a job that was not designed to measure
it. This measures it deliberately, on the fabric's real extraction workload, with an
anchor set frozen so that every model ever benched answers the same questions.

WHAT IT MEASURES, and the second one is the point.

  latency          wall seconds per call, per seat, at a fixed prompt size. This is the
                   number the setlist needs to schedule a phase.
  self-consistency the same seat reading the same anchor TWICE at temperature 0, scored
                   by field-set Jaccard. The twin calibration on 2026-07-31 found a seat
                   overlapping its own extracted field list by 0.311 on a 20k-token
                   judgment prompt. Whether a SHORT bounded prompt holds together better
                   is the open question that decides how much of the campaign can be
                   trusted from one read. A fast seat that does not reproduce itself is
                   not a fast seat, it is a random number generator with good latency.

THE ANCHOR SET IS PINNED AND CARRIES NEGATIVES. Twelve captured broker documentation
pages, stratified by the grade a 120B seat assigned them at stage 4, including pages
graded 0 and 1 where there is nothing to extract. A bench with only rich pages measures
throughput; the empty pages are what catch a model that invents fields to fill a schema.
The grade is used for stratification only and is never shown to the seat.

PROMPT BUDGET IS SET BY THE SMALLEST SEAT, not the largest. Every llama.cpp seat on this
fabric runs one slot at 8192 tokens total, shared between prompt and generation. Anchors
are truncated to 6000 characters so a 4B familiar and a 120B twin answer an identical
prompt. Comparing seats on prompts only some of them can hold is not a comparison.

ONE CALL IN FLIGHT, ALWAYS. llama.cpp seats do not batch; concurrency there starves rather
than parallelises, and it cost this fabric 35 of 35 batches once already. The bench is
deliberately serial even against vLLM seats so the latency number means the same thing on
every row.

Usage:
  python3 extraction_bench.py anchors             build and freeze the anchor set
  python3 extraction_bench.py run <seat> [seat2]  bench one or more seats, in sequence
  python3 extraction_bench.py report              summarise every run on disk
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import sys
import time
import urllib.request
from collections import defaultdict

import bench_config as BC

HERE = os.path.dirname(os.path.abspath(__file__))
ANCHORS = os.path.join(HERE, "anchors", "field_dictionary_v1.json")
RUNS = str(BC.runs_dir())
URL = BC.env("BENCH_VIEW", "http://127.0.0.1:8088") + "/api/chat"

CAPTURES = os.path.expanduser(BC.env("BENCH_CAPTURES", "~/captures"))
JOIN = os.path.expanduser(BC.env("BENCH_JOIN", "~/captures/stage4_join.json"))

PAGE_CHARS = 6000
MAX_TOKENS = 1200
TEMPERATURE = 0.0
PASSES = 2
STRATA = {3: 4, 2: 4, 1: 2, 0: 2}     # grade -> how many anchors

PROMPT = """You are reading one page of a data vendor's public documentation.

List every DATA FIELD the vendor states it holds or provides about a person, a household,
or a property. Use the vendor's own wording for each field. Do not include marketing
claims, product names, company names, or section headings that are not fields. If the page
names no data fields at all, return an empty list.

Reply with JSON and nothing else, in exactly this form:
{"fields": ["field one", "field two"]}

THE PAGE:
---
%s
---
"""


class SeatError(RuntimeError):
    pass


# ------------------------------------------------------------------ anchors

def _page_text(path: str) -> str:
    """The captured page with its provenance header stripped.

    The header is our metadata, not the vendor's page, and feeding it to the seat would
    leak the link scorer's own opinion of the page into the thing being measured.
    """
    with open(path, encoding="utf-8", errors="replace") as fh:
        body = fh.read()
    lines = body.split("\n")
    i = 0
    while i < len(lines) and (lines[i].startswith("#") or not lines[i].strip()):
        i += 1
    return "\n".join(lines[i:]).strip()


def cmd_anchors():
    with open(JOIN, encoding="utf-8") as fh:
        recs = json.load(fh)
    by_grade = defaultdict(list)
    for r in recs:
        try:
            by_grade[int(r["dictionary_grade"])].append(r)
        except (KeyError, TypeError, ValueError):
            continue

    picked = []
    for grade, want in sorted(STRATA.items(), reverse=True):
        # Deterministic selection: sort by registration id and take from the front, so
        # rebuilding the anchor set on another machine produces the same twelve pages.
        pool = sorted(by_grade.get(grade, []), key=lambda r: str(r["reg"]))
        taken = 0
        for r in pool:
            reg = str(r["reg"])
            rp = os.path.join(CAPTURES, reg, "RECEIPT.json")
            if not os.path.exists(rp):
                continue
            with open(rp) as fh:
                rec = json.load(fh)
            ok = [p for p in rec.get("pages", []) if p.get("verdict") == "ok"]
            if not ok:
                continue
            ok.sort(key=lambda p: (-p.get("dict_score", 0), -p.get("chars", 0)))
            best = ok[0]
            fp = os.path.join(CAPTURES, reg, best["file"])
            if not os.path.exists(fp):
                continue
            text = _page_text(fp)[:PAGE_CHARS]
            if len(text) < 400:
                continue
            picked.append({
                "id": f"g{grade}-{taken+1:02d}",
                "reg": reg,
                "legal_name": rec.get("name", ""),
                "url": best.get("url", ""),
                "grade_hint": grade,
                "chars": len(text),
                "text": text,
            })
            taken += 1
            if taken >= want:
                break
        if taken < want:
            print(f"  WARNING grade {grade}: wanted {want}, found {taken}")

    payload = {
        "version": "field_dictionary_v1",
        "built": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "page_chars": PAGE_CHARS,
        "strata": {str(k): v for k, v in STRATA.items()},
        "note": ("Twelve captured broker documentation pages, stratified by the stage 4 "
                 "grade, truncated to a budget the smallest llama.cpp seat can hold. "
                 "grade_hint is for stratification and analysis only and is never sent "
                 "to a seat. Pages graded 0 and 1 are negative controls."),
        "anchors": picked,
    }
    os.makedirs(os.path.dirname(ANCHORS), exist_ok=True)
    blob = json.dumps(payload, ensure_ascii=False, indent=1)
    with open(ANCHORS, "w", encoding="utf-8") as fh:
        fh.write(blob)
    digest = hashlib.sha256(blob.encode()).hexdigest()
    print(f"froze {len(picked)} anchors to {ANCHORS}")
    print(f"  sha256 {digest}")
    for a in picked:
        print(f"  {a['id']}  grade {a['grade_hint']}  {a['chars']:>5} chars  "
              f"{a['legal_name'][:40]}")


def load_anchors():
    with open(ANCHORS, encoding="utf-8") as fh:
        blob = fh.read()
    return json.loads(blob), hashlib.sha256(blob.encode()).hexdigest()


# ------------------------------------------------------------------ the wire

def ask(seat, content, timeout=600):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    body = json.dumps({"seat": seat,
                       "messages": [{"role": "user", "content": content}],
                       "max_tokens": MAX_TOKENS,
                       "temperature": TEMPERATURE,
                       "tools": False}).encode()
    req = urllib.request.Request(URL, data=body,
                                 headers={"Content-Type": "application/json"})
    parts, err, first = [], None, None
    with urllib.request.urlopen(req, context=ctx, timeout=timeout) as r:
        event = None
        for raw in r:
            line = raw.decode(errors="replace").strip()
            if line.startswith("event:"):
                event = line[6:].strip()
                continue
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            try:
                d = json.loads(payload)
            except Exception:
                continue
            if event == "error" or (isinstance(d, dict) and "message" in d
                                    and "text" not in d):
                err = d.get("message") if isinstance(d, dict) else payload
                continue
            if isinstance(d, dict) and "text" in d:
                if first is None:
                    first = time.time()
                parts.append(d["text"])
    out = "".join(parts)
    if err and not out:
        raise SeatError(err)
    if not out:
        raise SeatError("empty generation, no error reported")
    return out, first


def extract_fields(text):
    """The LAST balanced JSON object in the reply, then its `fields` list.

    Last rather than first, copied from stage4 deliberately: a reasoning seat writes the
    schema back to itself while thinking, and the first balanced object is that echo.
    """
    best = None
    for m in re.finditer(r"\{", text):
        depth, i = 0, m.start()
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[m.start():i + 1])
                    except Exception:
                        break
                    if isinstance(obj, dict) and "fields" in obj:
                        best = obj
                    break
            i += 1
    if not isinstance(best, dict):
        return None
    f = best.get("fields")
    if not isinstance(f, list):
        return None
    return [str(x).strip().lower() for x in f if str(x).strip()]


# ------------------------------------------------------------------ the run

def cmd_run(seats):
    payload, digest = load_anchors()
    anchors = payload["anchors"]
    os.makedirs(RUNS, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    for seat in seats:
        out_path = os.path.join(RUNS, f"{stamp}_{seat}.jsonl")
        print(f"\n=== {seat}: {len(anchors)} anchors x {PASSES} passes, "
              f"temp {TEMPERATURE}, one call in flight")
        rows = []
        for a in anchors:
            for p in range(1, PASSES + 1):
                t0 = time.time()
                rec = {"seat": seat, "anchor": a["id"], "pass": p,
                       "grade_hint": a["grade_hint"], "prompt_chars": a["chars"],
                       "anchor_set": payload["version"], "anchor_sha256": digest}
                try:
                    text, first = ask(seat, PROMPT % a["text"])
                    dt = time.time() - t0
                    fields = extract_fields(text)
                    rec.update(seconds=round(dt, 2),
                               ttft_s=round(first - t0, 2) if first else None,
                               out_chars=len(text),
                               parse_ok=fields is not None,
                               n_fields=len(fields) if fields is not None else None,
                               fields=fields)
                    flag = "ok " if fields is not None else "PARSE-FAIL"
                    n = len(fields) if fields is not None else 0
                    print(f"  {a['id']} p{p}  {dt:6.1f}s  {flag} {n:>3} fields")
                except Exception as e:
                    rec.update(seconds=round(time.time() - t0, 2), error=f"{type(e).__name__}: {e}")
                    print(f"  {a['id']} p{p}  ERROR {type(e).__name__}: {str(e)[:70]}")
                rows.append(rec)
                with open(out_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        summarise([(seat, rows)])
        print(f"  -> {out_path}")


def jaccard(a, b):
    sa, sb = set(a or []), set(b or [])
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def summarise(groups):
    print(f"\n{'seat':22s} {'n':>4} {'med s':>7} {'p90 s':>7} {'parse':>6} "
          f"{'self-J':>7} {'fields':>7} {'ghost':>6}")
    for seat, rows in groups:
        done = [r for r in rows if "error" not in r]
        if not done:
            print(f"{seat:22s}  all calls errored")
            continue
        secs = sorted(r["seconds"] for r in done)
        med = secs[len(secs) // 2]
        p90 = secs[min(len(secs) - 1, int(0.9 * len(secs)))]
        parse = 100 * sum(1 for r in done if r.get("parse_ok")) / len(done)
        byanchor = defaultdict(dict)
        for r in done:
            if r.get("parse_ok"):
                byanchor[r["anchor"]][r["pass"]] = r["fields"]
        js = [jaccard(v.get(1), v.get(2)) for v in byanchor.values() if len(v) == 2]
        selfj = sum(js) / len(js) if js else float("nan")
        nf = [r["n_fields"] for r in done if r.get("parse_ok")]
        # ghost rate: fields invented on pages a 120B seat graded as having none.
        neg = [r for r in done if r.get("parse_ok") and r["grade_hint"] <= 1]
        ghost = 100 * sum(1 for r in neg if r["n_fields"] > 0) / len(neg) if neg else float("nan")
        print(f"{seat:22s} {len(done):>4} {med:>7.1f} {p90:>7.1f} {parse:>5.0f}% "
              f"{selfj:>7.2f} {sum(nf)/len(nf) if nf else 0:>7.1f} {ghost:>5.0f}%")


def cmd_report():
    groups = defaultdict(list)
    if not os.path.isdir(RUNS):
        raise SystemExit("no runs yet")
    for fn in sorted(os.listdir(RUNS)):
        if not fn.endswith(".jsonl"):
            continue
        for ln in open(os.path.join(RUNS, fn), encoding="utf-8"):
            try:
                r = json.loads(ln)
            except Exception:
                continue
            groups[r["seat"]].append(r)
    summarise(sorted(groups.items()))
    print("\nself-J is the mean field-set Jaccard between two reads of the same anchor "
          "at temperature 0.\nghost is the share of reads on grade 0 and 1 pages that "
          "returned any field at all.")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "report"
    if mode == "anchors":
        cmd_anchors()
    elif mode == "run":
        if len(sys.argv) < 3:
            raise SystemExit("run needs at least one seat key")
        cmd_run(sys.argv[2:])
    else:
        cmd_report()
