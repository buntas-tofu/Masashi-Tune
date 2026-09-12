# The 120B reasoner under parallel streams: the batches, and how far

**2026-08-17 night, the primary node.** Status: testbed observation.
Instrument: vLLM's own `/metrics` on the hub node:8000 (`generation_tokens_total`
deltas over 20 to 240 s windows, `num_requests_running`), taken while a
batch gate ran through the view with the harness (two-pass, temp 0,
16384 budget, 6,500-char documents plus candidates, roughly 2k prompt tokens
per call). Model: Nemotron-3-Super-120B-A12B NVFP4, vLLM v0.20.0, util 0.70,
max-model-len 32768, default max-num-seqs, kv fp8, Mamba state fp32. Floor:
DMF. Dated observation, labeled inference.

## The curve

| streams running | aggregate tok/s | per stream | efficiency vs linear | how it was set |
|---|---|---|---|---|
| 1 | 7.5 | 7.5 | 1.00 | the standing receipt (07-05 onward) |
| 4 | 43.1 | 10.8 | 1.44 | the gate smoke, 4 lanes, 22:57 |
| 10 | 56.9 | 5.7 | 0.76 | lanes G (8) plus R (2), 23:11 |
| 14 | 72.7 | 5.2 | 0.69 | plus lane B (4), 23:29 |
| 20 | 86.0 | 4.3 | 0.57 | plus lane C (6), 23:32 |
| 23 to 25 | 97.5 | 4.0 | 0.52 | plus orphaned streams from killed clients, 00:03 to 00:07 |

Zero preemptions at every point; `num_requests_waiting` stayed 0, so the
scheduler was never the limit. The 4-stream number above single-stream linear
is real and repeated on both reads (the single-stream receipt was taken through
the view with SSE and persona; the multi-stream figures are engine counters, so
the 1.44 says the single-stream figure understates the engine, not that
batching is free).

## What it licenses, and what it does not

- **A gate night is sized by streams, not seats.** The 07-20 gate fed one
  stream per twin node and measured 7.8 min per doc per stream. Tonight one seat
  at 20 streams sustains eleven times the single-stream token rate. Two twin
  nodes at one stream each were the wrong shape; one 120B at N lanes is the right one.
- **Per-stream latency is the cost.** At 20 to 25 streams a two-pass document
  takes 25 to 50 minutes end to end (pass1 median 588 s at ~10 streams, verdict
  258 s; the repro slice's second doc took 2,982 s at 25). Anything with a
  per-call timeout shorter than that will cut a stream mid-thought: the harness
  view client's 900 s and the registry's 600 s are BETWEEN-BYTES timeouts and hold
  because tokens stream, but a total-time timeout would not.
- **Killing a client does not abort its stream.** Through the view, a lane
  killed mid-call leaves its request running on the seat to completion (29
  running with 20 attached observed). Budget for it or add an abort path.
- **Marginal return flattens past ~20.** 14 to 20 streams bought 13 tok/s; 20
  to 25 bought 11. Inference (Tier 3): the knee is memory-bandwidth-bound decode
  on the unified pool; more streams keep buying a little until the Mamba cache
  or KV fills, which it had not by 25 (no preemptions).
- **The consolidator shares the seat at 03:30.** Not measured tonight; the
  telemetry sampler ran through it.

## Not measured, worth a night

the math seat (Cascade-2 BF16, the specialist node:8001, max-num-seqs 32) at 3 streams gave 49.4
tok/s against 27.8 single, on a thinking-mode draft job that was not routed;
its curve past 3 is unmeasured. The 49B's curve is unmeasured (single-stream
4.2 tok/s on its first wake). The primary node's vLLM guests (olmOCR, the Omni) batch
too and none has a curve on record.
