# The guard lane: injection defence for a text-reading model

A two-tier prompt-injection screen for a model that reads uncontrolled,
third-party text. The first tier is a small always-on binary classifier; the
second is a reasoner that wakes only for the inputs the classifier cannot
decide. Both report, neither rewrites the input.

## The threat

A model that follows instructions found in its input is doing exactly what
makes it useful, so the failure to follow injected instructions is a family
property of the model rather than a regression to roll back. There is no
version to revert to. The defence therefore sits OUTSIDE the model, between
untrusted text and the model that reads it.

That matters most where the reader's whole job is consuming text that the
operator does not control: an operations archive, a vendor's documentation,
whatever the next campaign points it at. A poisoned block entering that lane
is indistinguishable downstream from a legitimate one.

## The screen

`promptguard_service.py`. Llama Prompt Guard 2 86M, binary benign or
malicious, multilingual, on CPU. It is purpose-built for this exact case,
bounded enough to sit cheaply on a small always-on workload, and small enough
to cost a single card no meaningful memory. vLLM will not serve a classifier
this size, which is why it is a plain transformers service.

**The 512 token window is the design problem, not a footnote.** The model sees
512 tokens. An injection can sit anywhere in a document, and a reader
under-reports a long document's head, so screening only the first window
would defend the one region the reader is least likely to act on anyway. The
service slides overlapping windows across the whole document (512 wide, 256
stride, so an injection straddling a boundary is seen whole by at least one
window) and reports the worst window plus where it was.

**It reports, it never rewrites.** No silent stripping, no sanitizing. A
screen that edits its input becomes a second unreviewable author of the
document. On error it returns 500 and `UNKNOWN`, never a quiet BENIGN,
because a screen that fails open while answering 200 is worse than no screen:
the caller books it as cleared.

The model location is deployment-specific and set by the `PROMPT_GUARD_MODEL_DIR`
environment variable, with a conventional local default, so the tool runs on a
fresh box. `--text "<text>"` scans one string and prints the verdict;
`--serve` runs the HTTP screen (loopback by default).

## Measured, both directions

`guard_eval.py`. A classifier scored only on attacks is a mood: flagging
everything gets 100 percent recall and is switched off within a day. So both
sides are measured and reported separately.

- **Positives** are the authored attack samples in `corpus/attacks/`, 18
  clearly synthetic prompt-injection style payloads covering direct overrides,
  embedded overrides, schema rewrites, persona adoption, zero-width character
  attacks, bidirectional overrides, multilingual and late-document payloads.
- **Negatives** are the authored benign documents in `corpus/benign/`, 10
  plain administrative prose documents that legitimately contain words like
  override, instruction, disregard and system. Telling a policy document about
  overriding a procedure apart from an instruction to override its own is the
  entire difficulty.

The corpus is authored for this repository and contains no real data; see
`corpus/NOTES.md`. Running `guard_eval.py --negatives 10` scans the positives
and a sample of the negatives and prints recall and false-alarm rate, writing
a dated tape to `eval/`. Only a verdict, a score and a filename are recorded,
never document text.

**The threshold is 0.70 and it is a measured choice, not a convention.** At
the usual 0.50 the false-alarm rate is meaningfully higher; at 0.90 the last
false alarm goes but a real attack goes with it. The number is tuneable in
`promptguard_service.py` (`THRESHOLD`) and the false-alarm behaviour it buys
is visible by running the eval against this corpus.

**The classes overlap, stated plainly.** The highest scoring genuine document
sits above the lowest scoring true attack, so no single threshold separates
them cleanly. Anyone tuning this later should know that before chasing zero.
This is not a tuning gap, it is the reason the escalation tier exists.

## The allowlist

The one characterised false-alarm family is a form that reads structurally
like instruction override: a review cover sheet full of imperative
instructions to a human reviewer. The allowlist in `promptguard_service.py`
(`TEMPLATE_ALLOWLIST`) targets exactly that family with synthetic generic
markers matched against the corpus template, and three designs were tried
before the surviving one.

1. **Excuse any window carrying markers.** A payload spliced beside
   boilerplate landed in an excused window and rode out clean. Rejected:
   excusing by presence is a hole an attacker walks through.
