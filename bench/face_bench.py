#!/usr/bin/env python3
"""face_bench.py: the face bench runner (docket 65, born 2026-08-07).

The performance comparison the operator wants before the final vessel call.
Field: gemma-4-26B-A4B (incumbent) against Nemotron-3-Nano-Omni NVFP4, with
gemma-4-31B dense benched alongside. Runs on the 5090, the ruled residence.

Law, per the routing law and the vessel dossier: one instrument one reader
(this runner IS the instrument; every anchor scores programmatically),
temperature 0, two reads minimum, field-level agreement published beside the
verdict. Speed lanes report cold and warm reads separately rather than an
agreement number, because both are real. Serving stacks differ by candidate
and are deployment reality, recorded in the manifest rather than hidden.

Scope envelope, stated beside the verdict per the corpus-bounds card: text
faculties and speed only. The tool lane is deferred to round 2 with the
operator's own persona re-test (docket 60). Vision is a plumbing smoke, not
a scored lane. Persona register beyond the countable laws is the operator's
own read; transcripts ride with the report.

Usage:
  face_bench.py run --endpoint http://127.0.0.1:8090 --candidate gemma-4-26b \
      --stack llamacpp [--model-dir DIR] [--gguf NAME] [--reads 2] [--speed] \
      [--vision-smoke IMAGE]
  face_bench.py report runs/face_bench_*.jsonl

Floor: DMF. No em dashes, no ellipses.
"""

from __future__ import annotations

import argparse
import base64
import glob as globmod
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANCHORS_DEFAULT = HERE / "anchors" / "face_v1.json"
RUNS_DIR = HERE / "runs"
PERSONA_DEFAULT = HERE / "anchors" / "persona_system.md"
PERSONA_PATH = Path(os.environ.get("FACE_PERSONA_PATH") or PERSONA_DEFAULT)
SPEED_SIZES = [1000, 8000, 20000]
SPEED_GEN = 256

sys.path.insert(0, str(HERE))
try:
    import manifest as manifest_mod
except Exception:
    manifest_mod = None


# ---------- persona and filler ----------

def persona_text() -> str:
    """The bundled generic persona prompt, frontmatter stripped if present."""
    raw = PERSONA_PATH.read_text()
    if raw.startswith("---"):
        end = raw.find("---", 3)
        raw = raw[end + 3:]
    return raw.strip()


LEDGER_SUBJECTS = ["the walk-in cooler", "tap line three", "the register drawer",
                   "the patio awning", "the ice machine", "the glass washer",
                   "the corner booth", "the jukebox amp", "the back stairwell",
                   "the delivery dock", "the neon transformer", "the mop sink"]
LEDGER_VERBS = ["was inspected", "was restocked", "was wiped down", "was flagged",
                "was signed off", "was recalibrated", "was inventoried",
                "was photographed", "was re-shimmed", "was descaled"]
LEDGER_TAILS = ["before the lunch rush", "after close", "during the vendor visit",
                "with no issues found", "pending a second look", "per the checklist",
                "by the opening shift", "under the standing order",
                "with the receipt filed", "ahead of the weekend"]


def filler(chars: int, seed: str) -> str:
    """Deterministic ledger prose. Seeded so both reads and every candidate
    receive byte-identical context."""
    rng = random.Random(seed)
    out = []
    n = 0
    day = 1
    while n < chars:
        s = ("Day %d: %s %s %s." % (
            day,
            rng.choice(LEDGER_SUBJECTS),
            rng.choice(LEDGER_VERBS),
            rng.choice(LEDGER_TAILS)))
        out.append(s)
        n += len(s) + 1
        day += 1
    return " ".join(out)


# ---------- client ----------

