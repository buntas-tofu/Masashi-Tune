#!/usr/bin/env python3
"""Setlist: phased model rotation over one fixed workload.

Named by the operator. The industry terms are model multiplexing (time-division
sharing of one GPU by swapping weights on a schedule) and, in the evaluation
framing, a model sweep. Setlist is the better name and it is the one used here.

WHY THIS IS NOT A PARALLEL SPLIT. A parallel split spreads a shared queue
across seats: different items go to different readers, which is
throughput mode. That is the exact shape that produced a stage 3
false signal, where 19 of the top 25 records came from one arm of a 50/50 split
at p = 0.007 and the effect turned out to be mostly instrument. A setlist is the
opposite: ONE fixed record set, EVERY model, ONE AT A TIME. Comparable by
construction, because the only thing that varies between phases is the weights.

That makes this the calibration harness the routing law requires. The law says a
stage may be split across seats for throughput only after a shared anchor set
runs through both and the offset is measured and recorded: no harness, no split.
This produces that artifact for whatever models the setlist names.

DESIGN RULES, and most are inherited from instruments that earned them.

1. Never disturb a live seat. Phases run on their own llama-server, on a GPU the
   fabric is not using, bound to loopback on a bench port. Nothing is registered
   in the roster, so no view restart is needed and no seat is bounced. A bench
   server is deliberately not reachable off-node so it can never be mistaken for
   a seat.
2. One call in flight, always. llama.cpp serves one slot on a context shared
   between prompt and generation; concurrency there starves rather than
   parallelises and cost this fabric 35 of 35 batches once already. Serial is
   also what makes the latency number mean the same thing in every phase.
3. Temperature 0 on every scored call. A vessel's sampler is a conversation
   setting and was never chosen as a measurement setting. Note that even at
   temperature 0 long generations are not bit-identical run to run, because
   batched floating-point reductions are not associative, so self-consistency is
   measured rather than assumed.
4. Deadlines, not hopes. Every phase carries a wall-clock deadline and the run
   carries a global one. A phase that runs out of time stops and records how far
   it got. An unattended run that overruns its window is a failed run even if
   the numbers are good.
5. Loud when blind. A phase whose server never becomes ready, or which dies
   mid-flight, is recorded as an incomplete phase with its reason. It is never
   silently dropped, and its partial rows are kept and marked.
6. Resumable. Rows are keyed by (phase, record, pass) and appended as they land,
   so a re-run skips finished work rather than repeating it.

Usage:
  setlist.py sample                    freeze the record sample
  setlist.py run [--until HH:MM]       run every phase in the setlist
  setlist.py report                    summarise what is on disk

Floor: DMF. No em dashes, no ellipses.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import bench_config as BC

HERE = Path(__file__).resolve().parent
SAMPLE = HERE / "anchors" / "operations_content_v1.json"
RUNS = HERE / "runs"
MODELS = BC.models_dir()
LLAMA = BC.llama_server()
CORPUS = Path(BC.env("BENCH_CORPUS", str(HERE / "anchors" / "operations_corpus.jsonl")))

# Device 0 is the RTX 5090, 32G, which the fabric does not use: the live
# seats are pinned to CUDA_VISIBLE_DEVICES=1, the 4090. Running here means they
# keep serving untouched through every phase.
BENCH_GPU = BC.env("BENCH_GPU", "0")
BENCH_PORT = 8090
BENCH_HOST = "127.0.0.1"

CTX = 8192          # match the fleet's llama.cpp seats so results transfer
# The schema is tiny, so 400 looked generous. It is not: Gemma reasons before it
# answers, and on the first smoke test 400 completion tokens produced an EMPTY
# content field with finish_reason "length", because the whole budget went to
# reasoning that never closed. This is the same max_tokens trap the judgment
# harness hit on /api/chat. Budget for the thinking, not for the answer.
MAX_TOKENS = 1500
TEMPERATURE = 0.0
PASSES = 2          # same record twice, same phase, for self-consistency
N_RECORDS = 120
HEAD_CHARS = 4000

# The 2x2. Two vessel families, each with the build we pulled on the 2026-08-03
# zoo sweep and the build it replaced. The E4B pair is the open question; the 26B pair is the companion that says whether any effect is
# specific to E4B or general to the republish.
SETLIST = [
    {"phase": "e4b-corrected",
     "dir": "gemma-4-e4b-qat-gguf",
     "gguf": "gemma-4-E4B_q4_0-it.gguf",
     "note": "the current QAT build, commit 4b4a2c1d"},
    {"phase": "e4b-stale",
     "dir": "gemma-4-e4b-qat-gguf.pre-4b4a2c1d",
     "gguf": "gemma-4-E4B_q4_0-it.gguf",
     "note": "the build other deployments still run"},
    {"phase": "g26b-corrected",
     "dir": "gemma-4-26B-A4B",
     "gguf": "gemma-4-26B-A4B-it-UD-Q4_K_M.gguf",
     "note": "the resident 26B build as flipped 2026-08-03, commit c099eb48"},
    {"phase": "g26b-stale",
     "dir": "gemma-4-26B-A4B.pre-c099eb48",
     "gguf": "gemma-4-26B-A4B-it-UD-Q4_K_M.gguf",
     "note": "the stale copy the model-store gate caught"},
    # The arm the 2026-08-02 casting amendment said was owed. It reads: "serve
    # the UD build on one QAT node and re-run the frozen anchor set. Same
    # instrument, same anchors, one variable. Without that, the swap is a strong
    # inference rather than a measurement." The amendment's case is that the QAT
    # quant produces garbled output and stray <unused24> tokens, a pathology now
    # sighted three independent ways: the amendment itself, unsloth discussion
    # #2 at 36 comments, and llama.cpp #26239 on gfx1151.
    {"phase": "e4b-ud",
     "dir": "gemma-4-e4b-ud",
     "gguf": "gemma-4-E4B-it-UD-Q4_K_XL.gguf",
     "note": "the UD-Q4_K_XL candidate the casting amendment names as the fix"},
    # Rung 7, the mini audition's first candidate (operator ruling 2026-08-04
    # evening, the synapse restoration): if the Littles' role is bounded
    # tagging, the original design said E2 class might carry it. UD not QAT,
    # by the same day's swap lesson. Verdict informs the embed-split execution.
    {"phase": "e2b-ud",
     "dir": "gemma-4-e2b-ud",
     "gguf": "gemma-4-E2B-it-UD-Q4_K_XL.gguf",
     "note": "unsloth E2B UD at commit 0314792d, the downsizing question"},
]

DICTIONARY_PROMPT = """You are reading one page of a data vendor's public documentation.

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

