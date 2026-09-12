# Roster

The team. Persistent agent identities that participate in scrimmages.

Each file is one agent. Each agent has one primary stance (and
optionally secondaries), one backing model, one compute envelope, and
optional persistent memory. Identity is stable across scrimmages: the
same `archaeologist` that worked scrimmage 0001 is the agent
that works scrimmage 0042.

## Files

One markdown file per agent, named in kebab-case. Frontmatter is validated
against `agent.schema.json`. The body is the agent's persona statement
and any agent-specific overrides on the stance defaults; it composes
into the system prompt at runtime, after the stance body.

## Memory files

Optional. When an agent declares `memory.type: persistent` with a path
of `roster/<name>.memory.md`, that file holds its session-spanning
notes. Memory files are markdown with no required structure, written
by the agent itself with orchestrator approval gates.

**Privacy floor.** Agents must not write content drawn from external
read-only inputs into persistent memory without explicit principal
approval. Memory is for the agent's own reasoning continuity, not for
accidentally archiving input data.

## Currently rostered

- `archaeologist.md`, stance: archaeologist, backing: hosted large
- `skeptic.md`, stance: skeptic, backing: hosted large
- `simplifier.md`, stance: simplifier, backing: hosted small
- `pragmatist.md`, stance: pragmatist, backing: local GPU
- `guardian.md`, stance: guardian, backing: command-line session

Three is the floor for the first scrimmage. Add agents as plays demand
new stances or as compute envelopes become available (local models, etc.).

## Adding a new agent

1. Decide whether you need a new agent or a new stance. A new stance
   is a new way of looking; a new agent is a new instance of an
   existing way of looking on different backing.
2. Choose backing type. `hosted` for a remote model API, `local` for a
   local runtime, `cli` for a command-line agent session. Match the
   model class to the cognitive load: a large model for hard reasoning,
   a small model for fast compression.
3. Choose compute. `api` for a remote model API, `local-gpu` / `local-workstation` / `local-mobile` for local. Declare honestly.
4. Write the persona body. Second person, focused on what makes this
   agent distinct beyond its stance.
5. Single commit on a `feat/agent-<name>` branch. PR for review.

## Roster hygiene

- An agent in `status: draft` does not run scrimmages. Promote to
  `active` when the identity is finalized and at least one scrimmage
  has stress-tested the persona.
- An agent in `status: inactive` is on the bench. Reasons might be:
  backing model deprecated, compute unavailable, stance redundant
  with another agent. Inactive agents stay in the roster (history is
  preserved); only `abandoned` agents would be deleted, and we have
  not needed that mode yet.
- Do not silently retire agents. If an agent is being deactivated,
  the commit message should say why.
