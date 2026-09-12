# Runtime cutover: moving a live fabric to a new layout

How to move a running multi-node fabric from one repository layout (or home directory,
or mount) to another without regressing what is live. This is the playbook the rig was
actually migrated with, generalized.

The migration this documents is deliberately not a rename. A working fabric accumulates
three kinds of path dependency, and each is cut over differently. Confusing them is the
standard mistake.

## The three grounds

1. **A shared model mount.** Large weights and engine builds often live on a stable
   mount shared by several nodes (`/srv/fabric` here), separate from the code tree. The
   services serve from this mount by decision, so moving multi-gigabyte weights buys
   nothing and risks much. Recommendation, and what was done: KEEP the mount. Cut over
   only the python packages and the configs.
2. **Per-node control-plane venvs.** The keeper, the registry, the view, and the
   recorder run from a venv per node, with the repo's own packages installed editable
   from a path inside that node's home. These move, and the move is the whole hazard:
   see the venv rule below.
3. **A containerized service.** One node may run a model in a container outside all
   three trees, invoked by an absolute path. It is its own world; leave it alone and
   note it as out of scope.

## CRITICAL, gates everything else: capture before you cut

Before any repoint: find every place the live tree has diverged from the recorded
origin, and snapshot it to a named directory. On the real migration, the head node's
live tree was three commits behind the merged main **and dirty**, carrying three pieces
of work that existed in git nowhere: a rewritten service prompt, a stream-layer style
filter, and a tool-scope change. A `git checkout` or `reset --hard` would have destroyed
all three, and cutting that node over before folding them in would have silently
regressed the live fabric.

The fold, once the diffs are reviewed:

```
cp <snapshot-dir>/{prompt,streaming,tools}.py  <repo>/<pkg>/
cd <repo> && git checkout -b fold-live-handpatches
git add <repo>/<pkg>/{prompt,streaming,tools}.py
# review, commit, PR, merge. Then the node can cut over without regressing.
```

Snapshot every node's live tree the same way, not just the head node. On-node `.bak`
copies beside the originals are cheap and worth having too.

## Also before the cut: close any floor inconsistency first

In the same session, check whether every node is actually running the current version
of the access-control code. On the real migration the head node had a deny-by-default
hard stop that two other nodes' keepers did not: 43 lines behind, the exact delta of
the control. On those nodes a credential file inside an allowed root was not refused.

It was bounded (own nodes, overlay only, not on fire) but it is exposure, not
housekeeping, so it goes **before** the cutover. Close it one node at a time: copy the
current file to the served package, restart that node's keeper, verify a denied path is
refused.

## Per-node state, taken read-only first

Record, per node, before touching anything:

- what each unit runs from, and which venv path it names;
- which packages are installed editable, and from where;
- which units are enabled versus started-only;
- any node that is already partially migrated (one node was ahead of the others on the
  real cutover, because the migration had been running for weeks).

## Decisions a cutover has to make

1. **The shared mount.** Keep or re-home it. Keep (above).
2. **Editable installs and the venv path.** After the repo is present on a node,
   reinstall the repo's own packages editable into that node's venv. Standardize the
   venv path across nodes while you are in there, rather than leaving one path per node.

   **Amended after the real cutover, and this step was missed on the primary
   workstation.** The list of editable packages is longer than it looks: a third package
   beyond the two obvious ones was installed as an editable on two nodes, and the
   primary workstation had neither of the two, because its venv had been rebuilt from a
   requirements file that lists third-party dependencies only. The fabric's own packages
   are not in that file, and nothing checked. The failure mode is silent, because nothing
   on the node had imported them yet. It surfaced days later when a batch job ran and the
   import failed.

   **Onboarding step for every node:** after the venv rebuild, install the repo's own
   packages editable and then IMPORT them to prove it. A requirements file that lists
   only third-party dependencies will always look complete.
3. **The data sink.** If one node writes telemetry to a legacy path, either keep the
   override through the cutover and port it later, or delete the override and let the
   node fall back to the shared default. Recommendation and what was done: delete the
   exception, do not relocate it. Node prerequisite: the shared memory directory must be
   user-owned, so `sudo mkdir -p /srv/fabric && sudo chown -R "$USER" /srv/fabric` once.
4. **Legacy units.** Any unit whose own comments call its tree legacy, or a unit that
   duplicates another service on the same port, is a retire candidate. Confirm which is
   active and disable the other.

## The sequenced procedure, reversible at every step

**Step 0, local, no nodes.** Fold any live-only work into the main line and push (see
capture before you cut). Without this, the cutover regresses the live fabric.

**Step 1, per node, additive, zero live impact.** Clone the repo to the new layout on
that node. Build or refresh the service venv against it with `service-kit/rebuild-service-venv.sh`
and the lock. Do NOT repoint anything yet. Rollback: remove the new tree on that node.

**Step 2, per node, the flip, with your eye on it.** For each unit, back it up
(`cp unit unit.bak-cutover`), edit `ExecStart`, `WorkingDirectory`, and any `paths.env`,
then `systemctl --user daemon-reload`, restart ONE service, and check the board before
the next. Never flip all nodes at once. Rollback: restore the `.bak` unit and
daemon-reload.

**Step 3, verify.** The board shows every service alive, tools report live, the access
control enforces, and the data sink is still being written. Then walk the service venv
check (`service-kit/check-service-venvs.sh`, exit 0) and re-capture the unit record.

**Step 4, clean.** Retire the legacy and duplicate units, remove the `.bak` files once
confident.

## Lessons that generalized

Four things this cutover taught that apply to any layout move.

- **A venv is not relocatable.** Its shebangs bake the absolute path they were created
  at. Moving the tree leaves running processes alive on deleted files; they die on the
  next restart. Always rebuild from the lock after a move, never edit the old venv in
  place. Full recipe in `service-kit/README.md`.
- **Enable, do not just start.** A unit that is started but not enabled comes back dark
  after a power cycle. `systemctl --user enable --now <unit>` for every resident
  service. Lazy or on-demand services correctly stay disabled.
- **The boot bind race.** Every binding unit needs the `wait-for-tailnet` drop-in before
  the node's first boot. Ordering cannot fix the race; polling can. See
  `service-kit/wait-for-tailnet.conf` for the mechanism and why `After=` silently
  no-ops across the system/user namespace boundary.
- **Tools must find their repo by walking, not by counting.** Anything that computed the
  repo root by counting parents from its own file broke silently when the depth changed
  (a `parents[3]` quietly became `$HOME`). Tools should locate the repo from their own
  file, and nothing should count parents.

## What this does not touch

The shared model mount, any containerized service, and any node's live serving state
until its own step 2. The live nodes are read for state only during recon.

## Provenance

The migration it documents is the one that closed the old layout on the primary
workstation first, with the other nodes following one at a time by the same recipe. The
dated addenda were folded into the lessons above.