PROMPT = """You are reading the opening text of one document from a document archive.

Reply with JSON and nothing else, in exactly this form:
{"record_type": "...", "program": "...", "dates": ["..."]}

record_type: what kind of document this is, in two or three words. For example
"memorandum of understanding", "statement of work", "meeting minutes". Use the
string "unknown" if the text does not say.
program: the program, survey, system or office the document concerns, in
the document's own wording. Use the string "unknown" if the text does not name one.
dates: every date the text asserts, copied exactly as written. Use an empty list
if the text states none.

THE DOCUMENT:
---
%s
---
"""


# Tasks the setlist can run. The point of naming more than one is that the first
# result (a 4B beating a 26B) was measured on ONE task shape, and a routing rule
# derived from a single task is exactly the over-generalisation the 26B arm just
# caught the E4B arm making. `operations` is bounded schema-fill on 200
# characters. `dictionary` is open-ended list extraction from 6,000-character
# pages, which is the real extraction task and the one carrying the 67
# percent parse rate that is still open on the board.
TASKS = {
    "operations": {
        "sample": SAMPLE,
        "prompt": None,          # bound below, after PROMPT is defined
        "id_key": "relpath",
        "text_key": "head",
        "shape": "dict",
        "max_tokens": 1500,
    },
    "dictionary": {
        "sample": HERE / "anchors" / "dictionary_sample_v2.json",
        "prompt": None,
        "id_key": "id",
        "text_key": "text",
        "shape": "list",
        # A rich page can name dozens of fields, and this model reasons before
        # it answers. 1500 is the operations budget and would truncate here,
        # which would be scored as a parse failure and read as a model defect.
        # Same lesson as the 400-token empty content on the first smoke test.
        # Raised 3000 to 6000 on 2026-08-04. The 26B produced 11,587 characters
        # of reasoning on a field-rich page and hit the ceiling before answering,
        # which scored as a parse failure and would have been read as a model
        # defect. 6000 is near the practical maximum: CTX is 8192 shared between
        # prompt and generation, and a 6000-char page is roughly 1500 tokens in.
        "max_tokens": 6000,
    },
}

