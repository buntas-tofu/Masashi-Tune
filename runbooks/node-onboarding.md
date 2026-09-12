# Node onboarding: bare Linux to a fabric-joined box

The repeatable pattern that every node in this rig was onboarded with, stated once and
node-agnostic. It is the point of the whole shelf: a fabric that only ever gains nodes
needs a recipe, not a path swap.

The pattern's executable half is `../ops/node-onboarding/kitting-node.sh` (in the repo's
ops lane), and its two hard-won guards are `service-kit/wait-for-tailnet.conf` and the
enable-not-just-start rule below. This file is the prose sequence and the reasoning.

## Who this is for

Any new node: a compute node, a serving node, a storage node. It is deliberately written
so the GPU steps are optional, because a storage node onboarded with the same recipe and
landed as a keeper with no serving service at all.

## The sequence

### 0. Prerequisites (one-time, needs sudo)

- The shared runtime directory must exist and be user-owned, so services can write to it
  without sudo:

  ```
  sudo mkdir -p /srv/fabric && sudo chown -R "$USER" /srv/fabric
  ```

  This is the one step that touches the system, and it is the only one that cannot be
  redone from the recipe later.

### 1. Clone the repo

Give the new node the distributable software only: the control plane, the serving
tooling, and the runtime artifacts it needs. Do **not** hand a fresh, not-yet-hardened
box the operator's umbrella tree, notes, or memory corpus. Minimal footprint on new
silicon is the design, not a limitation, and distribution of anything sovereign to a new
node is a per-node decision the operator makes, not a default.

### 2. Rebuild the service venv on the system python

```
service-kit/rebuild-service-venv.sh <repo>/.venv <pkg> [<pkg>]+
```

The venv is built on the **system** interpreter, never a package-manager-managed one, so
it survives that manager garbage-collecting an interpreter out from under it. The lock
file is the floor. Then install the repo's own packages editable and import them to
prove it (see `runtime-cutover.md`, the silent editable-install failure). Both of these
are the reason a node's keeper is reboot-immune.

### 3. Write the units from a template

Every service unit is derived from a recorded unit on an existing node, with three edits:
the node's own overlay IP in the bind, the model or data path, and the served name. The
recorded units live in the repo's unit record, and the drift gate compares the live units
against it.

Two guards that are **not optional**:

- **The boot bind race.** Drop `service-kit/wait-for-tailnet.conf` into each binding
  unit's `.d/` directory before the node's first boot. Every unit binds its node's
  overlay address; at boot the user manager starts before the address is assigned, and
  binding a missing address fails instantly. Polling fixes it; ordering cannot.
- **Enable, do not just start.** `systemctl --user enable --now <unit>` for every
  resident service. Linger plus enabled is what makes the board reboot-durable. A
  started-but-not-enabled unit comes back dark after a power cycle. Lazy and on-demand
  services correctly stay disabled.

### 4. Register the service in the roster

Service identity is config-as-identity in the roster files, loaded by the registry,
checked by the registry's golden test. Roster edits need a **view restart** to take
(there is no hot reload).

### 5. Board-verify at the wire

Ask the board (`GET /api/health`, `GET /api/services`) through the view. A newly onboarded
service should show alive with sane latency. A chat or vision smoke call confirms the
relay path end to end.

## The bind posture, so it is not rediscovered

Every service in this rig binds its node's overlay IP, one posture fleet-wide, zero
exceptions. Never loopback, never `0.0.0.0`, except where a service already does. That
single posture is exactly why the boot-race guard is mandatory rather than nice-to-have.

## The universal steps' proven record

The pattern was exercised several times in one week on the real rig (a serving node
flip, a CUDA workstation bring-up, a storage node). Each exercise added one lesson back
into this file, which is the loop working: the deliverable is the recipe, and the recipe
gets sharper every time it is run.

## What did not generalize, and is left out

The recon source for this pattern also held three per-node onboarding directories. They
are recorded here honestly rather than half-translated:

- **One exact silicon's tier scripts** (a ROCm bring-up: tier-0 apt foundation, tier-2
  driver stack, tier-3 sudo policy, a PyTorch bench, a syslog flood guard, a USB-C hold
  automount note). These target one hardware line and one driver generation. The
  *pattern* they follow (foundation, driver, policy, bench, guard) is general; the scripts
  are not, and a reader on different silicon would follow them into a wall. Left out
  rather than parameterized into something misleading.
- **A per-node kitting script** (node names, a fixed user, a fixed reference host). The
  honest generalization of it is the repo's `ops/node-onboarding/kitting-node.sh`, which
  keeps the sequence and parameterizes every deployment value. The node-specific original
  is not reproduced here.
- **A per-node bootstrap orientation file** written for one box and one session. Its
  substance (what a fresh node gets, what it deliberately does not, the guard checklist)
  is folded into the sequence above; the file itself names nodes and a personal clone
  URL and does not travel.

The CUDA case has its own runbook, `striker-onboarding.md`, which inherits this sequence
and adds the CUDA-specific deltas and gotchas.

Floor: no em dashes, no ellipses.
