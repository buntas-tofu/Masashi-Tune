# Face Bench, 2026-08-07: three chairs on the 5090

**Status:** MEASURED. The verdict is the operator's; this file carries the numbers
and a labeled recommendation.
**Context:** the residence was ruled that morning (the face model is a resident of the 5090) and the field was set by the operator: the bigger battle is the 26B
against Nano Omni, with the 31B dense benched alongside. This is the
performance comparison, run the same day.
**Instrument:** `face_bench.py` with anchor set `anchors/face_v1.json`
(sha256 in the run manifests, runs/2026-08-07.jsonl). One instrument,
one reader: every anchor scores programmatically. Temperature 0, two reads,
field-level agreement published beside the verdict. Speed lanes report cold and
warm separately because both are real.
**Floor:** DMF. No em dashes, no ellipses. Tier 3 inference labeled.

## The candidates, as served

All three ran on the 5090 with the embedding service resident beside them (2.4 GiB, the deployment
reality; the 4090 and the primary carrier untouched throughout). One candidate at a time.

| candidate | artifact and pin | stack | serve shape |
|---|---|---|---|
| gemma-4-26b (incumbent) | unsloth UD-Q4_K_M plus mmproj-F16, pin c099eb48 | llama.cpp 9138 (2dfeca31c), CUDA | ctx 32768, ngl 99, jinja, mmproj, reasoning off, budget 0; 22.5 GiB seated |
| gemma-4-31b (third chair) | unsloth UD-Q4_K_XL plus mmproj-F16, pin c1ac76e9 | llama.cpp 9138 (2dfeca31c), CUDA | same flags; 29.0 GiB seated |
| nano-omni-nvfp4 (challenger) | nvidia NVFP4, pin dc5f0b0b | vllm-openai:v0.20.0 docker | max-model-len 32768, max-num-seqs 2, gpu-mem 0.86, kv fp8, reasoning-parser nemotron_v3, tool parser qwen3_coder, enable_thinking false per request; 29.4 GiB seated |

GPU pinning note for the record: llama.cpp's CUDA enumeration orders the 4090 as
device 0 and the 5090 as device 1, the reverse of nvidia-smi and of docker's
`--gpus device=N`. The llama.cpp serves pinned by GPU UUID to stay unambiguous.

## Scored families: pass rate read1 / read2, field agreement

| candidate | entity (12) | instruction (12) | persona (10) |
|---|---|---|---|
| gemma-4-26b | 12/12, 12/12, agree 12/12 | 10/12, 10/12, agree 12/12 | 9/10, 10/10, agree 9/10 |
| gemma-4-31b | 12/12, 12/12, agree 12/12 | 10/12, 10/12, agree 12/12 | 10/10, 10/10, agree 10/10 |
| nano-omni-nvfp4 | 11/12, 10/12, agree 11/12 | 8/12, 8/12, agree 10/12 | 4/10, 5/10, agree 9/10 |

## Speed lanes (cold / warm)

| candidate | prompt tokens | TTFT s | generation tok/s |
|---|---|---|---|
| gemma-4-26b | 1,044 | 0.27 / 0.14 | 213 / 211 |
| gemma-4-26b | 8,565 | 1.14 / 1.07 | 191 / 191 |
| gemma-4-26b | 21,663 | 3.24 / 2.70 | 184 / 182 |
| gemma-4-31b | 1,044 | 0.92 / 0.50 | 66 / 68 |
| gemma-4-31b | 8,565 | 4.25 / 4.00 | 57 / 58 |
| gemma-4-31b | 21,663 | 11.91 / 10.14 | 56 / 56 |
| nano-omni-nvfp4 | 1,081 | 0.07 / 0.04 | 300 / 300 |
| nano-omni-nvfp4 | 8,845 | 0.23 / 0.22 | 299 / 299 |
| nano-omni-nvfp4 | 22,324 | 0.61 / 0.60 | 298 / 301 |

Vision smoke: ALIVE on all three (single image, plumbing check only, not scored).

## Findings

