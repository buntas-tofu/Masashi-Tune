---
title: "Heavy Team"
description: "The heavyweight-param team. A local GPU desktop. Local model backing."
date: "2026-05-05"
team_id: "heavy-team"
hardware: "a local GPU desktop"
backing_family: "local"
status: "captain-online-rest-as-configurations"
version: "0.1.0"
---

# Heavy Team

The heavyweight-param team on a local GPU desktop. They run on a
unified-memory SoC via a local runtime. A large resident model
backs every position currently on the field. The frame carries on
parameter count (a large model versus the lighter team's smaller models)
and kernel maturity. It does **not** carry on memory
budget: both sides have comparable unified memory, so the lighter team isn't
memory-poor, it's param-fewer.

A second resident model is parked: its weights are on
disk but coresident with the primary model triggers an OOM on
unified memory, because the primary model's physical footprint exceeds its
nominal GPU memory budget on aarch64. Until a second accelerator
arrives, the parked model is shelved and the team is a one-model team with
several configurations.

## Lineup

Seven positions, all the large resident model with different prompt and
parameter profiles. Configuration as identity for now.

| # | Position | Role | Model config |
|---|---|---|---|
| 1 | Captain (ace) | dominant ace, deep reasoning on every play | thinking-mode-on, temp 0.6, top_p 0.95 |
| 2 | Forward | secondary striker, faster decision than the captain | thinking-mode-off, temp 0.6, terse system prompt |
| 3 | Midfielder | balanced playmaker, the default voice | no role override, defaults |
| 4 | Midfielder | counter to the default voice, more conservative | cautious system prompt, temp 0.4 |
| 5 | Midfielder | utility, fills role gaps a play creates | utility prompt, adapts to instruction |
| 6 | Defender | quality control on the team's output | critic-oriented prompt, evaluates teammates' work |
| 7 | Goalkeeper | strict last-line safety | strict-skeptic prompt, halts on policy concerns |

### Stance overlay

The lineup against the existing stance taxonomy:

- **Captain** holds a `captain` stance (a lead stance, mirrors the other team's lead).
- **Forward** is closest to `pragmatist` (fast practical takes).
- **Default midfielder** is base / no stance (the default voice).
- **Cautious midfielder** maps to a softer `skeptic`.
- **Defender** is the closer fit for `skeptic` proper (adversarial review).
- **Goalkeeper** is the hardest `skeptic` (will halt the team).
- **Utility midfielder** has no fixed stance; it takes whatever
  stance the play needs filled.

## Machine context

- **Hardware**: a local GPU desktop, unified memory, ARM64
- **OS**: Ubuntu LTS
- **GPU runtime**: a current CUDA release
- **Resident model**: a large model served by a local runtime on loopback
- **Parked model**: a second large model (weights on disk, not running due to
  coresident OOM; lives on a second accelerator when it arrives)
- **Workspace**: a workspace tree; the schema set is this repo

## How a player is invoked

The players are reachable through the same OpenAI-compatible endpoint
on loopback. The differentiator is the system prompt and sampling config the
caller provides. A scrimmage manifest names the player role; the conductor
composes the corresponding system prompt plus sampling profile and dispatches
to the runtime.

Cost shape: each player turn is one model inference. At the configured max
model length and the current GPU memory budget, KV cache is sufficient for
plausible multi-turn play but not unbounded. Long scrimmages should chunk.

## Reasoning notes (what this version does not solve)

1. **A single resident model serves all positions.** Until a second
   resident model is online, every voice is the
   same model under different instructions. The "forward is faster than
   the captain" claim above is *prompt-true* but not *backing-true*; both are
   the same network running with different generation knobs.
2. **No genuine intra-team disagreement.** Same model running with different
   prompts produces correlated answers. The two-team axis is where
   the real divergence lives in this version. Once the parked model is back,
   intra-team disagreement becomes meaningful again.
3. **Concurrent players on a single endpoint are sequential, not parallel.** The
   runtime batches requests, but a play that calls four players in parallel will
   see them serialized at the wire layer. Throughput is fine; wall-clock
   parallelism is illusory at the moment.
4. **Some model families are out** by principal preference, regardless of fit.
