# Bench contract: one dual-GPU node, both cards, codified

The rules that govern how a single dual-GPU node holds services, takes summons, and stays
honest as a measurement instrument. Written because the free-agent contract that was
agreed for one card had in practice been applied only to that card, and the telemetry
said to codify it for both.

Companions: `used-gpu-bench.md` (the install bench, closed PASS), `striker-onboarding.md`
(how the box was built), and the card roster the registry loads.

## The cards, by receipt

| | GPU0 | GPU1 |
|---|---|---|
| card | RTX 5090, 32GB, air | RTX 4090 SUPRIM LIQUID X, 24GB, 240mm AIO |
| silicon | consumer Blackwell, sm_120 | Ada, sm_89 |
| power cap | 575W | 480W |
| PCIe | gen5 x8 under load | gen4 x8 (bench) |
| measured, loaded | 99 pct util at 377W, 2895 MHz (sustained) | 62C plateau at full 480W, 15 min, zero creep (bench); 5.4h at 99 pct, 238W, 55C, clocks flat 2760 (sustained) |
| extraction bench, alone | 1.98s median | 2.48s median |

Both cards flat out draw 1,055W against a 1,700W PSU, with the dual full-draw moment
already banked on install day (the container device-order burn). Power is never the
constraint on this box; scheduling is.

**The two cards are two silicon families.** Reproducibility is a property of the silicon:
on identical weights at temperature 0, a self-consistency score came back 1.00 on one
integrated-GPU family, 0.92 on a GB10, and 0.84 on Ada. A scored stage split across GPU0
and GPU1 is therefore a split across instruments, and falls under the routing law: no
calibration harness, no split. The setlist is that harness and the cross-card pair has
not been run. Until it is, a scored stage lives on one card start to finish.

## What the units say today, and what it costs

Two services were pinned to GPU1 with `CUDA_DEVICE_ORDER=PCI_BUS_ID` and
`CUDA_VISIBLE_DEVICES=1`, deliberately: the units named GPU1 the workroom card and the
service roster reserved GPU0 for the face. The reservation's referent was real (a
resident face service, the LoRA server purpose) and its tenant had not arrived, so through
one overnight the reservation meant a 5.4 hour campaign paid measured co-tenancy on the
small card while the big card held 1,149 MiB and zero percent.

The costs, measured not argued:

- co-tenancy on the small card: 2.48s alone against 3.98s beside the embedder at ceiling,
  up to 61 percent, worst case not expected case
- the card differential itself: 25 percent, 5090 over 4090, same model same records
- the embedder under both conditions: 0.08s flat to two decimals, all night

## The law

**1. Free agency is per card, not per box. RULED.** Any service may be summoned to either
card; fit decides: VRAM, latency class, co-tenancy, silicon family for scored work. GPU0
carries no standing reservation while the face is not resident. When the face lands in
weights, this contract revises with the face as GPU0's anchor tenant and the burst math
redone around its headroom. A reservation that idles the best card during the wait is
rent on an empty room.

**2. Split the small services: one to GPU0, the latency-sensitive one alone on GPU1.**
This ends the only live-live contention on the box. The latency-sensitive service runs
alone at 2.48s instead of sharing at up to 3.98s; the embedder at 1.1 GiB is the least
displacement-sensitive tenant on the rig, 0.08s flat even at ceiling.

Alternative considered and declined: moving the latency-sensitive service to GPU0 takes
the 25 percent differential for interactive work, but couples it to every burst summon
and future adapter claim on the big card, and evicting the interactive service to serve a
burst inverts the priority order below. Its stability is worth more than half a second.

Execution when ruled: one line in the unit (`CUDA_VISIBLE_DEVICES` 1 to 0), daemon-reload,
restart that service, re-capture units. Seconds of blip on the embedding port, no view
restart (unit layer, not roster layer). Not during a live campaign window.

**MEASURED AT THE MOVE, bounded-probe class at temperature 0:** shared card, the
latency-sensitive service median 0.150s solo against 0.288s under the embedder's ceiling,
a 92 percent cost; split cards, 0.150s against 0.150s at the same hammer rate. The
contention class is retired, measured rather than argued. Instrument note for the
embedding lane: a cross-card fingerprint on five fixed probes came back cosine 0.99985 to
0.99991 (sm_89 against sm_120), so the embedder's vectors are similarity-equivalent but
not bitwise stable across silicon; the determinism law extends to embeddings at roughly
1.5e-4 cosine.

**3. A measured phase owns its card by declaration.** Before measuring: assert the
physical GPU (`PCI_BUS_ID` plus `CUDA_VISIBLE_DEVICES`, the voided-run lesson, already
unit law), enumerate co-tenants off `nvidia-smi`, and write both into the run manifest.
Routine setlists may run beside the embedder once the embedder-offset calibration exists;
until then the embedder's presence is declared, not ignored. Calibration-grade runs stop
the embedding service for the window and restart it after.