TASKS["operations"]["prompt"] = PROMPT
TASKS["dictionary"]["prompt"] = DICTIONARY_PROMPT


def now() -> dt.datetime:
    return dt.datetime.now()


def stamp() -> str:
    return now().strftime("%Y%m%dT%H%M%S")


# ---------------------------------------------------------------- the sample

def cmd_sample() -> int:
    """Freeze a deterministic, stratified record sample.

    Deterministic by hash of relpath rather than by a random seed, so the same
    sample falls out on any node and in any interpreter. Stratified on whether
    the record asserts dates, because a set with only rich records measures
    throughput: the empty ones are what catch a model inventing fields to fill
    a schema, which is the same reason the extraction bench keeps grade 0 pages.
    """
    if not CORPUS.exists():
        print(f"corpus missing: {CORPUS}")
        return 1
    with_dates, without = [], []
    for line in CORPUS.open():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        head = (r.get("head") or "").strip()
        if len(head) < 80:
            continue          # too little text to ask anything of
        (with_dates if r.get("dates_seen") else without).append({
            "relpath": r["relpath"],
            "head": head[:HEAD_CHARS],
            "dates_seen": r.get("dates_seen", []),
            "series": r.get("series", []),
        })

    def rank(rec):
        return hashlib.sha256(rec["relpath"].encode()).hexdigest()

    with_dates.sort(key=rank)
    without.sort(key=rank)
    half = N_RECORDS // 2
    picked = with_dates[:half] + without[:N_RECORDS - half]
    picked.sort(key=rank)

    blob = json.dumps({"records": picked}, sort_keys=True)
    payload = {
        "built_at": now().isoformat(timespec="seconds"),
        "corpus": str(CORPUS),
        "corpus_lines": sum(1 for _ in CORPUS.open()),
        "n": len(picked),
        "with_dates": sum(1 for r in picked if r["dates_seen"]),
        "without_dates": sum(1 for r in picked if not r["dates_seen"]),
        "head_chars": HEAD_CHARS,
        "digest": hashlib.sha256(blob.encode()).hexdigest(),
        "records": picked,
    }
    SAMPLE.parent.mkdir(parents=True, exist_ok=True)
    SAMPLE.write_text(json.dumps(payload, indent=1))
    print(f"froze {len(picked)} records to {SAMPLE}")
    print(f"  {payload['with_dates']} assert dates, {payload['without_dates']} do not")
    print(f"  digest {payload['digest'][:16]}")
    return 0


def load_sample(task="operations"):
    """Records and a digest for a task, normalised to (id, text) pairs.

    Each task keeps its own frozen anchor file in its own native shape, so this
    adapts rather than rewriting them: the extraction set is the one the
    extraction bench already froze and its numbers have to stay comparable.
    """
    spec = TASKS[task]
    path = spec["sample"]
    if not path.exists():
        raise SystemExit(f"no sample for task {task} at {path}")
    p = json.loads(path.read_text())
    raw = p.get("records") or p.get("anchors") or []
    recs = [{"id": str(r[spec["id_key"]]), "text": r[spec["text_key"]], "_raw": r}
            for r in raw]
    digest = p.get("digest") or hashlib.sha256(
        json.dumps(raw, sort_keys=True).encode()).hexdigest()
    return recs, digest


# ---------------------------------------------------------------- the server

