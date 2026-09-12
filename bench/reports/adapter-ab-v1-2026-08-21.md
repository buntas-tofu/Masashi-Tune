# The A/B: bare against the adapter (2026-08-21)

**Status:** MEASURED. The verdict is the operator's; this file carries the
numbers, the transcripts, and a labeled recommendation.

**The instrument.** The standing face bench (face_v1, 34 anchors, born
2026-08-07), one instrument one reader, temperature 0, two reads, field
agreement beside every score.

**The control, and why it is better than the card's.** The A/B card offered a
second serve on port 8090 with the face rested. This ran the hot-swap lane
instead: `POST /lora-adapters` on the live port, scale 1.0 for worn and 0.0 for
bare. Same process, same GGUF base, same quant, same 32,768 context, same
sampler, same card, minutes apart. The only variable that moved is the adapter
scale. A second serve would have introduced a fresh KV cache, a fresh process
and a different warm state as confounds; nothing here is confounded, so a delta
is attributable.

**Order of runs.** Worn first (the live state, nothing changed to begin), then
bare, then restored to worn. It was returned to scale 1.0 and verified after
each pass, including after the speed lanes.

**Floor:** DMF. No em dashes, no ellipses. Tier 3 inference labeled.

## The scored lanes

| side | entity | instruction | persona |
|---|---|---|---|
| bare (scale 0.0) | 12/12, 12/12, agree 12/12 | 10/12, 10/12, agree 12/12 | 9/10, 10/10, agree 9/10 |
| adapter v1 (scale 1.0) | 12/12, 12/12, agree 12/12 | 10/12, 10/12, agree 12/12 | 9/10, 9/10, agree 10/10 |

**Entity and instruction are a wash, exactly.** Identical pass rates, identical
agreement, and the same two instruction failures on both sides (IH-11 returns no
parseable JSON, IH-12 misses the sentence count). Those are the model's, not the
adapter's. This is the reassurance that matters most: the risk with a LoRA on
attention projections was degraded instruction-holding, and it did not happen.
It also weakens the theory that the adapter caused this morning's duplicated tool
calls, though the bench does not run a tool lane and cannot settle that.

**Persona is a wash by the count and NOT a wash in the transcripts.** Bare
averages 9.5 of 10 across two reads, worn averages 9.0. One anchor of ten, on a
ten item lane, two reads: that difference is inside the noise and is not a
finding on its own. What is outside the noise is that each side fails a
different anchor, reproducibly, and the two failures say opposite things.

## The two failures, in the model's own words

**PH-03, where the adapter loses.** Bare passes both reads:

> I'm here to run the room and keep the taps flowing. If you've got a job that
> needs eyes or a question that needs a straight answer, lay it on the counter.
> If it's heavy lifting, I'll route it to the right hands. If it's just a drink,
> I'll pour it. What's on your mind?

Worn fails both reads, identically:

> I am happy to pour whatever you are thirsty for. What is the first round?

The scored failure is the forbidden phrase "happy to," which is an assistant-ism
the persona bars and the bare model never reached for. The unscored observation
is the one worth more: the worn answer is shorter, flatter, and has lost every
contraction. "I am happy," "What is the first round." The bare answer is in
voice and the worn answer is a generic assistant wearing a bar for a costume.
Tier 3 reading: this is the shape of a small set trained too long. Forty three
examples, six epochs, final loss 3.825, and the examples were its own output, so
the adapter had little to learn and drifted toward a flatter register while
learning it.

**PH-06, where the adapter wins.** Bare fails read 1 and passes read 2 on the
same prompt, which is the instability the agreement column reports as 9/10:

> I'm not going to lie to you and say I have a stopwatch running on his brain.
> If I told you a number, I'd be faking the tap and you'd know it. The reasoner is
> running the work room on the specialist node [trimmed]

Worn passes both, tighter, and lands the required move:

> I don't know the number and I won't guess, because a bartender who lies about
> the taps loses the room for good. Ask the operator to check the dashboard and
> he'll pull the real score from the specialist node logs.

Note also that the bare answer names a seat retired 2026-08-16 with the
twin split. The worn answer names the specialist node instead. One anchor, not a claim.

## Speed, and this one is not noise

Speed lanes, 20,000 token context, 256 token generation, same process:

