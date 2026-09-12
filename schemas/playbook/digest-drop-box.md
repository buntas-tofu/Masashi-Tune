---
$schema: ../schemas/play.schema.json
name: digest-drop-box
description: Take a chaotic working directory that has accumulated mixed-vintage artifacts (drafts, canon, exports, references) and produce a structured digest. Three stance-typed reads in parallel, then a synthesis pass.
input_type: directory
output_type: report
roster_requirements:
  min_agents: 3
  max_agents: 5
  required_stances:
    - archaeologist
    - skeptic
    - simplifier
  recommended_stances:
    - pragmatist
protocol:
  type: parallel-then-synthesize
  synthesis_role: designated
  max_rounds: 1
  halt_on_consensus: false
review:
  required: true
  mechanism: pr
default_compute:
  device: any
  tier: api
created: 2026-04-25
tags:
  - digest
  - founding-play
status: active
---

# Play: digest-drop-box

A "drop box" is a directory that has accumulated artifacts over time
without active curation: mixed drafts and canon, multiple versions of
the same document, exports from various tools, reference material,
research notes. The digest play takes such a directory and returns a
structured map.

## When to use

- A directory has 30+ files and you cannot tell what is in it from
  filenames alone.
- Multiple versions of the same artifact coexist and supersession is
  unclear.
- The directory has been a passive collection point and a decision
  is needed about what to keep, archive, or act on.

## When NOT to use

- The directory is small (under 10 files). Read it directly.
- The directory is actively maintained and the current state IS the
  truth. No archaeology needed.
- High-precision work where the simplifier's compression would lose
  load-bearing nuance. Use a different play.

## Protocol

`parallel-then-synthesize`. Three readers work the directory
independently from their respective stances; one designated
synthesizer integrates their reads.

1. **Phase 1 - parallel reads.** Each reader (archaeologist, skeptic,
   simplifier) walks the directory and produces a stance-specific
   read. The three reads are written to scratch and not exposed to
   each other during this phase. Each read lands at
   `scrimmage/<id>/output/reads/<stance>.md`.
2. **Phase 2 - synthesis.** The synthesizer reads all three parallel
   reads and the directory itself, then produces a single integrated
   digest at `scrimmage/<id>/output/digest.md`. The synthesizer
   preserves disagreement: when two stances diverge on a point, the
   synthesis names the divergence rather than blending it into false
   consensus.

## Roles

- **reader** (one per required stance, three by default): performs the
  stance-specific read on the directory.
- **synthesizer** (one agent): integrates the parallel reads. Default
  cast is whichever roster member holds the simplifier stance, since
  compression is the simplifier's native job. The simplifier doubles
  up: it does its parallel read first, then synthesizes.

A scrimmage manifest may override the default synthesis cast (e.g.,
adding a fourth agent dedicated to synthesis). Such overrides should
be justified in the manifest's `notes`.

## Output

A single markdown report at `scrimmage/<id>/output/digest.md` with
these sections:

1. **Inventory.** The directory's contents organized by topic, not
   by filename. Pointer to filenames for each grouping.
2. **Lineage.** What supersedes what. Surfaces version chains and
   abandoned drafts. Owned by the archaeologist read.
3. **Load-bearing claims and where they sit.** Tier-graded claims
   with evidence pointers. Owned by the skeptic read.
4. **The smallest correct map.** Two-paragraph compressed take on
   what this directory is actually about. Owned by the simplifier
   read and the synthesis.
5. **Stance divergences.** Points where the three reads disagreed,
   preserved without resolution. The synthesizer names each
   divergence and the disagreement; does not adjudicate.
6. **Recommendations.** Keep, archive, or act-on, with a one-line
   rationale per item. Each recommendation is tagged with which
   stance generated it.

The three parallel reads are also kept under
`scrimmage/<id>/output/reads/` for transparency. They are not the
primary review artifact but they are referenced from the digest.

## Halt conditions

- Halt if the directory contains files with live credentials, secrets,
  or third-party PII that the scrimmage manifest did not flag. Surface
  to principal before continuing.
- Halt if lineage is unresolvable AND the unresolved branch is
  load-bearing for a recommendation. Surface to principal before
  shipping the digest.
- Halt if the directory is dramatically larger than expected (e.g.,
  declared 70 files, actually 700). Surface and request scope
  confirmation.

## Review

PR-based. Branch `scrimmage/<id>`. The synthesizer's `digest.md` is
the deliverable; the three parallel reads are kept in
`output/reads/` for transparency but are not the primary review
target.

## Known cost shape

For a directory of approximately 70 mixed-vintage files:

- Parallel reads: 3 agents times a directory walk = 3x context-window
  pressure. Use a large model for archaeologist and skeptic
  if available; a small model is sufficient for simplifier.
- Synthesis: reads three reads + selective directory re-reads.
  Lower context burden than the parallel phase.
- Total: comfortable inside one large-model context window per agent if
  the directory is digest-shaped (markdown / docx / PDF, not video
  or large binaries). Halt if input balloons past this envelope.