def chat(endpoint: str, messages: list, max_tokens: int, stack: str,
         stream: bool = False, timeout: int = 600, cache_prompt: bool | None = None):
    """POST /v1/chat/completions at temperature 0. Returns dict:
    {text, prompt_tokens, completion_tokens, ttft, gen_time, wall}."""
    body = {
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if stream:
        body["stream_options"] = {"include_usage": True}
    if cache_prompt is not None and stack == "llamacpp":
        body["cache_prompt"] = cache_prompt
    if stack == "vllm":
        body["chat_template_kwargs"] = {"enable_thinking": False}
    req = urllib.request.Request(
        endpoint.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    if not stream:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
        wall = time.monotonic() - t0
        usage = data.get("usage") or {}
        msg = (data.get("choices") or [{}])[0].get("message", {}) or {}
        text = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or ""
        return {"text": text, "reasoning_chars": len(reasoning),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "ttft": None, "gen_time": None, "wall": wall}
    text = []
    rlen = [0]
    ttft = None
    t_first = None
    t_last = None
    usage = {}
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if chunk.get("usage"):
                usage = chunk["usage"]
            for ch in chunk.get("choices") or []:
                d = ch.get("delta") or {}
                delta = d.get("content")
                rdelta = d.get("reasoning_content")
                if delta or rdelta:
                    now = time.monotonic()
                    if ttft is None:
                        ttft = now - t0
                        t_first = now
                    t_last = now
                if delta:
                    text.append(delta)
                if rdelta:
                    rlen[0] += len(rdelta)
    wall = time.monotonic() - t0
    gen_time = (t_last - t_first) if (t_first and t_last and t_last > t_first) else None
    return {"text": "".join(text), "reasoning_chars": rlen[0],
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "ttft": ttft, "gen_time": gen_time, "wall": wall}


# ---------- scoring ----------

def first_json(text: str):
    t = re.sub(r"```(?:json)?", "", text)
    start = t.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(t)):
        c = t[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(t[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def norm(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v).strip().lower().rstrip(".")


def get_path(obj, dotted):
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        hit = None
        for k in cur:
            if k.strip().lower() == part.lower():
                hit = cur[k]
                break
        if hit is None:
            return None
        cur = hit
    return cur


def sentences(text: str) -> list:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if re.search(r"\w", p)]


def score(anchor: dict, text: str) -> dict:
    if not text.strip():
        return {"pass": False, "fields": {"empty": "1"}, "reason": "empty reply"}
    spec = anchor["score"]
    kind = spec["type"]
    fields = {}
    ok = True
    reason = ""

    if kind in ("json_fields", "json_exact", "json_field_wordcount"):
        obj = first_json(text)
        if obj is None:
            return {"pass": False, "fields": {"parse": "fail"}, "reason": "no parseable JSON"}
        if kind == "json_field_wordcount":
            val = get_path(obj, spec["field"])
            words = len(re.findall(r"\S+", str(val or "")))
            fields[spec["field"] + ".words"] = str(words)
            if words != spec["count"]:
                ok = False
                reason = "wordcount %d wanted %d" % (words, spec["count"])
            for k, want in (spec.get("also") or {}).items():
                got = norm(get_path(obj, k))
                fields[k] = got
                if got != norm(want):
                    ok = False
        else:
            contains = set(spec.get("contains") or [])
            for k, want in spec["expect"].items():
                got_raw = get_path(obj, k)
                got = norm(got_raw) if got_raw is not None else ""
                fields[k] = got
                want_n = norm(want)
                hit = (want_n in got) if k in contains else (got == want_n)
                if not hit:
                    ok = False
                    reason = reason or ("%s got %r wanted %r" % (k, got, want_n))
            if kind == "json_exact":
                keys = sorted(k.strip().lower() for k in obj)
                fields["_keys"] = ",".join(keys)
                if keys != sorted(k.lower() for k in spec["exact_keys"]):
                    ok = False
                    reason = reason or ("extra or missing keys: %s" % fields["_keys"])

    elif kind == "regex":
        for i, pat in enumerate(spec.get("must") or []):
            hit = bool(re.search(pat, text))
            fields["must%d" % i] = str(hit).lower()
            if not hit:
                ok = False
                reason = reason or ("missing required /%s/" % pat)
        for i, pat in enumerate(spec.get("must_not") or []):
            hit = bool(re.search(pat, text))
            fields["not%d" % i] = str(hit).lower()
            if hit:
                ok = False
                reason = reason or ("forbidden /%s/ present" % pat)
        anys = spec.get("must_any") or []
        if anys:
            hit = any(re.search(p, text, re.IGNORECASE) for p in anys)
            fields["any"] = str(hit).lower()
            if not hit:
                ok = False
                reason = reason or "no must_any matched"

    elif kind == "sentences_end_with":
        sents = sentences(text)
        fields["n"] = str(len(sents))
        endings = []
        for s in sents:
            words = re.findall(r"[A-Za-z']+", s)
            endings.append(words[-1].lower() if words else "")
        fields["endings"] = ",".join(endings)
        if len(sents) != spec["count"] or any(e != spec["word"] for e in endings):
            ok = False
            reason = "sentences %s endings %s" % (fields["n"], fields["endings"])

    elif kind == "sentence_count":
        sents = sentences(text)
        fields["n"] = str(len(sents))
        ok = len(sents) == spec["count"]
        reason = "" if ok else ("got %d sentences" % len(sents))

    elif kind == "word_count":
        n = len(re.findall(r"\S+", text))
        fields["n"] = str(n)
        ok = spec["min"] <= n <= spec["max"]
        reason = "" if ok else ("%d words outside %d..%d" % (n, spec["min"], spec["max"]))

    elif kind == "numbered_list":
        lines = [l for l in text.strip().splitlines() if l.strip()]
        items = [re.match(r"\s*\d+[.)]\s+(.+?)\s*$", l) for l in lines]
        good = [m for m in items if m]
        fields["items"] = str(len(good))
        fields["stray"] = str(len(lines) - len(good))
        ok = (len(good) == spec["count"] and len(lines) == len(good) and
              all(len(re.findall(r"\S+", m.group(1))) <= spec["max_words_per_item"]
                  for m in good))
        reason = "" if ok else ("items %s stray %s" % (fields["items"], fields["stray"]))

    else:
        return {"pass": False, "fields": {}, "reason": "unknown scorer %s" % kind}

    return {"pass": ok, "fields": fields, "reason": reason}


# ---------- run ----------

def build_messages(anchor: dict) -> list:
    msgs = []
    if anchor.get("system") == "@persona":
        msgs.append({"role": "system", "content": persona_text()})
    user = anchor["user"]
    if "{FILLER}" in user:
        user = user.replace("{FILLER}", filler(anchor["filler_chars"], anchor["id"]))
    msgs.append({"role": "user", "content": user})
    return msgs


def cmd_run(args):
    anchors_path = Path(args.anchors)
    aset = json.loads(anchors_path.read_text())
    fams = set((args.families or "entity,instruction,persona").split(","))
    fam_map = {"ET": "entity", "IH": "instruction", "PH": "persona"}
    fams = {fam_map.get(f, f) for f in fams}
    anchors = [a for a in aset["anchors"] if a["family"] in fams]

    ts = time.strftime("%Y%m%dT%H%M%S")
    RUNS_DIR.mkdir(exist_ok=True)
    out_path = RUNS_DIR / ("face_bench_%s_%s.jsonl" % (args.candidate, ts))
    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    records = []

    print("face_bench run: %s at %s, %d anchors x %d reads, speed=%s" % (
        args.candidate, args.endpoint, len(anchors), args.reads, args.speed))

    with out_path.open("w") as out:
        for a in anchors:
            msgs = build_messages(a)
            for read in range(1, args.reads + 1):
                t0 = time.monotonic()
                try:
                    r = chat(args.endpoint, msgs, a["max_tokens"], args.stack)
                    sc = score(a, r["text"])
                    err = ""
                except Exception as e:
                    r = {"text": "", "prompt_tokens": None, "completion_tokens": None,
                         "wall": time.monotonic() - t0}
                    sc = {"pass": False, "fields": {"error": "1"}, "reason": str(e)[:200]}
                    err = str(e)[:200]
                rec = {"kind": "anchor", "candidate": args.candidate, "anchor": a["id"],
                       "family": a["family"], "read": read, "pass": sc["pass"],
                       "fields": sc["fields"], "reason": sc["reason"], "error": err,
                       "prompt_tokens": r.get("prompt_tokens"),
                       "completion_tokens": r.get("completion_tokens"),
                       "reasoning_chars": r.get("reasoning_chars"),
                       "wall": round(r.get("wall") or 0, 3), "text": r["text"]}
                out.write(json.dumps(rec) + "\n")
                records.append(rec)
                print("  %-6s read%d %s %s" % (
                    a["id"], read, "PASS" if sc["pass"] else "fail",
                    ("(%s)" % sc["reason"]) if sc["reason"] else ""))

        if args.speed:
            for size in SPEED_SIZES:
                body = filler(size * 4, "speed-%d" % size)
                msgs = [{"role": "user", "content":
                         body + "\n\nSummarize the ledger above in one sentence."}]
                for read, label in ((1, "cold"), (2, "warm")):
                    try:
                        r = chat(args.endpoint, msgs, SPEED_GEN, args.stack,
                                 stream=True, cache_prompt=(read == 1))
                        err = ""
                    except Exception as e:
                        r = {"prompt_tokens": None, "completion_tokens": None,
                             "ttft": None, "gen_time": None, "wall": None, "text": ""}
                        err = str(e)[:200]
                    ct = r.get("completion_tokens")
                    gt = r.get("gen_time")
                    tg = round((ct - 1) / gt, 2) if (ct and gt and ct > 1) else None
                    rec = {"kind": "speed", "candidate": args.candidate,
                           "target_tokens": size, "read": label,
                           "prompt_tokens": r.get("prompt_tokens"),
                           "completion_tokens": ct,
                           "ttft": round(r["ttft"], 3) if r.get("ttft") else None,
                           "tg_tok_s": tg,
                           "wall": round(r["wall"], 3) if r.get("wall") else None,
                           "error": err}
                    out.write(json.dumps(rec) + "\n")
                    records.append(rec)
                    print("  speed %5d %s: ttft=%s tg=%s pt=%s %s" % (
                        size, label, rec["ttft"], rec["tg_tok_s"],
                        rec["prompt_tokens"], err))

        if args.vision_smoke:
            img = Path(args.vision_smoke).read_bytes()
            uri = "data:image/png;base64," + base64.b64encode(img).decode()
            msgs = [{"role": "user", "content": [
                {"type": "text", "text": "In one short sentence, what is in this image?"},
                {"type": "image_url", "image_url": {"url": uri}}]}]
            try:
                r = chat(args.endpoint, msgs, 120, args.stack)
                low = r["text"].lower()
                alive = bool(r["text"].strip()) and not any(
                    p in low for p in ("cannot see", "can't see", "no image",
                                       "unable to view", "text-only"))
                err = ""
            except Exception as e:
                r = {"text": ""}
                alive = False
                err = str(e)[:200]
            rec = {"kind": "vision_smoke", "candidate": args.candidate,
                   "alive": alive, "text": r["text"], "error": err}
            out.write(json.dumps(rec) + "\n")
            records.append(rec)
            print("  vision smoke: %s" % ("ALIVE" if alive else "dead"))

    finished = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if manifest_mod is not None:
        man = {"schema": manifest_mod.SCHEMA, "kind": "face_bench",
               "candidate": args.candidate, "endpoint": args.endpoint,
               "stack": args.stack, "started": started, "finished": finished,
               "anchors_file": str(anchors_path),
               "anchors_sha256": hashlib.sha256(anchors_path.read_bytes()).hexdigest(),
               "reads": args.reads, "results": str(out_path),
               "instrument": manifest_mod.instrument(__file__),
               "hardware": manifest_mod.hardware()}
        if args.model_dir and args.gguf:
            man["vessel"] = manifest_mod.vessel(args.model_dir, args.gguf)
        elif args.model_dir:
            src = Path(args.model_dir) / "SOURCE.txt"
            man["vessel"] = {"model_dir": args.model_dir,
                             "source": src.read_text().strip() if src.exists() else None}
        try:
            print("manifest: %s" % manifest_mod.emit(man))
        except Exception as e:
            print("manifest emit failed: %s" % e)
    print("results: %s" % out_path)


# ---------- report ----------

def cmd_report(paths):
    files = []
    for p in paths:
        files.extend(globmod.glob(p))
    rows = []
    for f in sorted(files):
        for line in Path(f).read_text().splitlines():
            rows.append(json.loads(line))
    cands = sorted({r["candidate"] for r in rows})
    fams = ["entity", "instruction", "persona"]

    print("## Scored families: pass rate read1 / read2, field agreement\n")
    print("| candidate | " + " | ".join(fams) + " |")
    print("|---" * (len(fams) + 1) + "|")
    fails = {}
    for c in cands:
        cells = []
        for fam in fams:
            rs = [r for r in rows if r.get("kind") == "anchor"
                  and r["candidate"] == c and r["family"] == fam]
            ids = sorted({r["anchor"] for r in rs})
            if not ids:
                cells.append("n/a")
                continue
            p1 = sum(1 for r in rs if r["read"] == 1 and r["pass"])
            p2 = sum(1 for r in rs if r["read"] == 2 and r["pass"])
            agree = 0
            for i in ids:
                f1 = [r["fields"] for r in rs if r["anchor"] == i and r["read"] == 1]
                f2 = [r["fields"] for r in rs if r["anchor"] == i and r["read"] == 2]
                if f1 and f2 and f1[0] == f2[0]:
                    agree += 1
                for r in rs:
                    if r["anchor"] == i and not r["pass"]:
                        fails.setdefault(c, []).append(
                            "%s r%d: %s" % (i, r["read"], r["reason"]))
            n = len(ids)
            cells.append("%d/%d, %d/%d, agree %d/%d" % (p1, n, p2, n, agree, n))
        print("| %s | %s |" % (c, " | ".join(cells)))

    print("\n## Speed lanes (cold / warm)\n")
    print("| candidate | ctx target | prompt_tokens | ttft s | tg tok/s |")
    print("|---|---|---|---|---|")
    for c in cands:
        for size in SPEED_SIZES:
            rs = {r["read"]: r for r in rows if r.get("kind") == "speed"
                  and r["candidate"] == c and r["target_tokens"] == size}
            if not rs:
                continue
            cold, warm = rs.get("cold", {}), rs.get("warm", {})
            print("| %s | %d | %s | %s / %s | %s / %s |" % (
                c, size, cold.get("prompt_tokens"),
                cold.get("ttft"), warm.get("ttft"),
                cold.get("tg_tok_s"), warm.get("tg_tok_s")))

    vs = [r for r in rows if r.get("kind") == "vision_smoke"]
    if vs:
        print("\n## Vision smoke\n")
        for r in vs:
            print("- %s: %s %s" % (r["candidate"],
                                   "ALIVE" if r["alive"] else "DEAD",
                                   (r.get("error") or "")[:80]))

    if fails:
        print("\n## Failures, by candidate\n")
        for c in cands:
            for line in fails.get(c, []):
                print("- %s: %s" % (c, line))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--endpoint", required=True)
    r.add_argument("--candidate", required=True)
    r.add_argument("--stack", choices=["llamacpp", "vllm"], required=True)
    r.add_argument("--anchors", default=str(ANCHORS_DEFAULT))
    r.add_argument("--families", default=None)
    r.add_argument("--reads", type=int, default=2)
    r.add_argument("--speed", action="store_true")
    r.add_argument("--vision-smoke", default=None)
    r.add_argument("--model-dir", default=None)
    r.add_argument("--gguf", default=None)
    rep = sub.add_parser("report")
    rep.add_argument("paths", nargs="+")
    args = ap.parse_args()
    if args.cmd == "run":
        cmd_run(args)
    else:
        cmd_report(args.paths)


if __name__ == "__main__":
    main()
