# Design note: the gated art judge

`art_judge.py` ranks generated plates by having a vision model critique each
one against a fixed rubric, then reports an order only where the instrument
can support one. It is deliberately not a taste detector. It decides what the
machine is allowed to claim and makes ties look like ties.

The loop: the generator proposes, a vision model critiques each plate against
a fixed rubric, a curator keeps the survivors. Each candidate PNG rides to
the serving view's `/api/vision` as a data URI and the model returns strict
JSON scores plus a one-line flaw note.

## Why it is gated

The original ranked a gallery on the model's own one-number `verdict` field: a
single unpinned draw of a 1 to 10 ordinal, written to disk, with a curator
picking from that order. That is worse than the same defect in a text report
because of the failure mode. A false positive in a ranked report is a wrong
row you can argue with. Here it sorts a good plate below the fold and it is
never seen. The failure is an absence, and an absence does not announce
itself. So the judge is gated with four gates, weakest to strongest.

## The four gates

- **PIN.** The scoring call passes an explicit temperature (greedy by
  default). A scored stage must not roll the conversational sampling.
- **FLOOR.** The commission makes claims that are measurable off the pixels
  without asking anybody: SNES-era discipline means a bounded palette, "black
  background" means dark borders, and a degenerate render has near-zero
  variance. A plate failing the floor cannot ride a generous verdict into the
  top band. The model proposes taste; the pixels dispose on fact.
- **DERIVE.** The rubric asks for four component scores and nine inventory
  booleans, then asks the model to summarize its own answer as a single
  `verdict`. The booleans measured 97 to 100 percent reproducible on a 2026-07-29
  run and a fine ordinal at 58. So the rank is computed from the observations
  (components carry 70 percent, inventory completeness 30) and the model's own
  summary is kept beside it as a cross-check. Where a model's verdict
  disagrees with its own observations, that divergence is printed, because it
  is a better signal than either number alone.
- **BAND.** A single read is not a measurement. Plates are read K times and
  the observed spread sets a band width. Plates inside one band are tied and
  printed unordered. False precision is how a good plate ends up below the
  fold, so the report refuses to express an order it cannot support. Band
  width comes from the largest observed read-to-read spread, never a guessed
  constant.

## Model references

The vision model is parameterized and defaults to `gemma`:

- CLI: `--model <name>`.
- Env: `JUDGE_VISION_MODEL` (used when `--model` is not passed).

The serving view client is supplied by the harness. Point `VIEW_HARNESS` at a
directory that provides `harness.view.ViewClient`, an SSE chat and vision
client, and the judge will use it. Without it the import is not attempted and
the judge cannot run.

## Running

```
art_judge.py out/*.png --model gemma --reads 2
```

Each plate is read twice by default (a single read is not a measurement), the
pixel floor is measured off the image, and a markdown gallery is written next
to the plates as `JUDGE_<timestamp>.md`. Plates that fail the floor are held
out of the bands and named. Plates with no valid read are named, never
dropped.

The image corpus that generated the plates is not part of this repository.
