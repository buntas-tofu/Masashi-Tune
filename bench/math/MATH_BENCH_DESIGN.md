# The math instrument: design and envelope

Commissioned by the operator 2026-08-11 ("we have previously only built a test
for a single model; it would be valuable to have a more comprehensive test set
for math focused models"). The comprehensive successor to the July 23 overnight's 8-item
numeric gauntlet, built for the bench series between common models. Floor: DMF,
no em dashes, no ellipses.

## What it is

58 auto-gradable items in `items.jsonl`, single scalar answer each, three
sections:

- **A, standard-form core (36).** Six domains (number theory, algebra,
  combinatorics, probability, calculus, linear algebra) at three difficulty
  tiers, two items per cell. Public-STYLE classics by design: training corpora
  contain these types, which is the declared envelope, not a flaw. This is the
  comparability section.
- **B, homegrown parallel-form (12).** Authored fresh 2026-08-11 for this
  instrument, never published, structurally fresh constructions (invented
  operators, specific constraint combinations, bounded counts with a trick).
  The contamination control: the per-seat A-minus-B delta reads memorization
  against skill. If this section is ever published with a study, its items
  retire and get replaced (the used-questions registry pattern).
- **C, house-shaped applied (10).** Rounding preimage intervals, weighted
  medians, provisioning quantiles, reconciliation discrepancies, finite
  population corrections, migration flows. Ranks fit for the fabric's actual
  math lanes, per the corpus-bounds card.

## Verification law

`verify_answers.py` re-derives every answer by an independent method (brute
force or numeric) and the bank is not banked until it prints ALL VERIFIED. A
wrong answer key produces believable wrong rankings; the 08-09 lesson (a bench
on the wrong population) is the reason this file exists.

`test_grader.py` feeds the grader every format the fleet has actually
produced (ANSWER: lines, \boxed{} tex fractions, think blocks, markdown bold,
percent signs, comma groupings, bare final lines) and requires 100 percent.
The July grader falsely zeroed the boxed-emitting OpenMath family; format
tolerance is now a precondition, and format adherence is recorded as its own
routing finding rather than a grading penalty.

## Protocol

- Temperature 0 on every scored read. At greedy decode the vessel sampler
  differences (Gemma 0.7/64 against Nemotron 0.6/20) are neutralized.
- Two reads minimum; per-item read agreement published beside the ranking.
- Uniform token budget (default 16384, the July exam budget) with stop
  reasons recorded; the stopping profile is a finding, not noise.
- One instrument, one reader: grading is deterministic in the runner.
- Direct seat endpoints (`/v1/chat/completions`), never the view (the view
  clamps max_tokens). llama.cpp seats run one slot: one candidate per node at
  a time.
- Cost (tokens, wall, tok/s) reported beside quality, never blended in.
- Discrimination check before ranking: items solved or missed by every seat
  in a heat cannot separate the field; the report keeps them but the
  headline score should be read with the discriminating subset in mind. If
  the whole instrument stops discriminating, it reports a null result and
  gets rebuilt (the instrument-must-discriminate card).

## What it is not

Proof-writing and derivation quality are out of scope here; the proof-writing
harness exam heats (IMO and Putnam problems, judged) carry that lane,
unchanged from July, for longitudinal continuity. This instrument is the auto-graded floor
under the field: standard competence, contamination delta, house fit.
