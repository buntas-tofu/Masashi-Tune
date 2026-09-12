# Masashi-Tune

The machine side of a personal genAI practice, published so the work carries receipts: a small multi-model rig you build, serve, measure, and keep.

## What this is

A small sovereign multi-model fabric in a box. Not a product, not a company, not a platform. It is the working shape of one person's practice of running models on hardware they own, in a small cluster they build and keep themselves, and of being able to point at a receipt for every claim the writing in this repository makes.

The claim at the center of the practice is a simple one: the model is the cheap, swappable part. The durable thing is the rig, the discipline, and the record of measurement that survives each quarterly swap of weights. Models change; the method that keeps you from fooling yourself does not. This repository is the rig and the record, published in plain vocabulary so a stranger with some hardware and patience can reproduce the shape, and so the operator cannot quietly fool himself with a good-looking number.

Everything here was exercised on real hardware. Every number quoted in prose is reproducible from a file in the tree. What works is labeled as working; what is unproven is labeled as unproven. The read is meant to be honest rather than impressive.

The repository carries a guard lane, a judgment harness, schemas used as configuration, fleet operations tooling, a bench with its reports, runbooks, serving scripts, and a method shelf. Each piece took a separate lesson to earn, and each is written so the next person does not have to repeat the mistake that produced it.

A few operating laws recur, and stating them up front makes the rest read more plainly. A gap that announces itself is a bug; a gap that does not is a class. An instrument that cannot fail loudly will eventually pass quietly. A failed probe is not an absence. Every instrument reports and never rewrites; the operator judges, the tools hand him something to judge. These are not slogans. They are the conclusions that each losing week produced, and the design decisions in this repository are their echo.

## Layout

- `guard/` the injection lane: a two-tier screen for a model that reads uncontrolled third-party text. The first tier is a small always-on classifier; the second is a reasoner that wakes only for what the classifier cannot decide. Both report, neither rewrites input. The screen slides overlapping windows across a whole document so an injection straddling a boundary is still seen whole. The corpus and its provenance live here too, re-authored from clean sources rather than scrubbed from contaminated ones.
- `harness/` the judgment harness: a small Python package that runs batch, judge, self-test, and red-team lanes against a model endpoint. It carries its own test suite, and that suite runs with no model attached, which is the offline-safe proof that the package works.
- `schemas/` JSON Schema for the deliberation layer: roster, stances, playbook, and scrimmage run manifests. These layer on top of the governance artifacts at the root, and they are the machine-readable shape of how a team of agents works a problem together.
- `ops/` fleet operations: read-only gates and collectors. A drift gate checks whether recorded units match what is installed, a liveness gate asks the question the drift gate cannot, whether the recorded unit is actually running, a host profile collector inventories the machine, and a compromise-assessment collector walks trust outward from the baseline. Every instrument reports and never rewrites.
- `bench/` the measurement presence: bench instruments, their run scripts, and the reports that read in date order as one narrative of measurement discipline. An instrument is built, then found contaminated, then rebuilt until it discriminates, then a second lane catches the first lane's own blind spot. The reports name the manifest that produced each run, so a stranger can rerun the shape against any endpoint.
- `runbooks/` the operational shelf: step by step guides for building and keeping the rig, the ones a stranger follows to build the same thing and the operator reads at 2am when a node will not come back. Hardware is described by class, never by name, so the numbers are that rig's measurements and the reader substitutes their own.
- `serve/` the serving lane: one launch script per model vessel, a thin wrapper setting neutral defaults and handing them to a real llama.cpp or vLLM binary. Ports, model paths, the binary, and any GPU pin are environment variables with documented defaults, so the same script runs on any box with the weights staged.
- `method/` the method shelf: written lessons from building, keeping, and publicly releasing this fabric, de-identified and told in plain vocabulary. The fullest entry is how private work was swept for public release in waves and the gates it had to pass.
- `scripts/` the bundled invariant linter, a faithful copy of the framework linter, plus anything that is a single self-contained tool rather than a package.
- Root files: `AGENTS.md` holds the agent contract, `agent-manifest.json` and its schema carry the machine-readable summary, and `LICENSE` carries the MIT terms.

