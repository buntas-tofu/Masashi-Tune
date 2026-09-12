# Scrimmage 0001: Digest the sample notes folder

| Field | Value |
|---|---|
| Status | `draft` (awaiting principal approval) |
| Play | `digest-drop-box` |
| Branch | `scrimmage/0001-sample-digest` (not yet created) |
| Created | 2026-04-25 |

## What this is

A worked example of the first scrimmage. It is an end-to-end test of the
parallel-then-synthesize protocol on a small, fully synthetic input: a
folder of fictional documents (`examples/sample-notes/`) that stands in
for a drop box. The folder holds a short version chain of one reference
document plus two dated meeting notes.

The deliverable is a single structured digest of the folder:
inventory, lineage, claim grading, smallest-correct-map, stance
divergences, and recommendations.

No real corpus is referenced. The example exists to show the shape of a
scrimmage manifest and its output tree.

## Roster cast

| Agent | Role | Stance | Backing |
|---|---|---|---|
| `archaeologist` | reader | archaeologist | hosted large |
| `skeptic` | reader | skeptic | hosted large |
| `pragmatist` | reader | pragmatist | local model |
| `simplifier` | synthesizer | simplifier | hosted small |

`simplifier` doubles up: it performs the simplifier read in
parallel with the other readers, then synthesizes all the reads. This
is the digest-drop-box play's default synthesis cast.

## Why this is a good first scrimmage

It exercises every part of the locker room. Four stances, two
backing classes, one play with a non-trivial protocol, small synthetic
input, PR-based review fit for mobile. If this works end-to-end, the
framework holds.

It is also low-stakes in the right ways: input is read-only, output
is a markdown report, no production system is touched, and the
principal can reject the digest without losing anything (the source
folder is untouched).

## Halt conditions specific to this run

- **Surprise content.** Halt if the folder read surfaces files the
  manifest did not flag.
- **Scope balloon.** If the folder turns out to be dramatically larger
  than expected (e.g., hundreds of files instead of a handful), halt and
  confirm scope before reading.

## Open questions before execution

These need principal answers before status can move from `draft` to
`ready`:

1. **Status promotion.** This scrimmage is at status `draft`. The
   orchestrator will not promote to `ready` without an explicit
   green-light from the principal.
2. **Branch creation.** The branch is created only when status moves to
   `ready`.

## Estimated cost shape

Three hosted-model reads (archaeologist, skeptic, simplifier) and one
local-model read (pragmatist). A handful of mostly-markdown files fits
easily inside one context window per reader. The synthesis pass reads
the short reads plus a selective re-read of the folder.

## Output preview

When this scrimmage executes, the output tree will look like:

```
scrimmage/0001-sample-digest/
├── manifest.json
├── README.md           # this file
├── log.md              # execution trace
└── output/
    ├── digest.md       # primary deliverable
    └── reads/
        ├── archaeologist.md
        ├── skeptic.md
        ├── pragmatist.md
        └── simplifier.md
```

The PR will deliver the entire `output/` tree. The reviewer can read the
digest first and dive into the parallel reads if a finding looks
worth pressure-testing.