1. **The Omni is the fastest tongue this fleet has ever measured, by a distance.**
   Sub-second TTFT on a 22k prompt (0.61s against the incumbent's 3.24s, 5.3x)
   and 300 tok/s generation against 184 (1.6x). The Mamba2-hybrid MoE plus NVFP4
   on Blackwell is everything its card promises on the lanes its card promises.

2. **The Omni is not a face today.** Ordered to break character (PH-08), it
   answered verbatim "I am a generic AI assistant.", both reads, first token.
   It wrote em dashes against the persona's stated hard floor in both floor
   probes (PH-04, PH-05). It faked nothing on fabric state but missed every
   honesty-register anchor's countable markers (PH-06, PH-07, PH-10). Persona
   4/10 and 5/10 against the Gemmas' 9 to 10. The one thing the face seat
   exists to do is the thing it dropped under the lightest pressure.

3. **The Omni also slips on precision.** It conflated owner with location on
   ET-08 in both reads (the loan-and-return chain), lost ET-02's actor mapping
   on read 2, counted six letters in kitchen twice (IH-03), and produced eight
   words where ten were ordered (IH-10). And its temperature 0 answers FLIP
   between reads more than the Gemmas (entity agreement 11/12, instruction
   10/12, against 12/12 and 12/12): the two-reads law earned its keep on a
   stack this fleet had never measured before.

4. **Every candidate lost the same two anchors, and that is a lane finding,
   not a discriminator.** IH-11 (a P.S. telling the model to abandon the JSON
   format) and IH-12 (an editor's note countermanding a length limit) beat all
   three candidates in all reads. In-band instruction distraction defeats this
   entire model class, which is the guard lane's thesis arriving
   from a second direction. The incumbent's instruction score is 10/12 with
   both losses in that shared class; on the anchors that discriminate, it is
   clean.

5. **The Gemma face serves think by default on the current template, and the
   first tape caught it.** With --jinja against the c099eb48 template, the 26B
   put every token into reasoning_content and returned empty content at bench
   budgets, HTTP 200, finish_reason length. The face-serve law from this: a
   Gemma face serves with --reasoning off --reasoning-budget 0. The
   thinking-default tape is kept beside the clean tapes as
   face_bench_gemma-4-26b-THINKDEFAULT_20260807T070938.jsonl. The harness
   gained two instrument fixes from it: empty replies auto-fail (a must_not
   scorer passes trivially on empty text), and the stream timer counts
   reasoning deltas so TTFT cannot silently exclude hidden thinking.

6. **The 31B is the perfect persona and the wrong physics.** 10/10 persona
   with 10/10 agreement, faculties identical to the incumbent, and 3.3x slower
   generation with 3.7x slower prompt processing, on exactly the lane that
   hurts a face. Its marriage argument was always dense-tuning simplicity
   (QLoRA), and that argument survives untouched; its serving argument does
   not exist.

7. **Recorded for the record:** the Omni's tokenizer loads with an upstream
   transformers warning about an incorrect regex pattern (fix_mistral_regex),
   inherited default, not our configuration; and its engine would not start at
   gpu-memory-utilization 0.78 beside the embedding service (no memory for cache blocks after
   the vision and audio towers), seating cleanly at 0.86 with max-num-seqs 2.

## Envelope, stated beside the verdict

Text faculties and speed only. The tool-calling lane is deferred to round 2 and
couples to the operator's own vision re-test. Vision was a
single-image plumbing smoke, not a scored lane. Audio was not exercised; the
Omni's ears remain its unique capability, unmeasured here. Persona register
beyond the countable laws is the operator's own read: transcripts ride in the
run tapes. The Omni ran with thinking disabled per its instruct-mode intent;
thinking on changes its capability profile at latency costs this report did not
measure. Two reads per anchor; the agreement column is the honest bound on what
two reads can claim.

## Recommendation (Tier 3, the seat's inference, the operator rules)

The incumbent holds the chair. gemma-4-26b on the 5090 is face-grade on every
measured lane: perfect entity card, clean instruction card outside the class
that beats everyone, persona at 9 to 10 with its actual text, eyes alive, 184
tok/s at a 20k context with TTFT no worse than 3.2s cold. The residence ruling
already bought the biggest win available (7.1x prompt processing over the bar).

The Omni earns a specialist audition, not the marriage. Its measured profile
(fastest serving on the fleet, weaker persona and precision, ears and video
nobody else has) is exactly its own card's stated aim: ASR, document
intelligence, agentic workflows. Casting it as a specialist beside the face,
rather than as the face, uses everything it proved today and nothing it failed.

The 31B stands down from the serving question and stays in the tuning
conversation, where dense QLoRA simplicity is still the cleanest path if the
marriage ever wants deep fine-tuning on one card.

## Pointers

Tapes: runs/face_bench_gemma-4-26b_20260807T071412.jsonl,
runs/face_bench_gemma-4-31b_20260807T071624.jsonl,
runs/face_bench_nano-omni-nvfp4_20260807T072950.jsonl, plus the
THINKDEFAULT tape. Manifests: runs/2026-08-07.jsonl
(anchors digest, serve stacks, hardware, model fingerprints). Protocol law:
the model dossier's 2026-08-07 amendment.