**4. Burst summons land by fit, behind a wake floor.** A summon must fit model plus KV
plus 2 GiB margin inside the card's free VRAM at wake, else it queues or takes the other
card.

**5. Priority order, top wins:** live services, operator-interactive work, measured
phases, burst campaigns, opportunistic work. A measured phase never preempts a live
service; a campaign queues behind a measured phase only on the card the phase declared.

**6. Scored stages pass temperature 0 and one card reads one instrument.** Restated from
the routing law because every specialist below will run scored stages, and because on this
box the cross-card boundary is a cross-silicon boundary (Blackwell against Ada).

**7. Serving stacks.** GGUF serves on the llama.cpp CUDA build. Safetensors-class serves
on vLLM in docker. The pinned vLLM tag SERVES sm_120, verified by a vision-model canary:
engine compiled and opened its API in 40 seconds on GPU0, end-to-end vision OCR PASS. The
tag holds; the currency routine stays the upgrade path. Measured caveat for the wake
floor: vLLM's default 0.9 `gpu-memory-utilization` pooled 29.6G of the 32G card for a
9.4G model, so a guest sharing a card MUST pass an explicit `--gpu-memory-utilization`.
Tiny classifiers and embedders vLLM will not take serve via a minimal transformers
service, CPU acceptable at 86M.

## The specialist kit (first wave, all weights on disk)

Technical specialists and RAG plus sorting specialists. Ports are the node's bench range;
keys are stable handles. Every service lazy, none enabled, wake by summon. VRAM estimates
are inference until each smoke; the smoke writes the measured figure into the runs lane.

The big two are pool-dominated numbers (vLLM pre-allocates the configured fraction), so
their resident figure follows `GPUMEM`, now explicit in every serve script per law 7.

| service key | model | disk | stack | measured VRAM | card fit | port |
|---|---|---|---|---|---|---|
| olmocr7b | olmOCR-2-7B FP8 | 9.4G | vLLM | 29.6G at default pool; GPUMEM 0.50 now | either, prefer GPU0 | 8087 |
| guardian8b | granite-guardian-4.1-8b | 16G | vLLM | 24.3G at 0.75 pool | GPU0 (tight on GPU1) | 8091 |
| gptoss20b | gpt-oss-20b MXFP4 | 39G on disk, serves in 24.8G at 0.75 pool | vLLM | 24.8G at 0.75 pool | either | 8092 |
| devstral24b | Devstral-Small-2-24B | 49G BF16 | vLLM | HELD, see below | GPU0 if it wins its heat | 8093 |
| nemotron-embed | llama-nemotron-embed-1b-v2 | 4.7G | vLLM, trust-remote-code | 3.3G measured | either | 8094 |
| nemotron-rerank | llama-nemotron-rerank-1b-v2 | 4.7G | vLLM, trust-remote-code | 3.3G measured | either | 8095 |
| granite-embed | granite-embedding-english-r2 | 573M | vLLM | 1.3G measured | either or CPU | 8096 |
| granite-rerank | granite-embedding-reranker-english-r2 | 575M | vLLM | 1.3G measured | either or CPU | 8097 |
| promptguard | Llama-Prompt-Guard-2-86M | 1.1G | transformers service | CPU-class | either or CPU | 8098 |

**The large code-model pull is HELD.** What landed is a 49G BF16 build that fits neither
card, and before spending the pull the code lane itself goes to a heat: no single campaign
directs the hardware work, so the code lane auditions on tasks drawn from the project
corpora, on-disk candidates first, gate harnesses as graders where they exist. A large
SWE-agent tune built for autonomous issue resolution is a candidate in that heat and not
its presumptive winner; a conducted fabric may not want that tune at all.

## What this contract does not cover

The other nodes' shelves and routing go by the casting doc and the routing law. The face's
residency plan lives in the vessel dossier and `striker-onboarding.md`. This contract
governs one box: how its two cards hold services, take summons, and stay honest as
instruments.

## Open items

1. CLOSED: law 1 ruled; law 2 executed with the at-move measurement pair (92 percent
   shared-card cost retired to zero cross-card) and the embedding-lane fingerprint banked
   in the law text.
2. The code-service heat, portfolio-scoped; the large code-model pull rides its outcome.
3. CLOSED: the vision canary passed, the pinned tag serves sm_120.
4. Cross-card calibration pair: same model, same anchors, both cards, the silicon-boundary
   offset measured before any scored stage may span cards.
5. HALF CLOSED: the small embedding pair's vLLM path is PROVEN by ad-hoc smoke
   (`--runner pooling`, 24s to API, 1.3G each). Remaining: the prompt-guard transformers
   service and serve scripts for the pair when a consumer arrives.
6. Embedder-offset calibration (law 3's gate for routine setlists beside the embedder).
7. CLOSED: the view restarted for the lazy flips (with the pull-before-restart lesson
   honored the second time).

All numbers here are single-run measurements from the sustained and setlist captures named
above. They are reproducible by re-running those captures on the same cards.

Floor: no em dashes, no ellipses.
