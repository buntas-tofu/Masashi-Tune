# The 67 percent was never a model defect

**2026-08-04, the primary node.** Found while testing whether the previous night's
4B-beats-26B result survives a harder task. It does not survive, because the
instrument that was supposed to test it cannot answer the question. Floor: DMF.
Dated observation, labeled inference.

## What is wrong

Four of the twelve anchors in `reid_dictionary_v1.json` are **undecoded bytes,
not text**. The set describes itself as "twelve captured broker documentation
pages"; four of them are the raw contents of PDF files.

| id | grade | printable | begins |
|---|---:|---:|---|
| g3-01 | 3 | 46% | `%PDF-1.4` then a Ghostscript invocation |
| g3-02 | 3 | 43% | `%PDF-1.7` then PDF object structure |
| g1-01 | 1 | 49% | binary |
| g0-01 | 0 | 49% | binary |

The other eight are 100 percent printable and read as ordinary web page text.

## Every parse failure ever recorded on this set is one of those four

Six runs, four seats, two days. Not one clean anchor has ever failed to parse
for any model.

| run | seat | parse | anchors that failed |
|---|---|---:|---|
| 2026-08-02 | the primary carrier | 16/24, 66% | g0-01, g1-01, g3-01, g3-02 |
| 2026-08-02 | the hub carrier | 17/24, 70% | g0-01, g1-01, g3-01, g3-02 |
| 2026-08-02 | the AMD carrier | 18/24, 75% | g0-01, g1-01, g3-01 |
| 2026-08-02 | the 4060 Ti carrier | 22/24, 91% | g3-02 |
| 2026-08-03 | the primary carrier, stale E4B | 16/24, 66% | g0-01, g1-01, g3-01, g3-02 |
| 2026-08-03 | the primary carrier, corrected E4B | 16/24, 66% | g0-01, g1-01, g3-01, g3-02 |

Sixteen of twenty-four is 66.7 percent. **The "67 percent parse rate" that has
been open on the board is eight clean anchors out of twelve, doubled for two
passes.** It is not malformed model output, it is not a vocabulary defect, and
it is not a quantisation artifact. It is four PDFs that were never decoded, and
no model can extract a field list from PDF object structure.

## Three things this reverses

**1. Yesterday's E4B confirming run measured nothing on its headline axis.**
The corrected build was tested against the stale one and parse "did not move"
off 67 percent. Of course it did not. Both arms failed on the same four
undecodeable anchors and succeeded on the same eight readable ones, so that
metric was saturated and structurally incapable of showing a difference in
either direction. The conclusion that the two builds are equivalent still
stands, but it now rests entirely on the 120-record operations run that came
back 120 of 120 identical, and not at all on the parse figure that motivated the
test.

**2. The 2026-08-02 four-carrier comparison ranked garbage tolerance.** The 4060 Ti
carrier at 91 percent against the primary carrier at 66 was read as a seat quality difference. The
whole spread lives in the four corrupt anchors: what actually differed is how
gracefully each model degrades when handed binary, which is not a property
anyone wanted to rank seats on.

**3. Stratifying by grade concentrated the contamination.** The capture store is
only about 1 percent affected, 43 of 3,301 files. The anchor set is 33 percent
affected. That is not bad luck: the set was stratified by the grade a 120B
assigned at stage 4, high grades mean field-rich documentation, and field-rich
documentation is disproportionately published as PDF. Sampling on a quality
label pulled in the file type that was silently failing to decode. Inference,
Tier 3, but the mechanism is straightforward and the numbers fit.

## What it did to this morning's question

The question was whether a 4B still beats a 26B when the task gets harder, moving
from 200-character bounded schema-fill to open-ended extraction from 6,000
character pages. The result is not usable as it stands:

| arm | parse | exact self-match | self-Jaccard | median s |
|---|---:|---:|---:|---:|
| e4b-corrected | 100% | 75% (9/12) | 0.833 | 2.41 |
| g26b-corrected | 83% | 100% (10/10) | 1.000 | 3.48 |

Read naively the 26B looks better on consistency and hallucination. The per-page
view says otherwise: the 26B returns an empty list on ten of twelve pages, and
on the only two pages with substantial extractable content it spends its entire
token budget reasoning and never answers. A model that says "nothing here" every
time is perfectly self-consistent and never invents a field. It is also not doing
the task.

Meanwhile nine of twelve pages yield zero fields from BOTH models, four because
they are binary and the rest because the 6,000 character truncation window
appears not to contain the field lists. **Roughly two anchors actually
discriminate between models.** No conclusion about task-complexity crossover can
rest on that, in either direction.

One genuine signal did survive and it is worth keeping: on the single grade 0
page that is readable, the 4B invented nine fields where the 26B correctly
returned none. That is the one place the larger model was clearly better, and it
is the failure mode the negatives exist to catch.

## What has to happen before the task ladder runs

The bigger study, a task-complexity ladder crossed with a parameter ladder, is
worth running and the instrument for it now exists. It cannot run on this anchor
set.

1. **Rebuild the anchor set with decoded text.** The four PDFs need extracting
   rather than reading, and the capture pipeline needs the same fix or it will
   keep producing them.
2. **Validate that anchors discriminate before freezing them.** An anchor where
   every model returns the same empty answer contributes nothing but dilution.
   The selection rule should require that the field content is present inside
   the truncation window, not merely that a 120B graded the full document highly.
3. **Fix the 43 contaminated captures**, or at minimum mark them, because any
   registrant whose only captured page is undecoded bytes carries a stage 4 grade
   derived from binary.
4. **Keep the negatives.** They earned their place twice this morning: once
   catching the 4B inventing fields, and once making the 26B's empty-list
   behaviour visible instead of flattering.

Method note, and it is the third instance in two days. The 26B's parse failures
looked like a model defect at a 3,000 token budget and survived a raise to
6,000. The raise was still the right move, because at 3,000 the failure was
partly the ceiling and the two causes were not separable. Budget for the
thinking before concluding anything about the answer.
