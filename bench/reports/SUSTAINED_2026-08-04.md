# The chair under load: 5.4 hours, and where the time actually goes

**2026-08-03 23:51 to 2026-08-04 05:14 on the primary node.** Phase 2 of the overnight.
Instrument: `sustained.py`, both primary-node seats worked continuously on the frozen
120-record operations sample at temperature 0, with `fleet_telemetry.py`
sampling five nodes every 30 seconds throughout. The 5090 held nothing during
this phase. Floor: DMF. Dated observation, labeled inference.

## The result: nothing moved

**7,018 calls, zero errors.** The primary carrier 4,704 chat completions, the embedding service 231,490
embedding calls covering 7,407,680 vectors.

| window | primary carrier median | p95 | parse | embedding service median |
|---|---:|---:|---:|---:|
| 0.0h | 3.98 | 4.87 | 100% | 0.08 |
| 1.0h | 3.91 | 5.09 | 100% | 0.08 |
| 2.0h | 3.98 | 5.09 | 100% | 0.08 |
| 3.0h | 3.98 | 4.97 | 100% | 0.08 |
| 4.0h | 3.97 | 5.08 | 100% | 0.08 |
| 5.0h | 3.90 | 4.97 | 100% | 0.08 |

Hour five equals hour zero on every axis. The embedding service is flat to two decimals in all
eleven windows. Parse never left 100 percent.

The physical half agrees. The 4090 held 99 percent utilisation for the whole run
at a median 2760 MHz, with the per-window clock minimum also 2760, meaning not
one sample dipped while loaded. Temperature crept two degrees, 54 to 56. Power
sat at 238W flat.

**The chair does not throttle.** Same conclusion the 2026-08-02 capture reached
for the GB10, now established for the primary node, and it licenses the same thing: a long
unattended campaign here can be scheduled at its first-hour rate.

One caution on reading the clock table. The final window shows a minimum of 210
MHz, which is not a throttle: the run ended at 05:14 and those are idle samples
taken after it. The last loaded sample was still 2760.

## The headroom nobody was using

Neither card came near a limit.

| | util | temp | power | of limit | clock |
|---|---:|---:|---:|---:|---:|
| 4090, phase 2, two seats | 99% | 55C | 238W | 50% | 2760 MHz |
| 5090, phase 1, bench only | 99% | 68C | 377W | 66% | 2895 MHz |

The 4090 ran two seats flat out at half its 480W envelope and 55 degrees. It is
not power limited and it is not thermally limited, which means the contention
below is scheduling between two processes on one GPU rather than the card
running out of anything.

## Where the time goes, decomposed

The 3.98s figure conflates two different things, so it was measured apart on an
idle fleet at 06:03 rather than left as a caveat.

| condition | median | p95 |
|---|---:|---:|
| E4B on the 5090, alone | 1.98s | 2.53s |
| the primary carrier on the 4090, alone | 2.48s | 3.01s |
| the primary carrier on the 4090, with the embedding service loaded | 3.98s | 5.09s |

Same model, same 120 records, same temperature, one call in flight throughout.

- **The card is worth 25 percent.** 1.98s to 2.48s, 5090 against 4090.
- **The embedding service is worth 61 percent.** 2.48s to 3.98s on the same card.

Contention costs more than twice what the silicon difference does, and it is
being paid on a box whose second GPU sat at 1,149 MiB and zero percent for the
entire night.

**Read the 61 percent with its condition attached.** The embedding service ran at its ceiling all
night, 231,490 calls of 32 texts each, roughly 380 texts per second sustained.
No real campaign generates that. The honest claim is that 61 percent is the
worst case rather than the expected case, and the useful part is the sign and
the size of the effect rather than the exact figure.

## What this argues for

**Move the embedding service to the 5090.** Both primary-node seats are currently pinned to
`CUDA_VISIBLE_DEVICES=1`, and nothing chose that: it is what the initial
onboarding set when there was one seat. The 5090 is larger, faster on this
workload by 25 percent, and completely unused. Splitting the two seats across
the two cards costs one line in one unit file and recovers a contention penalty
that runs up to 61 percent under heavy embedding load.

The follow-up measurement that would close this properly is the same sustained
run with the seats split, which is a four-hour rerun of an instrument that now
exists. Until that runs, the split is a well-supported inference and not a
measured result. Tier 3.

Second and smaller: both devices report `pcie gen1 x8` in the telemetry. Model
load times of 2s and 12s say it is not hurting anything today, and idle link
downshift is the ordinary explanation, but the map records this box as x8/x8 and
nobody has checked what it negotiates under a transfer that would care.
