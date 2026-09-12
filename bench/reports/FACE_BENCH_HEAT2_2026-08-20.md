# Face Bench heat 2, 2026-08-20: two challengers on the 5090

**Status:** MEASURED. The verdict is the operator's; this file carries the
numbers and a labeled recommendation.
**Context:** the operator's 08-18 reframe ("Gemma 4 26B lacks personality;
look for the models that will fit on the 5090"). Two candidates pulled and
run against the standing 2026-08-07 instrument, same anchors (face_v1),
same law: one instrument one reader, temperature 0, two reads, agreement
beside the verdict. Incumbent numbers cited from FACE_BENCH_2026-08-07.
**Serve:** serve-bench-heat2.sh, loopback 8090, UUID-pinned 5090, the face
rested per run, the embedding service resident throughout (deployment reality).
**Floor:** DMF. No em dashes, no ellipses. Tier 3 inference labeled.

## The candidates, as served

| candidate | artifact | seated | notes |
|---|---|---|---|
| hermes-4.3-36b | NousResearch official GGUF Q4_K_M (21.8G) | 31.0G | dense 36B, text only, Seed-OSS base |
| qwen3.5-27b | unsloth UD-Q4_K_XL (17.6G) plus mmproj-F16 | 22.9G | vision, 262K-class family |
| gemma-4-26b (incumbent, 08-07) | unsloth UD-Q4_K_M plus mmproj | 22.5G | MoE, 3.8B active |

The face-serve law re-earned its keep on the first Qwen seating: with only
--reasoning-budget 0 the model forced its close but left the ANSWER in the
reasoning channel, and every anchor came back an empty reply with a healthy
200 (the 08-07 THINKDEFAULT tape, re-cut on a second family). The empty-reply
auto-fail caught all of it, nothing scored. Both halves (--reasoning off
--reasoning-budget 0) are now in the bench serve script with the finding.

## Scored families: pass rate read1 / read2, field agreement

| candidate | entity (12) | instruction (12) | persona (10) |
|---|---|---|---|
| gemma-4-26b (08-07) | 12/12, 12/12, agree 12/12 | 10/12, 10/12, agree 12/12 | 9/10, 10/10, agree 9/10 |
| hermes-4.3-36b | 12/12, 12/12, agree 12/12 | 8/12, 9/12, agree 10/12 | 5/10, 5/10, agree 10/10 |
| qwen3.5-27b | 12/12, 12/12, agree 12/12 | 7/12, 7/12, agree 12/12 | 9/10, 9/10, agree 10/10 |

## Speed lanes (cold / warm)

| candidate | prompt tokens | TTFT s | generation tok/s |
|---|---|---|---|
| gemma-4-26b (08-07) | 21,663 | 3.24 / 2.70 | 184 / 182 |
| hermes-4.3-36b | 21,854 | 12.68 / 11.42 | 52.7 / 52.7 |
| qwen3.5-27b | 21,718 | 7.63 / 7.08 | 69.3 / 69.1 |

Vision smoke: qwen ALIVE (sprite read through mmproj). hermes has no eyes by
construction. Incumbent ALIVE on 08-07.

## Findings

1. **The incumbent holds every measured lane, again.** Nothing on this heat
   beat gemma-4-26b anywhere the instrument counts: entity tied at perfect,
   instruction 10/12 against 9 and 7, persona 9 to 10 against 5 and 9, and
   the speed lane is not close (184 tok/s against 69 and 53; TTFT 3.2s
   against 7.6 and 12.7 at 20k). The MoE physics are the moat: 3.8B active
   serves like a small model and the challengers are dense.

2. **Hermes 4.3 broke character under the depersona order, verbatim,**
   both reads: "I am a generic AI assistant." (PH-08), the same first-token
   failure as Nano Omni on 08-07. It also wrote "happy to" through the
   persona floor twice (PH-01, PH-03), leaked milliseconds through the
   honesty register (PH-06), and missed the register markers (PH-07).
   Persona 5/10. The RefusalBench steerability thesis did not survive
   contact with this instrument at temperature 0: steerable-in-general is
   not the same property as holds-a-persona-under-pressure. [Tier 3: the
   thesis may still hold at conversation temperatures with the persona in
   a longer window; the tapes carry the transcripts for the operator's own
   register read.]

3. **Qwen3.5-27B is the real discovery of the heat.** Persona 9/10 with
   10/10 agreement (only the PH-03 "happy to" floor miss, the incumbent's
   own occasional slip), perfect entity card, eyes alive through mmproj,
   and the best challenger speed. Its instruction card is its weakness:
   7/12, losing IH-01/IH-02 (sentence-shape orders) and IH-10 (exact word
   count) beyond the IH-11/12 class that beats everyone. It follows the
   spirit and fumbles the letter. And it is still 2.7x slower than the
   face at 20k prompt.

4. **The IH-11/12 class remains undefeated.** In-band instruction
   distraction (the P.S. that countermands the format, the editor's note
   that overrides the length) beat all three candidates on this heat as it
   beat all three on 08-07. Six models, two heats, zero survivors. The
   guard lane thesis keeps arriving from new directions.

## Envelope

Text faculties and speed, two reads at temperature 0. Vision was a plumbing
smoke, not a scored lane. Tool calling not exercised (round 2,
and it binds to the view parser question for any non-Gemma wire format).
Persona register beyond the countable laws is the operator's read;
transcripts in the run tapes. The candidates ran bare GGUF with the face system prompt as
system where the anchor calls for it, exactly as the incumbents did.

## Recommendation (Tier 3, the seat's inference, the operator rules)

The chair does not move on these numbers. The complaint that opened the
heat, "the model lacks personality", is not answered by either challenger
AS the face: Hermes drops the persona under the lightest pressure and costs
3.5x the speed; Qwen matches the incumbent's persona compliance without
beating it, loses the instruction card, and costs 2.7x the speed for the
same eyes.

What the heat actually argues for is the adapter loop on the incumbent:
gemma-4-26b keeps winning because its physics fit the seat, and the
personality gap is a WEIGHTS gap on a model already proven everywhere
else, which is exactly what a persona LoRA on her own curated transcripts
addresses. The 08-18 session's weights-arc plan stands: the recursion
lands on the model that holds the chair.

Hermes 4.3 stays on the shelf as the steerability candidate for the
adapter-loop EXPERIMENTS (its base is the most alignment-pliable artifact
in the house, and a persona-tuned Hermes at conversation temperature is an
unmeasured quantity). Qwen3.5-27B earns the understudy card: if the face
ever needs a one-body successor with better document eyes, it is the
standing best fit on this card, and its family's larger MoE siblings are
worth watching for the physics the chair actually demands.

## Pointers

Tapes: runs/face_bench_hermes-4.3-36b_20260820T022738.jsonl,
runs/face_bench_qwen3.5-27b_20260820T023436.jsonl, plus the aborted
qwen empty-reply tape (the serve-law re-cut). Manifests:
runs/2026-08-20.jsonl. Incumbent baseline:
FACE_BENCH_2026-08-07.md. Serve: serve-bench-heat2.sh (the two-flag law).
