# Playbook

Reusable scrimmage definitions. Each play is a template: an input
type, an output type, a required roster shape, and a protocol.
Scrimmages are instances of plays, with specific input paths and
specific agents cast into roles.

## Files

One markdown file per play, named in kebab-case
(`playbook/digest-drop-box.md`). Frontmatter is validated against
`schemas/play.schema.json`. The body holds the play's protocol
description, role definitions, and any prompts beyond stance defaults.

## Currently catalogued

- `digest-drop-box.md`, take a chaotic directory, produce a structured
  digest via parallel-then-synthesize over three stances.

## Adding a new play

1. State the input type and output type clearly. If you cannot, the
   play is not yet shaped.
2. State the roster requirements (min/max agents, required stances).
   Resist over-specification; one or two required stances is usually
   right.
3. Choose a protocol. The five available are `parallel`,
   `parallel-then-synthesize`, `sequential`, `debate`, `round-robin`.
   Default to the simplest one that produces the value you want.
4. Define the output shape. What sections does the deliverable have?
   What halt conditions trigger halts?
5. Single commit on a `feat/play-<name>` branch. PR for review.

## Play hygiene

- A play is reusable. If it only ever runs once, it should not be a
  play; it should be a one-off scrimmage with an inline definition.
- Plays should have at least two scrimmage runs before they're
  considered stable. The first run will surface ergonomics issues
  no amount of design catches.
- When a play's protocol changes meaningfully, version it. Old
  scrimmages keep their reference to the old play file via git
  history; new scrimmages reference the new file.