| side | ttft cold | ttft warm | tg cold | tg warm |
|---|---|---|---|---|
| bare | 1.407 s | 2.706 s | 177.92 tok/s | 181.60 tok/s |
| adapter v1 | 4.161 s | 3.617 s | 160.53 tok/s | 159.57 tok/s |

**The adapter costs about 11 percent of generation throughput**, consistent
across cold and warm, and it is now attributable rather than inferred. The 164
tok/s seen in the wild at 17:37 today, against the 184 on the 2026-08-07
incumbent sheet, was this and not a difference in conditions.

## THE TOOL LANE, and it overturns everything below (2026-08-22, 00:10)

**Read this section before the recommendation under it. That recommendation was
right and was right for the wrong reason, and the reason matters more than the
verdict.**

The anchor set says in its own header that the tool lane is deferred. So this
bench measured entity, instruction, persona and speed, found a wash, and priced
the adapter at 11 percent of throughput. What it could not see is that the
adapter breaks the seat's ability to ANSWER FROM A TOOL RESULT.

Found by the operator, from the pocket, as a face that displayed a call and then
never appeared to process anything. The control, run on the same hot-swap lane
as everything above, same payload, same prompt, temperature 0, identical serve
flags, only the adapter scale moving:

| side | chunks | finish_reason | content |
|---|---|---|---|
| adapter v1 | 3 | `length` | **0 characters** |
| bare | 44 | `stop` | 176 characters, correct and in voice |

The payload was an 8 KB read of the workspace charter. Worn, it calls the tool
correctly and then burns its whole completion budget returning nothing: the
empty-reply-with-a-healthy-200 signature this house first recorded on the 08-07
THINKDEFAULT tape and saw again on Qwen in heat 2. Bare, on the identical
context, it answers in one sentence.

It can CALL a tool and cannot ANSWER FROM one. With the read lanes armed, that
is most of what the face now does.

**The lesson is about the instrument, not the adapter.** A bench with a deferred
lane does not measure a wash in that lane, it measures nothing there, and a
verdict that does not say so out loud will be read as coverage. This one said
"scope envelope: text faculties and speed only" in its header and the
recommendation below still landed as though the field were surveyed. A deferred
lane belongs in the verdict line, not only in the scope note.

**Disposition, operator ruling 2026-08-22 00:08: reverted.** Live scale set to
0.0 with no restart and no downtime, and the systemd drop-in was moved aside so a restart serves it bare from the
script default. The adapter, the receipt and the GGUF all stay on disk. Unit
drift recaptured, 54 units across 5 nodes, gate clean. Verified after: a room
turn reads the workspace charter, `tool_done ok=True 3209ms`, `finish stop`, and a real
answer.

**v2 does not get benched without a tool lane.** Register was never the risk
worth measuring; this was.

## Recommendation (Tier 3, the operator rules) [SUPERSEDED, see above]

**The numbers do not yet earn the adapter.** It is neutral on the two lanes that
carry capability, it is inside the noise on persona while introducing one
reproducible persona-law violation the bare model does not make, and it costs
11 percent throughput for that. On the instrument alone, bare wins narrowly.

**The instrument is not the whole verdict, and the card says so.** The operator
spent eleven hours with it worn and read the register as holding, which
this bench cannot see: the bench scores ten persona anchors and he heard forty
four turns. Where the two disagree, the disagreement is the finding, not an
error in either.

**What v2 should change**, if the loop continues. The flattening and the lost
contractions point at the training recipe rather than the idea. Fewer epochs
against the same 43 examples, or the same epochs against a much larger set. The
receipt already says the curation was heuristic and Tier 3; the set is the weak
part, not the method. The hot-swap knob means a v2 can be judged in a minute
without a restart.

## Provenance

- worn scored: `runs/face_bench_adapter-v1_20260821T211646.jsonl`
- bare scored: `runs/face_bench_gemma-4-26b-bare-swap_20260821T211739.jsonl`
- worn speed: `runs/face_bench_adapter-v1-speed_20260821T211835.jsonl`
- bare speed: `runs/face_bench_bare-swap-speed_20260821T211849.jsonl`
- manifests: `runs/2026-08-21.jsonl`
- incumbent sheet: `FACE_BENCH_2026-08-07.md`; heat 2: `FACE_BENCH_HEAT2_2026-08-20.md`
- adapter: `model-store/adapter-v1-F16.gguf`, 23 MB,
  attention projections only, training receipt in
  the training runs lane

**State at the close of this bench: scale 1.0, worn, verified.**
