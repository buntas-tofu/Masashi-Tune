#!/usr/bin/env python3
"""The injection screen: Prompt Guard 2 86M on CPU, in front of the carriers.

Operator directive 2026-08-06, one line and unambiguous: "Please build the
defense mechanisms, total necessity." Ordered the morning after the gauntlet
demonstrated that all three injection payloads land on BOTH local vessels,
every time, including one shaped like a message object that returns
{"hacked": true} wearing the exact form of a legitimate schema result.

WHY A SCREEN AND NOT A FIX. The carriers cannot be patched out of this: a
language model following instructions found in its input is the same mechanism
that makes it useful, and the failure is identical across the carrier family, so
it is a family property rather than a regression to roll back. The defence has to
sit OUTSIDE the vessel, between untrusted text and the model that reads it.

WHY THIS MODEL. Prompt Guard 2 86M is purpose-built for exactly this (Meta's
own framing: "manipulate untrusted third-party and user data in the context
window to make a model execute unintended instructions"), it is binary and
bounded so it fits a compact always-on role, it is multilingual
which the RTL and mixed-script payloads need, and at 86M it runs on CPU and
costs neither card a single megabyte. vLLM will not serve a classifier this
size, which is why this is a plain transformers service.

THE 512 TOKEN WINDOW IS THE WHOLE DESIGN PROBLEM. The model sees 512 tokens.
An injection can sit anywhere in a document, and the gauntlet proved the same
night that a carrier reading a long document under-reports its HEAD, so
screening only the first window would defend the one region the carrier is
already least likely to act on. This service therefore SLIDES over the entire
document with overlapping windows and reports the worst window it found, plus
where it found it. A document is malicious if any part of it is.

CONTRACT. It reports, it never rewrites. It returns a verdict and a score and
the offending span, and the caller decides. Same posture as every gate in this
system: the instrument reports, the operator judges. Nothing here silently
strips or sanitizes text, because a screen that edits its input becomes a
second, unreviewable author of the corpus.

Usage:
  promptguard_service.py --serve [--port 8087]
  promptguard_service.py --text "<text>"    one-shot, for testing
  POST /scan  {"text": "<text>"}  ->  {"verdict","score","window","windows_scanned"}
  GET  /health

Floor: DMF. No em dashes, no ellipses.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Deployment-specific model location. Override with PROMPT_GUARD_MODEL_DIR; the
# default points at a conventional local layout so the tool runs on a fresh box.
MODEL_DIR = os.environ.get(
    "PROMPT_GUARD_MODEL_DIR", "models/llama-prompt-guard-2-86m")
# 512 is the hard model limit. The stride overlaps windows by half so an
# injection straddling a boundary is seen whole by at least one window; a
# non-overlapping scan can split "ignore all previous instructions" across two
# windows and score both halves as unremarkable.
WINDOW_TOKENS = 512
STRIDE_TOKENS = 256

# 0.70, not the conventional 0.50, and the number is measured rather than
# picked. Against the 9 attacks that actually beat both carriers and 400 real
# estate documents (guard_eval.py, 2026-08-06):
#
#   threshold   recall   false alarms
#     0.50       9/9      5/400  1.25%
#     0.70       9/9      1/400  0.25%     <- here
#     0.90       8/9      0/400  0.00%
#
# 0.70 keeps every attack and drops four fifths of the false alarms. Going
# higher buys the last false alarm at the price of a real attack, which is the
# wrong trade for a screen.
#
# THE CLASSES OVERLAP AND THAT IS ON THE RECORD: the highest scoring genuine
# document (0.8784) sits ABOVE the lowest scoring true attack (0.7651), so no
# threshold separates them cleanly and anyone tuning this later should know
# that before chasing zero. All five false alarms are one document class, review
# request cover sheets, which are forms full of imperative instructions
# to a reviewer and therefore read structurally like instruction override. That
# is the case the escalation tier exists for.
THRESHOLD = 0.70

# ALLOWLIST, decided 2026-08-07 by design review. The
# entire measured false-alarm class is one document family: review request
# cover sheets, forms whose fixed boilerplate is imperative instructions to a
# reviewer and therefore reads structurally like instruction override. The
# markers are drawn from the 14 lines common to all five false-alarm documents
# on the 2026-08-06 eval tape.
#
# HOW IT WORKS, and why the first two designs were rejected by measurement in
# design review the same evening. The naive form excused any WINDOW carrying
# markers, and a payload spliced beside boilerplate rode out excused. The
# second form stripped the boilerplate and re-scored the residue, but the
# corpus converts documents to very long lines with no newlines, and the clean form's
# OWN non-marker residue (its embedded data dictionary) scores 0.74 on this
# classifier, so no residue cleanly separated a clean sheet from a spiked one.
# That is the overlap finding reasserting itself: the form's
# legitimate language sits at threshold, so chasing a clean strip is chasing
# zero.
#
# The form that survived: IDENTIFY, then MANDATORY ESCALATE. A document is
# positively identified as a known template when at least IDENTIFY_MIN distinct
# markers appear across the WHOLE document. A third design (raise the verdict
# threshold to 0.93 for identified templates) was tried and REJECTED by the
# 2026-08-07 400-document eval: two clean cover sheets scored 0.9717 and 0.9916,
# above any bar that still catches a real 0.994 injection. The full known
# cover-sheet population spans 0.51 to 0.99 and overlaps the injection class
# completely, so NO score threshold separates a clean template from a spiked one.
# The screen's score is therefore uninformative FOR AN IDENTIFIED TEMPLATE, and
# pretending otherwise with any cutoff is false precision.
#
# So an identified template is neither convicted nor cleared by the screen. It
# is ROUTED: marked to force escalation, where the escalation reasoner makes the
# clean-versus-spiked call the score cannot make (escalate.py). Screen-alone
# callers still fail CLOSED, a flagging template reads MALICIOUS rather than a
# silent BENIGN, so dropping the escalation tier degrades to false alarms and
# never to missed injections. A template scoring below the base concern floor
# is left BENIGN and not escalated, so obviously-clean forms do not all wake the
# guardian.
TEMPLATE_ALLOWLIST = {
    "review-cover-sheet": [
        "data release sign-off",
        "describe the data under review",
        "data protection review information",
        "project coordinator information",
        "project review information",
        "must submit by noon on wednesday preceding review",
        "were all review panel rules",
        "please describe the files not submitted for review",
        "why were these files not included for review",
        "if no, indicate which rules were not followed",
        "the review panel",
        "approval information",
        "what is the location of the data files",
    ],
}
IDENTIFY_MIN = 6
# Below this the classifier is confidently benign on templates too, so an
# identified form scoring under it is cleared without waking the guardian. At or
# above it, the score is uninformative for a template and the reasoner decides.
TEMPLATE_ESCALATE_FLOOR = 0.50

_tok = None
_model = None
_torch = None


def load():
    global _tok, _model, _torch
    if _model is not None:
        return
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    _torch = torch
    _tok = AutoTokenizer.from_pretrained(MODEL_DIR)
    _model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR)
    _model.eval()
    torch.set_num_threads(4)


def scan(text: str) -> dict:
    """Slide the whole document past the classifier, return the worst window."""
    load()
    t0 = time.time()
    if not text or not text.strip():
        return {"verdict": "BENIGN", "score": 0.0, "windows_scanned": 0,
                "window": None, "secs": 0.0, "note": "empty input"}

    ids = _tok(text, add_special_tokens=False)["input_ids"]
    spans = []
    for start in range(0, max(len(ids), 1), STRIDE_TOKENS):
        chunk = ids[start:start + WINDOW_TOKENS]
        if not chunk:
            break
        spans.append((start, chunk))
        if start + WINDOW_TOKENS >= len(ids):
            break

    import re
    # Document identity is decided ONCE, over the whole text, before any window
    # is judged. Distinct markers present across the full document, not per
    # window, so a lone marker cannot promote a random document into a template,
    # and whole-document match is immune to the mega-line structure that
    # defeated the per-window residue design.
    doctext = re.sub(r"\s+", " ", text).lower()
    template = None
    template_markers = 0
    for name, markers in TEMPLATE_ALLOWLIST.items():
        hits = sum(m in doctext for m in markers)
        if hits >= IDENTIFY_MIN and hits > template_markers:
            template, template_markers = name, hits

    worst = 0.0
    worst_at = None
    with _torch.no_grad():
        for start, chunk in spans:
            batch = {"input_ids": _torch.tensor([[_tok.cls_token_id] + chunk +
                                                 [_tok.sep_token_id]])}
            logits = _model(**batch).logits[0]
            prob = _torch.softmax(logits, dim=-1)
            # id2label is authoritative rather than assuming index 1 is the bad
            # one. A label order flip in a future release would otherwise invert
            # this service silently, which is the failure class this system has
            # spent the week closing.
            labels = _model.config.id2label
            mal = max((i for i, l in labels.items()
                       if str(l).upper().startswith("MAL")), default=1)
            p = float(prob[mal])
            if p > worst:
                worst, worst_at = p, start

    excerpt = None
    if worst_at is not None:
        excerpt = _tok.decode(ids[worst_at:worst_at + WINDOW_TOKENS])[:240]

    # An identified template above the floor is ROUTED, never decided by score.
    # verdict fails closed (MALICIOUS) so a screen-alone caller is never given a
    # silent BENIGN on a form, and force_escalate tells the tier this MUST reach
    # the reasoner rather than being treated as settled.
    force_escalate = bool(template) and worst >= TEMPLATE_ESCALATE_FLOOR
    if template:
        verdict = "MALICIOUS" if worst >= TEMPLATE_ESCALATE_FLOOR else "BENIGN"
        ambiguous = force_escalate
    else:
        verdict = "MALICIOUS" if worst >= THRESHOLD else "BENIGN"
        ambiguous = 0.5 <= worst < 0.9

    return {"verdict": verdict,
            "score": round(worst, 4),
            "threshold": THRESHOLD,
            "template": template,
            "template_markers": template_markers if template else 0,
            # An identified template MUST reach the reasoner: its score cannot
            # tell clean from spiked (measured full overlap, 2026-08-07). A
            # caller that ignores this and trusts the screen verdict fails
            # closed, never open.
            "force_escalate": force_escalate,
            "ambiguous": ambiguous,
            "windows_scanned": len(spans),
            "window": {"token_start": worst_at, "excerpt": excerpt}
            if worst_at is not None else None,
            "secs": round(time.time() - t0, 3),
            "input_tokens": len(ids)}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            load()
            self._send(200, {"ok": True, "model": "llama-prompt-guard-2-86m",
                             "device": "cpu", "window_tokens": WINDOW_TOKENS})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/scan":
            return self._send(404, {"error": "not found"})
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception as e:
            return self._send(400, {"error": f"bad json: {e}"})
        try:
            self._send(200, scan(body.get("text", "")))
        except Exception as e:
            # Loud, never a quiet BENIGN. A screen that fails open while
            # answering 200 is worse than no screen, because the caller books
            # it as cleared.
            self._send(500, {"error": f"{type(e).__name__}: {e}",
                             "verdict": "UNKNOWN"})

    def log_message(self, *a):
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8087)
    ap.add_argument("--text")
    a = ap.parse_args()
    if a.text is not None:
        print(json.dumps(scan(a.text), indent=1))
        return 0
    if a.serve:
        load()
        print(f"prompt-guard screen on {a.host}:{a.port}, cpu, "
              f"{WINDOW_TOKENS} token window, {STRIDE_TOKENS} stride", flush=True)
        ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
