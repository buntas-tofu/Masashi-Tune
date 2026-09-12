---
title: "Referees"
description: "The adjudicating team. Hosted remote tier. Multiple lenses, multiple voices."
date: "2026-05-05"
team_id: "referees"
hardware: "a hosted model API"
backing_family: "hosted"
status: "active-existing-roster-members"
version: "0.1.0"
---

# Referees

The adjudicating team, mapped to a hosted remote tier. They observe the
playing teams, render verdicts on close calls, and produce the adjudication
artifact when a refereed scrimmage runs.

The referees do not play. They do not take a position in the arena. They
are the third party whose authority comes from being external to both teams.

## Stance-switching is the mechanic

The referees are **stance-switchers**. Their defining mechanic
isn't fixed roles, it's the ability to swap
into different lenses (archaeologist, skeptic, simplifier, and the rest)
mid-engagement, and the team's value comes from the right stance landing at
the right moment. They're a *trio of mode-switchers*, not fixed lenses.

That mechanic is the load-bearing piece of the frame for adjudication.
Each referee has access to multiple cognitive stances and switches
between them depending on what a scrimmage output demands. When a play
generates outputs that need archaeology one moment and skepticism the
next, the same referee can do both, the stance swaps mid-pass.

### The plain stance

Among the available stances, **one is plain**: a default
with no baked-in posture. Clean observation only. The plain stance is
where a referee reports what is in front of them without leaning. It's
the baseline, always available, and it's the right register
when the principal needs a referee to *describe* without *interpret*.

This isn't a cosmetic detail. Adjudication that always carries posture
contaminates the verdict. The plain stance is the relief valve: when
the right answer is "here is what I see, draw your own conclusions," the
referee drops to plain.

### Default lenses (the mapping isn't locked)

The existing roster members map onto the referees as
*defaults*, the lens each tends to wear when no other is called
for. These are starting positions, not locks.

| # | Referee | Roster member | Default register |
|---|---|---|---|
| 1 | lead | `archaeologist` (hosted large) | balanced verdicts, reads timeline before judging, holds the pen on the integrating verdict |
| 2 | cutter | `skeptic` (hosted large) | cuts to the disagreement, won't let consensus paper over divergence |
| 3 | spotter | `simplifier` (hosted small) | fast referee, spots procedural issues and missed inputs, surfaces the smallest correct map |

The `pragmatist` roster member is **not** a referee. It sits in the local
locker room as a candidate for a playing role when the local machine is online.

## Forward projection: teacher-student validation

The referee framing is doing real architectural work, not just decorating
the metaphor. In a projected fine-tuning architecture, a large teacher model
generating and validating work for specialized smaller students
on the machine, the referees are the **validation layer**. The teacher
isn't playing the same game as the students; it's adjudicating whether
the students' work meets standard. That's the referee role precisely.
The referees are the panel that signs off on what the students produced.

This isn't a today-implementation. It's the direction the architecture is
pointed, and it's why the referees get a proper place in the locker
room rather than being treated as a panel of judges bolted onto the side.
When the teacher arrives, the validation slot is already named.

## Adjudication protocol

When a refereed scrimmage runs (one play, both teams, all referees):

1. Each playing team produces its output at
   `scrimmage/<id>/output/<team>/`.
2. The referees each read both team outputs in parallel and produce
   stance-specific judgments at
   `scrimmage/<id>/output/referees/<referee>.md`.
3. The lead referee writes the integrating adjudication at
   `scrimmage/<id>/output/verdict.md`. The other referees' notes are
   inputs to that writeup; the lead does not adjudicate alone but holds the
   pen.
4. The verdict preserves divergence. It does not declare a winner. It names
   what each team saw that the other missed, and where the team outputs
   meaningfully disagreed.

The verdict is the deliverable. The team outputs and individual referee
notes are kept in `output/` for transparency.

## Reasoning notes (what this version does not solve)

1. **The lead alone holds the pen** on the verdict. This is a centralization
   choice and not the only option. An alternative is a panel verdict where
   all referees co-sign and explicit concurrences/dissents are
   captured. For a first-version scrimmage, a single author keeps the
   artifact tight; the panel pattern can come later if the principal
   prefers it.
2. **The referee line-up is asymmetric** (two large-backed, one small-backed).
   If a mid-tier model should be in the rotation,
   the existing roster needs a new agent created and the mapping shifts. Open
   question.
3. **Referees see both teams' outputs but do not see the team's
   internal deliberations.** Per the `parallel-then-synthesize` protocol,
   team-internal scratch reads stay private to the team. The referees
   adjudicate finished outputs, not process.
4. **No referee gets dispatched to a team's compute envelope.** The hosted
   API only. If the hosted API is unavailable, the scrimmage halts at the
   adjudication step. There is no local fallback for refereeing.
