# Bench reports

Honest measurement write-ups from a small sovereign multi-model fabric. These
are staged clean copies of measurement reports, kept because the method and the
numbers are the point: one instrument, one reader, temperature 0, two reads,
agreement reported beside every score, and a recommendation labeled as
inference and left to the operator. Names are normalized to model class and
role register. Every figure is kept exactly as measured.

The set:

| report | what it measures |
|---|---|
| `FACE_BENCH_2026-08-07.md` | Three vision-language candidates on one card: entity, instruction, persona, and speed, with the two-reads agreement law. |
| `FACE_BENCH_HEAT2_2026-08-20.md` | Two challengers against the standing face under the same instrument and anchors. |
| `adapter-ab-v1-2026-08-21.md` | A bare model against the same model wearing a persona adapter, hot-swap, one variable. Ends with the tool-lane finding that superseded the recommendation. |
| `GAUNTLET_2026-08-05.md` | Variation and abuse testing of two small carriers, plus a relay run: where the carriers break, and what co-location with a busy reasoner costs. |
| `ANCHOR_CONTAMINATION_2026-08-04.md` | A parse-rate mystery traced to four undecoded PDFs in the anchor set, and what that invalidated. |
| `LADDER_2026-08-04.md` | Two task rungs crossed with several quant arms, and the reproducibility gradient between them. |
| `SETLIST_2026-08-04.md` | A paired-arm comparison of two republishes of two model families on a frozen record sample. |
| `SPECIALIST_LADDER_2026-08-04.md` | The run order and results that turn a staged specialist kit into receipts: serve smokes, a cross-silicon gate, an endurance nestle, the flip. |
| `SUSTAINED_2026-08-04.md` | Several hours of continuous load on two seats in one box, and where the time actually goes. |
| `SUSTAINED_LOAD_2026-08-02.md` | A first fleet telemetry capture: one eight-GPU-class node under a real campaign, plus idle figures across the fleet. |
| `DEEPSEEK_V4_FLASH_CHARACTERIZATION_2026-08-22.md` | A checkpoint characterization computed from the index and config: integrity, parameter accounting, and KV physics. |
| `reasoner-streams-2026-08-17.md` | A 120B reasoner under parallel streams: the throughput curve, what it licenses, and what it does not. |

Reading notes:

- The reports cite run tapes and manifest files (under `runs/`) that are not
  part of this set. Raw result tapes are not shipped by ruling, so a few figures
  rest on the estate originals of record rather than on a file in this tree.
  The launch review owns the number-provenance gate.
- Status lines are kept on every report: these are testbed observations, dated,
  with inference labeled and the verdict left to the operator.
