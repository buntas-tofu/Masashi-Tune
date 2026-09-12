# Deliberation Schemas

JSON Schema definitions for a small multi-agent deliberation layer. They
validate the YAML frontmatter of identity files (`roster/`, `stances/`,
`playbook/`) and the JSON manifests of live runs (`scrimmage/`).

These schemas are layered on top of the project framework, not part of it.
The governance artifacts at the repository root (`AGENTS.md`,
`agent-manifest.json`, plus their schema) cover how an agent behaves; these
schemas cover how a team of agents works a problem together.

## The four schemas

| Schema | Validates | File pattern |
|---|---|---|
| `agent.schema.json` | Roster member identity (frontmatter) | `roster/<name>.md` |
| `stance.schema.json` | Stance catalog entry (frontmatter) | `stances/<name>.md` |
| `play.schema.json` | Reusable run definition (frontmatter) | `playbook/<name>.md` |
| `scrimmage.schema.json` | Single run manifest (full file) | `scrimmage/<NNNN-slug>/manifest.json` |

Each schema is standard JSON Schema (draft 2020-12) and is written so a
frontmatter block validates as a plain object.

## How they compose

A **scrimmage** is the live unit of work. It references a **play** (the
template), and assigns specific **agents** from the roster to roles in that
play. Each agent has a persistent **stance** that defines how it looks at
things.

```
scrimmage  ->  play  ->  required_stances
   |
roster of agents  ->  each agent has a stance
```

A scrimmage is valid when:

- Its `play` references an existing `playbook/<name>.md`.
- Its `roster` references existing `roster/<name>.md` agents.
- The roster collectively covers `play.roster_requirements.required_stances`.

The `agent-manifest.json` at the repository root lists these schemas under
`agent_contract.schemas` so framework discovery walks them.

## What each directory holds

- `roster/`: one file per agent identity. Frontmatter is validated against
  `agent.schema.json`. The body is the agent's persona statement and any
  overrides on its stance defaults.
- `stances/`: one file per lens. Frontmatter is validated against
  `stance.schema.json`. The body describes how an agent in that stance reads
  the world.
- `playbook/`: one file per reusable run definition. Frontmatter is validated
  against `play.schema.json`. The body describes the protocol, the roles, and
  any prompts beyond the stance defaults.
- `scrimmage/`: one directory per run, named `<NNNN>-<slug>`. The
  `manifest.json` is validated against `scrimmage.schema.json`. Output
  artifacts land under `output/` when the run executes.
- `teams/`: optional, free-form team and role sketches (an arena layer on top
  of the single-team scrimmage model). Nothing here is schema-validated.

## System prompt composition (runtime)

When the orchestrator instantiates an agent for a scrimmage, the system prompt
is composed in layers:

1. The framework GLOBAL contract from `AGENTS.md` (style, register, posture).
2. The stance body from `stances/<stance>.md` (the lens, default probes).
3. The agent body from `roster/<name>.md` (agent-specific persona, any
   overrides on the stance).
4. The scrimmage-specific role assignment from `scrimmage/<id>/manifest.json`
   (what this agent is doing in this run).

Agents are not interchangeable. A `skeptic` instance running a digest
scrimmage is the same identity that ran the previous scrimmage, with continuity
through its memory file at `roster/<name>.memory.md` if declared.

## Versioning

Schemas are at `0.1.0`. Bumping policy: internal-only while the team is small
and the patterns are still emerging. A breaking schema change should land in
the same commit as the migration of every dependent file, so the tree is
always valid.

## Validation

No CI/CD enforces these schemas yet. Validation is the orchestrator's
responsibility on read. When tooling is added, `ajv` or an equivalent plus a
pre-commit hook is the path of least resistance. Each schema also carries a
`$schema` pointer so an ordinary JSON Schema validator can be pointed at any
file directly.