The discipline across all of it is the same: one tool, one job, one self-test. Every deployment-specific value is a parameter with a documented default, never a hardcoded name or path. Numbers are reproducible from files in the tree, or they are not quoted.

## The bench reports

The reports in `bench/reports` are meant to be read in date order, as one long exercise in not fooling yourself. The arc is worth knowing before you open the files.

The first instrument is built and run, and its own operation turns up the contamination that invalidates the result: what looked like a model failing at the extremes was an anchor leaking into the read. The instrument is rebuilt until it discriminates, and a ladder of specialist models is measured across rising context. A gauntlet then finds the hard truth: failure is loud at the extremes and silent in a narrow band, so the instrument that cannot fail loudly will eventually pass quietly. A sustained-load run and a tool-lane run extend the measurement to load and agentic latency. A later characterization run reads a specific model family in depth, and separate lanes measure face and fidelity, prefix survival, and graded relevance.

Each report is a status line, then the numbers, then the method and the run manifest behind them. Read the status line first. It states what the report is, what it is not, and who may act on it, in the same breath as the figures.

Representative titles, so the naming stays legible without opening every file:

- `ANCHOR_CONTAMINATION_2026-08-04.md`, the contamination postmortem that started the arc.
- `LADDER_2026-08-04.md` and `SPECIALIST_LADDER_2026-08-04.md`, the context and specialist measurement ladders.
- `GAUNTLET_2026-08-05.md`, the phased-variation run that found the silent band.
- `FACE_BENCH_2026-08-07.md`, the first face bench, one instrument, one reader, two reads, agreement beside the verdict.
- `SUSTAINED_2026-08-04.md` and `DEEPSEEK_V4_FLASH_CHARACTERIZATION_2026-08-22.md`, a load run and a model family characterization.

## Quick start

The repository is offline-safe in the specific sense that the parts proving the code works run anywhere, with no model and no GPU required.

- Every self-test runs against no model at all, on any machine with Python 3.11 or newer. The harness carries its own self-test lane by design and needs only its one declared dependency, `httpx`. A fresh clone is expected to come up green, which is the launch bar this project holds itself to.
- The invariant linter at `scripts/inertia-drift-lint` is pure standard library. It lints the repository for the style floor and the governance shape, and it runs anywhere, with no dependencies to install.
- The `ops/` gates and collectors run read-only against the local machine and need nothing beyond the standard library.

What is not offline-safe: the model-backed benches and the serving scripts. Those need you to point them at a model. The bench instruments read a model endpoint over HTTP, so you bring your own weights. The serving scripts are thin wrappers over a real llama.cpp or vLLM binary, so you bring the binary and the weights.

In both cases the code in this repository is exercised and the wiring is documented; the model itself is never shipped here, by design. The tree stays text and code, small on purpose. Models and corpora live outside the repository, and guests run offline with their model store mounted read-only.

What you need, depending on what you want to do:

- Read only: nothing. The runbooks, method, and reports are plain markdown.
- Run the self-tests and the linter: Python 3.11 or newer. The linter is standard library, no install; the harness needs its one declared dependency, `httpx` (`pip install httpx` is the lightest path; installing the package from `harness/` also fetches its build backend).
- Run the ops gates: one Linux box, standard library, nothing else.
- Run a model-backed bench: whatever serves an OpenAI-shaped endpoint, weights staged, and one GPU will do for a single model.
- Stand up the full rig: the runbooks describe the hardware classes; read `node-onboarding.md` first.

To start: clone the repository, run the harness self-tests (`cd harness && python -m harness selftest`), lint it with `scripts/inertia-drift-lint`, and read `runbooks/node-onboarding.md` if you intend to stand up the rig itself. The governance workflow in `.github` runs the same linter, validates `agent-manifest.json` against its schema, and runs the harness self-tests, on every push to main.

## Working here

The conventions for changing this repository are written down in `AGENTS.md`, and they are simple enough to restate.

- One tool, one job, one self-test. A new tool lands with its own self-test, and the self-test runs with no model attached.
- Configuration is TOML with annotated examples. Every deployment-specific value is a parameter with a documented default.
- Runbooks live in `runbooks/`. A change that touches a gate or a bench instrument lands as one commit with its receipt, so the source of any number stays traceable to the change that produced it.
- The launch bar is every self-test green on a fresh clone. Nothing is released against failing self-tests, and no gate or bench test is weakened, skipped, or reordered to make it pass.
- Third-party material arrives with a recorded license disposition or not at all. The tree ships no secrets and no second-party material.
- Numbers quoted in prose are reproducible from a file in the tree. A number without a committed input does not get quoted.

