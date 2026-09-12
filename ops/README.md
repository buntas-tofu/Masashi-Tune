# ops: fleet operations

Read-only fleet operations tooling, plus the shell wrappers that drive it. One
tool, one job. Every deployment-specific value (node lists, hostnames, home
paths, endpoints, mount points) is an environment variable with a documented
neutral default.

## Gates and collectors

- `unit_drift.py`, `unit_liveness.py` - whether recorded units match and run.
- `machine_profile.py` - host inventory.
- `compromise_watch.py` - compromise-assessment collector.
- a storage collector and its reconciler, with an example ledger (its own
  subdirectory; see the tree).
- `scripts/` - the six small gates (claim verification, context inventory,
  event correlation, memory hygiene, serving summary, topology validation).

## Fleet shell wrappers

- `fleet-apt.sh` - package currency across the fleet. `FLEET_NODES` lists the
  ssh aliases; the serving stack (kernel, NVIDIA, CUDA, ROCm) is held back so a
  plain upgrade cannot desync a running driver.
- `gpu-claim` - claim an accelerator back from the fabric, or hand it over.
  Talks to this node's keeper over HTTP, nothing else.
- `gpu-game` - run a program with a card to itself and give it back after.
- `heat-run` - run one campaign step and capture it whole. `HEAT_ROOT` holds the
  raw artifacts; `CAMPAIGN_LOG` names the index file.
- `mirror_bares.sh` - mirror every git bare to a backup store, fsck each one,
  write a receipt. `HUB`, `SRC`, `NAS_MOUNT`, `DST`, `LOGS_DIR` parameterize it.
- `node-onboard.sh` - one-stop onboarding for a new lightweight node. `KIT_URL`
  points at the host serving the kit artifacts.
- `pull-zoo.sh` - fill the model shelf from a curated pull list. `ZOO_DIR` and
  `HF_BIN` parameterize it.
- `git-hooks/pre-commit` - generic pre-commit checks (invariant linter, config
  and golden test in the same edit). Install per clone:

      ln -sf ../../ops/git-hooks/pre-commit .git/hooks/pre-commit

## Model-card tooling

- `zoo/` - the model-card gate and its companions:
  - `zoo_drift.py` - did a watched upstream card change, and does the local copy
    still match what upstream publishes (`ZOO_STORE_ROOTS` lists local copies).
  - `community.py` - what the field already knows about a model, into dossiers.
  - `hf_survey.py`, `hf_cards.py` - public Hub surveys.
  - `ledger_check.py` - the disposition gate over `ledger.toml`.
  - `watchlist.toml`, `sources.toml`, `ledger.toml` - example configuration.
  - `dossiers/` - example dossiers showing the shape the tools write.

## Node onboarding

- `node-onboarding/kitting-node.sh` - bring one fresh node from bare Linux to a
  fabric-joined box: OS baseline, identity, packages, clone, venv. Idempotent.
