# Scrimmage

Live and recent scrimmage runs. One directory per run, named with a
zero-padded ordinal and a kebab-case slug:

```
scrimmage/<NNNN>-<slug>/
```

## Anatomy of a scrimmage directory

```
scrimmage/0001-some-slug/
├── manifest.json    # validated against schemas/scrimmage.schema.json
├── README.md        # human-readable overview of THIS specific scrimmage
├── log.md           # run-time trace; written during execution
└── output/          # produced artifacts; populated when scrimmage runs
    ├── digest.md    # primary deliverable (varies by play)
    └── reads/       # per-agent intermediate work (optional, play-dependent)
```

`output/` is created during execution, not at scrimmage manifest
creation. Empty directories are not committed.

## Lifecycle

```
draft → ready → running → review → merged
                            ↓
                       (or: changes_requested → ready)

                       abandoned (terminal, kept for history)
```

| Status | Meaning | Orchestrator may execute? |
|---|---|---|
| `draft` | Manifest exists, principal has not approved. | No. |
| `ready` | Principal-approved. Awaiting orchestrator pickup. | Yes, when picked up. |
| `running` | In progress. Orchestrator owns the branch. | Already executing. |
| `review` | Outputs produced. PR open. | No, awaiting review. |
| `changes_requested` | Principal asked for revisions. | Yes, in revision mode. |
| `merged` | PR merged. Scrimmage closed. | No, terminal. |
| `abandoned` | Will not run. Kept for history. | No, terminal. |

Status transitions are commits. When the principal approves a draft
scrimmage, the orchestrator updates the manifest's `status` and
commits.

## Branches

Each scrimmage runs on its own branch: `scrimmage/<id>`. Output
artifacts land on that branch. The PR brings them to `main`.

The branch is created when status moves from `draft` to `ready`. Until
then, the manifest lives on `main`.

## Currently in flight

- `0001-sample-digest/` (status: draft, awaiting principal review)
