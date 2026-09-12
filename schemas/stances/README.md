# Stances

The catalog of ways an agent can look at things. Each stance is a
persistent lens, not a task. Agents are typed by stance, not by
function: a `skeptic` can review architecture, code, a research drop
box, or a dinner plan, and the same lens applies.

## Files

One markdown file per stance, named in kebab-case
(`stances/skeptic.md`, not `stances/Skeptic.md`). Frontmatter is
validated against `schemas/stance.schema.json`. The body is the
stance's ethos and default probes; it composes into the system prompt
at runtime, after the DMF GLOBAL contract and before agent-specific
persona text.

## Currently catalogued

- `archaeologist.md`, looks at lineage, layers, supersession
- `skeptic.md`, looks at the load-bearing assumption
- `simplifier.md`, looks at the smallest correct map

## Adding a new stance

1. Decide if the new lens is genuinely distinct from existing stances
   or is a flavor of one. Stance proliferation erodes value; resist
   adding when an existing stance covers it.
2. Write the file. Body in second person (it becomes part of the
   system prompt). Include default probes the stance asks.
3. Update `compatibility.conflicts_with` and `pairs_well_with` on
   neighboring stances if the new stance changes pairing dynamics.
4. Single commit on a `feat/stance-<name>` branch. PR for review.

## Composition rules

When a play's roster requirements list multiple stances, the
orchestrator should ensure the assigned roster does not include two
agents whose stances appear in each other's `conflicts_with` list.
This is one of the few hard validation checks the framework enforces.