def gpu_of_pid(pid: int):
    """Which physical GPU index a process actually landed on, per nvidia-smi.

    Asserted rather than assumed, because the environment variable that was
    supposed to guarantee it is exactly what failed once. Returns None when the
    answer cannot be determined, which the caller must treat as unknown and not
    as correct.
    """
    try:
        uuid_of_index = {}
        r = subprocess.run(["nvidia-smi", "--query-gpu=index,uuid",
                            "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=30)
        for line in r.stdout.strip().splitlines():
            idx, uuid = (x.strip() for x in line.split(",", 1))
            uuid_of_index[uuid] = idx
        r = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,gpu_uuid",
                            "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=30)
        for line in r.stdout.strip().splitlines():
            p, uuid = (x.strip() for x in line.split(",", 1))
            if p == str(pid):
                return uuid_of_index.get(uuid)
    except Exception:
        return None
    return None


def server_up(timeout=2) -> bool:
    try:
        with urllib.request.urlopen(
                f"http://{BENCH_HOST}:{BENCH_PORT}/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def start_server(model: Path, log: Path):
    """Launch the bench server on the idle GPU. Returns (proc, load_seconds).

    load_seconds is a real measurement and it is the number the setlist needs to
    schedule a phase: a 15.8G vessel does not cost what a 4.8G one costs, and
    the swap is part of the phase whether or not anyone times it.
    """
    env = dict(os.environ)
    # CUDA_DEVICE_ORDER is NOT optional here and leaving it out cost a false
    # start on 2026-08-03. nvidia-smi always enumerates by PCI bus, but CUDA
    # defaults to FASTEST_FIRST, so "device 0" meant the 4090 to this process
    # and the 5090 to the human reading nvidia-smi. The bench server loaded onto
    # the same card as the live seats, which is the one thing the phase design
    # exists to prevent. Every fabric seat unit already sets this; the bench did
    # not, and an index is meaningless without the ordering that defines it.
    env["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
    env["CUDA_VISIBLE_DEVICES"] = BENCH_GPU
    env["LD_LIBRARY_PATH"] = str(LLAMA.parent) + (
        ":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    cmd = [
        str(LLAMA), "-m", str(model),
        "--host", BENCH_HOST, "--port", str(BENCH_PORT),
        "-ngl", "99", "-c", str(CTX),
        # --reasoning-format deepseek is what serve_familiar.sh passes on every
        # familiar. Without it a reasoning model's thinking lands in content and
        # the answer never separates out. Matching the serve script is also what
        # makes these numbers say anything about how the seats actually behave.
        "--jinja", "--reasoning-format", "deepseek",
        "--metrics", "--threads", "8",
    ]
    t0 = time.time()
    fh = log.open("wb")
    proc = subprocess.Popen(cmd, env=env, stdout=fh, stderr=subprocess.STDOUT,
                            start_new_session=True)
    # Give a big vessel room to page in from disk, but never hang forever.
    while time.time() - t0 < 900:
        if proc.poll() is not None:
            return None, time.time() - t0
        if server_up():
            return proc, time.time() - t0
        time.sleep(2)
    stop_server(proc)
    return None, time.time() - t0


def stop_server(proc) -> float:
    if proc is None:
        return 0.0
    t0 = time.time()
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass
    try:
        proc.wait(timeout=90)
    except Exception:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            pass
    # The port must actually be free before the next phase binds it.
    while time.time() - t0 < 60 and server_up(timeout=1):
        time.sleep(1)
    return time.time() - t0


def ask(content: str, timeout=300, max_tokens=None):
    body = json.dumps({
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens or MAX_TOKENS,
        "temperature": TEMPERATURE,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        f"http://{BENCH_HOST}:{BENCH_PORT}/v1/chat/completions",
        data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode(errors="replace"))
    ch = (d.get("choices") or [{}])[0]
    msg = ch.get("message", {}) or {}
    text = msg.get("content") or ""
    usage = d.get("usage") or {}
    # finish_reason and the reasoning length are recorded rather than discarded:
    # an empty content field with finish "length" is a budget failure, not a
    # model that had nothing to say, and the two must never look alike on disk.
    usage = dict(usage, finish_reason=ch.get("finish_reason"),
                 reasoning_chars=len(msg.get("reasoning_content") or ""))
    return text, time.time() - t0, usage


# ---------------------------------------------------------------- scoring

def parse_reply(text: str):
    """The model's JSON, or None. Tolerant of a fenced or padded reply."""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("```")[1] if len(s.split("```")) > 1 else s
        s = s[4:] if s.lower().startswith("json") else s
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        d = json.loads(s[a:b + 1])
    except Exception:
        return None
    return d if isinstance(d, dict) else None


def norm_fields(d, shape="dict"):
    """A comparable shape, so two passes can be scored against each other."""
    if shape == "list":
        # The dictionary task returns {"fields": [...]}. Compared as a SET,
        # because the routing law is explicit that agreement is field-level and
        # never exact-match: one extra item should not make a record "differ"
        # while it stays substantially the same.
        if not isinstance(d, dict):
            return None
        f = d.get("fields")
        if not isinstance(f, list):
            return None
        return sorted({str(x).strip().lower() for x in f if str(x).strip()})
    if not isinstance(d, dict):
        return None
    def s(x):
        return (x or "").strip().lower() if isinstance(x, str) else ""
    dates = d.get("dates")
    dates = [str(x).strip() for x in dates] if isinstance(dates, list) else []
    return {"record_type": s(d.get("record_type")),
            "program": s(d.get("program")),
            "dates": sorted(set(dates))}


# ---------------------------------------------------------------- the run

def done_keys(path: Path):
    seen = set()
    if path.exists():
        for line in path.open():
            try:
                seen.add(json.loads(line)["_key"])
            except Exception:
                continue
    return seen


def run_phase(spec, records, sink: Path, deadline: dt.datetime, logdir: Path,
              task="operations"):
    model = MODELS / spec["dir"] / spec["gguf"]
    tspec = TASKS[task]
    result = {"phase": spec["phase"], "model": str(model), "note": spec["note"],
              "task": task}
    if not model.exists():
        result.update(status="MISSING", reason=f"no model at {model}")
        return result

    log = logdir / f"{spec['phase']}_server.log"
    print(f"\n=== phase {spec['phase']}: loading {model.name} "
          f"({model.stat().st_size / 2**30:.1f}G)", flush=True)
    proc, load_s = start_server(model, log)
    if proc is None:
        result.update(status="NO_START", load_s=round(load_s, 1),
                      reason=f"server never became ready, see {log}")
        print(f"  FAILED to start after {load_s:.0f}s, see {log}", flush=True)
        return result
    landed = gpu_of_pid(proc.pid)
    result["gpu_landed"] = landed
    if landed is not None and landed != BENCH_GPU:
        # Refuse rather than measure. A phase on the seats' own card is not a
        # slower version of this experiment, it is a different one, and it would
        # also corrupt the sustained phase it is supposed to stay clear of.
        stop_server(proc)
        result.update(status="WRONG_GPU", load_s=round(load_s, 1),
                      reason=f"server landed on GPU {landed}, expected {BENCH_GPU}")
        print(f"  ABORT: landed on GPU {landed}, expected {BENCH_GPU}", flush=True)
        return result
    print(f"  ready in {load_s:.0f}s on GPU {landed if landed is not None else '?'}",
          flush=True)

    seen = done_keys(sink)
    n_ok = n_err = n_skip = 0
    lat = []
    try:
        with sink.open("a") as out:
            for rec in records:
                for p in range(PASSES):
                    key = f"{spec['phase']}|{task}|{rec['id']}|{p}"
                    if key in seen:
                        n_skip += 1
                        continue
                    if now() >= deadline:
                        result["truncated_at"] = key
                        raise TimeoutError("phase deadline")
                    row = {"_key": key, "phase": spec["phase"], "task": task,
                           "relpath": rec["id"], "pass": p}
                    try:
                        text, secs, usage = ask(tspec["prompt"] % rec["text"],
                                                max_tokens=tspec.get("max_tokens"))
                        d = parse_reply(text)
                        row.update(secs=round(secs, 2), ok=True,
                                   parsed=d is not None,
                                   fields=norm_fields(d, tspec["shape"]),
                                   raw=None if d is not None else text[:600],
                                   usage=usage)
                        lat.append(secs)
                        n_ok += 1
                    except Exception as e:
                        row.update(ok=False, error=f"{type(e).__name__}: {e}"[:300])
                        n_err += 1
                    out.write(json.dumps(row) + "\n")
                    out.flush()
                    if (n_ok + n_err) % 20 == 0:
                        print(f"  {n_ok + n_err}/{len(records) * PASSES} "
                              f"ok={n_ok} err={n_err}", flush=True)
    except TimeoutError:
        result["status"] = "DEADLINE"
        print(f"  hit deadline, stopping this phase", flush=True)
    else:
        result["status"] = "COMPLETE"
    finally:
        unload_s = stop_server(proc)

    lat.sort()
    result.update(load_s=round(load_s, 1), unload_s=round(unload_s, 1),
                  calls=n_ok + n_err, ok=n_ok, errors=n_err, skipped=n_skip,
                  median_s=round(lat[len(lat) // 2], 2) if lat else None)
    print(f"  phase {spec['phase']}: {result['status']} "
          f"ok={n_ok} err={n_err} median={result['median_s']}s", flush=True)
    return result


def cmd_run(until: str | None, task: str = "operations",
            phases: str | None = None) -> int:
    records, digest = load_sample(task)
    RUNS.mkdir(parents=True, exist_ok=True)
    tag = stamp()
    logdir = RUNS / f"setlist_{tag}_{task}"
    logdir.mkdir(parents=True, exist_ok=True)
    sink = RUNS / f"setlist_{tag}_{task}.jsonl"

    if until:
        hh, mm = (int(x) for x in until.split(":"))
        end = now().replace(hour=hh, minute=mm, second=0, microsecond=0)
        if end <= now():
            end += dt.timedelta(days=1)
    else:
        end = now() + dt.timedelta(hours=3)

    start_iso = now().astimezone().isoformat(timespec="seconds")
    live = [s for s in SETLIST if (MODELS / s["dir"] / s["gguf"]).exists()]
    # A paired heat wants exactly its arms, not the whole setlist rerun: the
    # filter keeps the config as the record of every arm ever defined while a
    # run names the subset it is a measurement of.
    if phases:
        want = {p.strip() for p in phases.split(",") if p.strip()}
        unknown = want - {s["phase"] for s in SETLIST}
        if unknown:
            print(f"unknown phases: {', '.join(sorted(unknown))}")
            return 1
        live = [s for s in live if s["phase"] in want]
    print(f"setlist: {len(live)} of {len(SETLIST)} phases have their vessel on disk"
          + (f" (filtered to: {', '.join(s['phase'] for s in live)})" if phases else ""))
    print(f"sample {len(records)} records, digest {digest[:16]}")
    print(f"global deadline {end:%Y-%m-%d %H:%M}")
    if not live:
        print("nothing to run")
        return 1

    results = []
    for i, spec in enumerate(live):
        remaining = (end - now()).total_seconds()
        left = len(live) - i
        if remaining <= 60:
            results.append({"phase": spec["phase"], "status": "NOT_RUN",
                            "reason": "global deadline reached"})
            print(f"\n=== phase {spec['phase']}: SKIPPED, out of time", flush=True)
            continue
        # Share what is left evenly across the phases still to run, so an early
        # slow phase cannot eat the whole window and leave the rest unmeasured.
        share = min(remaining, remaining / left + 300)
        results.append(run_phase(spec, records,
                                 sink, now() + dt.timedelta(seconds=share),
                                 logdir, task))

    # Emit a run manifest into the telemetry runs lane. Done here rather than
    # by hand afterwards because the serving flags, the landing GPU and the
    # vessel fingerprints are knowable now and become archaeology later.
    try:
        sys.path.insert(0, str(HERE))
        import manifest as MF
        arms = []
        for spec, res in zip(live, results):
            arms.append({
                "arm": spec["phase"],
                "vessel": MF.vessel(MODELS / spec["dir"], spec["gguf"]),
                "serving_flags": ["-ngl 99", f"-c {CTX}", "--jinja",
                                  "--reasoning-format deepseek", "--metrics",
                                  "--threads 8"],
                "gpu_index": res.get("gpu_landed"),
                "status": res.get("status"),
                "load_s": res.get("load_s"),
                "result": MF.summarise_jsonl(sink).get(spec["phase"]),
            })
        MF.emit({
            "run_id": f"setlist_{tag}_{task}",
            "kind": "setlist",
            "instrument": MF.instrument(__file__),
            "node": subprocess.run(["hostname"], capture_output=True,
                                   text=True).stdout.strip(),
            "started": start_iso, "ended": MF.now_iso(),
            "hardware": MF.hardware(),
            "workload": {"task": task, "anchor_digest": digest,
                         "records": len(records), "passes": PASSES},
            "settings": {"temperature": TEMPERATURE,
                         "max_tokens": TASKS[task].get("max_tokens", MAX_TOKENS),
                         "ctx": CTX, "one_call_in_flight": True},
            "arms": arms,
            "raw": str(sink),
        })
        print("manifest emitted to the telemetry runs lane")
    except Exception as e:
        print(f"WARNING: manifest not emitted: {type(e).__name__}: {e}")

    summary = {"tag": tag, "task": task, "sample_digest": digest,
               "records": len(records),
               "passes": PASSES, "temperature": TEMPERATURE,
               "gpu": f"CUDA_VISIBLE_DEVICES={BENCH_GPU} (RTX 5090)",
               "finished_at": now().isoformat(timespec="seconds"),
               "phases": results}
    (RUNS / f"setlist_{tag}_{task}_summary.json").write_text(json.dumps(summary, indent=1))
    print(f"\nwrote {RUNS / f'setlist_{tag}_{task}_summary.json'}")
    return 0


# ---------------------------------------------------------------- report

def cmd_report() -> int:
    runs = sorted(RUNS.glob("setlist_*.jsonl"))
    if not runs:
        print("no setlist runs on disk")
        return 1
    latest = runs[-1]
    rows = []
    for line in latest.open():
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    by = {}
    for r in rows:
        by.setdefault(r["phase"], []).append(r)

    print(f"# Setlist report: {latest.name}\n")
    print("| phase | calls | ok | parse | self-consistent | median s |")
    print("|---|---:|---:|---:|---:|---:|")
    for phase, rs in by.items():
        ok = [r for r in rs if r.get("ok")]
        parsed = [r for r in ok if r.get("parsed")]
        pairs = {}
        for r in ok:
            pairs.setdefault(r["relpath"], {})[r["pass"]] = r.get("fields")
        both = [v for v in pairs.values() if 0 in v and 1 in v]
        same = sum(1 for v in both if v[0] == v[1] and v[0] is not None)
        lat = sorted(r["secs"] for r in ok if r.get("secs") is not None)
        print(f"| {phase} | {len(rs)} | {len(ok)} | "
              f"{100 * len(parsed) // max(len(ok), 1)}% | "
              f"{100 * same // max(len(both), 1)}% ({same}/{len(both)}) | "
              f"{lat[len(lat) // 2]:.2f} |" if lat else
              f"| {phase} | {len(rs)} | {len(ok)} | - | - | - |")
    print("\nself-consistent is the share of records where two passes at "
          "temperature 0 produced an identical normalised field set. It is a "
          "property of the instrument, not of the documents.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Setlist: phased model rotation.")
    ap.add_argument("mode", choices=["sample", "run", "report"])
    ap.add_argument("--until", help="global wall-clock deadline, HH:MM")
    ap.add_argument("--task", choices=sorted(TASKS), default="operations",
                    help="which workload the setlist runs")
    ap.add_argument("--phases", help="comma-separated subset of setlist "
                    "phases to run (default: every phase on disk)")
    a = ap.parse_args()
    if a.mode == "sample":
        return cmd_sample()
    if a.mode == "run":
        return cmd_run(a.until, a.task, a.phases)
    return cmd_report()


if __name__ == "__main__":
    raise SystemExit(main())
