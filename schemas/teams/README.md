---
title: "Team Arena"
description: "A playing team, an adjudicating team, and a guardian. The competitive frame on top of the locker room."
date: "2026-05-05"
tags: ["multi-agent", "teams", "arena"]
owners: ["maintainer"]
status: "active"
version: "0.1.0"
provenance:
  last_reviewed: "2026-05-05"
  sources:
    - "local docs"
---

# Team Arena

The arena layer sits on top of the locker room. Where the locker room (`roster/`,
`stances/`, `playbook/`, `scrimmage/`) defines who agents are and what they do,
the arena defines how teams of agents compete on the same problem.

## Roles in the arena

Three roles. One plays, one adjudicates, one guards.

| Role | Tier | Hardware | Backing | What it does |
|---|---|---|---|---|
| **heavy team** | team (plays) | a local GPU desktop (unified memory) | local model via a local runtime | The heavyweight team. Deeper reasoning per turn, single-resident on its machine. |
| **referees** | adjudicate | a hosted model API | hosted models | Observe the playing teams' outputs, render verdicts, hold the pen on adjudication. |
| **guardian** | stewards archives | location-flexible (any machine or session that touches cross-team artifacts) | command-line session | Silent steward of cross-team content: the research corpus, `dmf/`, the arena overview itself. Does not play, does not adjudicate, keeps the archives coherent. |

Each role's directory carries its own README:
- [`referees/`](referees/README.md)
- [`heavy-team/`](heavy-team/README.md)
- [`guardian/`](guardian/README.md)

## Why this exists

The locker room already has stances (archaeologist, skeptic, simplifier,
pragmatist) and a play (`digest-drop-box`). What it lacks is a way to express
the natural axis the principal cares about: same problem, two compute envelopes,
two model families, divergent answers, refereed.

A refereed scrimmage in this frame is a play run by both teams in parallel,
with the referees adjudicating. The play stays the same; the implementations
differ. The disagreement is the data.

This subsumes neither the existing stance taxonomy nor the existing play. It is
a cross-cutting frame.

## Engineering note: persona-context isolation

The team-player pattern is **one model on each side serving many
personas**. A single resident model runs every player as different prompt
and parameter configurations of the same weights.

That is correct architecture, but it carries a known failure mode: **state
can bleed across personas if the conductor doesn't reset context between
role changes**. If the model plays one role and then another within the
same conversation context, the second role's responses can inherit the first
role's lines, phrasings, or assumptions. The model has no native sense of "I am now a
different persona", that boundary lives in the orchestrator.

The conductor's invariants for this pattern:
- **Fresh context per persona turn** (or per role change), unless the play
  explicitly calls for a hand-off where prior persona's output is the input
  to the next persona.
- **Explicit role manifest in the system prompt** every turn, not assumed
  from prior context.
- **No long-running per-instance state** that travels with the model. State
  belongs to the scrimmage manifest, the orchestrator, and the referee
  outputs, not in the model's open KV cache.

Consequence: same-team plays that "feel like" parallel agents are actually
sequential model calls with disciplined context isolation between them.
The illusion of parallelism is the conductor's job, not the model's.

## How a refereed scrimmage runs (sketch)

Same play, two implementations, multiple referees:

1. **Pre-game.** Scrimmage manifest declares the play, the two team rosters
   (heavy lineup and light lineup), the referees, and the input.
2. **First half.** Each team runs the play against the input. Outputs land at
   `scrimmage/<id>/output/<team>/`.
3. **Second half.** The referees read both outputs in parallel. Each
   produces a stance-specific judgment.
4. **Final whistle.** A designated referee writes the
   adjudication. Disagreement between teams is preserved. The verdict is which
   team's read was load-bearing for which finding, not "who won."

The point is not victory. It is divergence. Two model families running the same
play surface different angles on the same problem, and the referees name what
each side saw that the other missed.

## Open questions

1. Does the referees' adjudication produce a single verdict or a panel verdict?
   One author alone, or all referees signing?
2. Can the principal step into a guest seat on one side and play a turn
   manually, or is the principal strictly off-field per the existing
   "hands-off operability" project constraint?
3. When does a team win promote a configuration into the roster as a
   permanent player? Avoid configuration sprawl.
