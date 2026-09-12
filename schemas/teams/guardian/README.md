---
title: "Guardian"
description: "The guardian. Cross-team archivist. Lives off-field."
date: "2026-05-05"
role_id: "guardian"
tier: "guardian"
team_id: "guardian"
hardware: "any (location-flexible)"
backing_family: "cli"
status: "active-as-role-draft-as-roster-entry"
version: "0.1.0"
---

# Guardian

The guardian. Not on a team. Not in the referee booth. Lives in the back
office of the arena, where the cross-team archives are kept.

This file is the **role-tier overview** for the guardian role. It exists
as a parallel to `teams/referees/README.md` (the referee tier overview).
The actual locker-room artifacts live where they belong:

- **Stance:** [`../../stances/guardian.md`](../../stances/guardian.md):
  the lens (archive integrity at workspace scope).
- **Roster:** [`../../roster/guardian.md`](../../roster/guardian.md):
  the first guardian agent. Backing is a command-line session; compute
  device is `any`. Status: draft until a first guardian-mode
  scrimmage promotes the role.

## Beat at a glance

The guardian stewards cross-team content that doesn't belong to any single
team's locker room:

- the research corpus, and cross-team reference docs.
- `dmf/`, the framework both teams' AGENTS.md inherit.
- `teams/README.md`, the arena overview.
- Any future cross-team manifest, schema, or reference index.

Teams play. Referees adjudicate. The guardian keeps the archive coherent.

## Why the role gets a tier overview when it's already in roster + stances

Same reason `teams/referees/` exists despite each referee
having its own roster file: the **role-tier story** is bigger than any
single agent. Referees are a tier with several named members.
The guardian is currently a tier of one but designed to grow if the archive
demands it.

The role-tier overview is the place where role-tier stories live. The
roster file is where the specific agent identity lives. The stance file
is where the lens lives. Three layers, no duplication: this overview
points at the others rather than restating them.

## Reasoning notes

1. **Single guardian for now.** No second guardian
   yet. If the archive grows beyond one guardian's reasonable beat (e.g.,
   separate research and ops corpuses, or shared spaces between specific team
   pairs), additional guardians get named.
2. **Authority boundary between the guardian and the referees is blurry on
   the page.** In practice: the guardian stewards the corpus; the referees
   adjudicate scrimmage outputs. Edge cases (a scrimmage produces a new
   index file for the corpus) get resolved by halting and asking the
   principal, not by guessing.
3. **The first observable guardian operation predates this file.** An
   earlier local session that renamed a reference file and expanded its scope
   was operating in guardian mode without the role being named. Naming the
   pattern retroactively is honest.