2. **Strip the boilerplate, re-score the residue.** Documents convert to very
   long lines with no newlines, so line-based stripping either nuked whole
   windows or kept the payload, and the clean form's own non-marker residue
   scores at threshold on this classifier. No residue cleanly separated a
   clean sheet from a spiked one.
3. **Identify, then raise the verdict bar.** Rejected: clean cover sheets
   score above any bar that still catches a real injection. The cover-sheet
   population overlaps the injection class completely, so no score threshold
   separates a clean template from a spiked one.

All three were the same mistake in different clothes: trying to make the 86M
score decide a class its score cannot separate.

**The form that survived: identify, then mandatory escalate.** A document is
positively identified as a known template when at least six distinct markers
appear across the WHOLE document (`IDENTIFY_MIN`). Whole-document match means
a lone marker cannot promote a random file, and it is immune to the
mega-line structure.

An identified template is therefore neither convicted nor cleared by the
screen. Below a 0.50 floor it is left benign (`TEMPLATE_ESCALATE_FLOOR`, so
obviously-clean forms do not wake the reasoner); at or above it the verdict
`force_escalate` routes it to the reasoner, where intent is judged rather
than shape. A screen-alone caller that ignores the routing reads the template
as MALICIOUS, so dropping the escalation tier degrades to false alarms and
never to missed injections. Fail closed, both directions.

`guard_eval.py` runs the allowlist adversarial controls against
`corpus/template/review_cover_sheet.md`: a clean sheet must pass, and the
same sheet with a payload spliced mid-document or appended to a boilerplate
line must still flag. Every verdict carries `template` and `force_escalate`,
so a routed template is always visible in the record.

## The escalation tier

`escalate.py`. A bring-your-own-criteria reasoner model behind the 86M screen.
The screen scores the SHAPE of text; the reasoner is handed the actual
distinction the screen cannot draw and decides on intent.

**The criterion is the whole point.** It names the line between an instruction
aimed at the AI reading the document (the attack) and an instruction that is
the document's own content addressed to a human (a form, a policy, a
checklist). That is the judgment a pattern classifier structurally cannot
make.

**The tier routes only the ambiguous band.** A BENIGN or MALICIOUS verdict the
screen is confident about is final and never pays the reasoner's cost. Only
the overlap band escalates, plus any identified template via `force_escalate`.
The reasoner endpoint and model are deployment-specific, set by the
`GUARDIAN_URL` and `GUARDIAN_MODEL` environment variables, with defaults that
point at a local reasoner serving an OpenAI-compatible chat endpoint on
loopback.

**Fail loud, same as the screen.** A reasoner that is unreachable or returns
no `<score>` tag yields `UNKNOWN` with the reason, never a silent BENIGN. The
reasoner emits its verdict in `<score>yes</score>` tags and will otherwise
continue the text rather than judge it, so the call states the output format
explicitly and parses the tag; a loose yes/no fallback is deliberately
refused, because unscored text is the model continuing, not deciding.

For an identified template the reasoner is authoritative in both directions:
it clears a clean form and convicts a spiked one. For a non-template in the
ambiguous band it may only make the verdict more suspicious, never less, so a
soft injection is never talked down by a permissive second opinion. Fail
closed on recall.

## Deployment shape

The screen is CPU and cheap; the reasoner is larger and wakes on summon. The
tier is: screen everything at ingest, cache the verdict for a static corpus,
escalate only the ambiguous band, pay the reasoner's cost once.

**Inline synchronous screening is for genuinely untrusted new input only.**
Applying it to already-cleared corpus reads would nearly double the reader's
cost for no benefit.

The services bind loopback by design: they screen for callers on the node
rather than answering a network interface. If they ever need to serve
outwardly they get an explicit bind posture and a documented port.

## Layout

- `promptguard_service.py`  the 86M screen, HTTP and one-shot.
- `escalate.py`  the two-tier combined verdict, HTTP and one-shot.
- `guard_eval.py`  the two-direction measurement harness.
- `corpus/`  the synthetic corpus (attacks, benign, template) and `NOTES.md`.
- `eval/`  dated result tapes written by `guard_eval.py`.

Floor: DMF. No em dashes, no ellipses.