None of this is ceremony. Each rule is the trace of a specific week the operator lost to its absence, and the rule exists so that week does not recur.

## A note on two words

Two words here are chosen, not accidental, because they carry the work.

- A seat is a named position: a role cast to a model, with an identity, a place in the roster, and limits on what it may serve. Seats persist across model swaps. The chair outlives the player.
- A vessel is a model in serving condition: weights staged, a binary wrapped around them, a port open. The same weights under different flags are a different vessel. A vessel can be woken, rested, or reserved.

The names come from the three teachers this practice runs on. The band gave the seat: Count Basie's orchestra, where sections hold their form while the players move through them. The water gave the vessel: Bruce Lee's instruction to be water, which takes the shape of whatever holds it, the way a model takes the shape of its serving. And Stevie gave the reason: everything here exists to deliver, and delivery deserves soul.

Hold the form. Move like water. Play it with soul.

## What is proven, and what is not

Proven: the harness self-tests are green, and the linter passes on this tree. Both run in CI on every push to main, and both run clean in a fresh clone, which is the launch bar the project holds itself to. The `ops/` gates and collectors have been run against a live multi-node rig, and their findings match what the rig actually reported. The serving scripts have launched the vessels they describe on the hardware the runbooks describe.

Not proven, plainly: some bench numbers trace to run tapes that are not shipped. The reports record the numbers and the method, but the raw untracked tape that produced every figure is not in the tree, so a reader cannot rerun every bench end to end from this repository alone. The honest statement is that the reports are reproducible in method, and the aggregate numbers are not independently reproducible from committed inputs yet. That is a known gap, recorded rather than hidden.

Also not proven: the model-backed benches and the serving scripts need weights and a GPU, so they are not exercised in a fresh clone. The code paths that do not need a model are tested; the paths that do need a model are exercised only where hardware and weights exist. Treat the model-dependent lanes as working-shape guides rather than as verified against your environment until you run them yourself.

If you read the reports expecting every claim to be independently re-derivable from this repo alone, you will find places where it is not. That is the line the project draws between what it asserts and what it merely records.

## Boundary

Some things stay out of this repository by design, and the list is worth stating because each item is deliberate.

- Models and corpora. They are large, they are not the author's to license, or both. The repository holds text and code only, and the serving lane points at weights the operator stages outside the tree.
- Credentials of any kind. Nothing in the tree holds a secret, a token, or a path that names where one lives. The ops gates refuse to record credential-looking bodies even when asked.
- Names that identify a machine or a person. Hardware is described by class, deployment values are parameters, and the operator's legal name appears only in the copyright line of the license, which the law requires.
- Raw private evidence. The method shelf ships lessons, not logs. The narrative of an incident that names people or a workplace stays home; the transferable rule ships.

This boundary is what makes the repository publishable. Architecture generalizes; the person does not ship.

## Governance

This repository is governed by [Inertia-Drift-Framework](https://github.com/buntas-tofu/Inertia-Drift-Framework):
`AGENTS.md` carries the principal contract and this project's layer,
`agent-manifest.json` is the machine-readable summary, and the invariant
linter plus schema validation run in CI on every push.

Note: the bundled `scripts/inertia-drift-lint` is a faithful copy of the
framework linter; it deliberately still recognizes the legacy `CLAUDE.md`
contract filename so that pre-rename adopters lint correctly. That string is
a compatibility affordance, not this project's naming.

## License

MIT, covering both code and documentation. See `LICENSE`.

The copyright line in `LICENSE` carries the operator's legal name, because the license requires a copyright holder. The name is otherwise treated as private, and it is not used as an identity anywhere else in the tree.

## Lineage

This repository adopts the Inertia-Drift-Framework as its governance stack, per `AGENTS.md`. Its companion repository is Shigeno, the memory side: the architecture and laws of a persistent memory substrate that holds continuity and identity across model swaps. Together the two are the machine and the memory of the same practice, kept separate because the machine is tooling and the memory is architecture, and each publishes on its own terms.