# Runbooks: building and keeping a small multi-node AI rig

The operational shelf for a small sovereign rig: a handful of nodes serving models over
an overlay network, built and kept by hand, where every claim carries a receipt. These
are the guides a stranger can follow to build the same thing, and the ones the operator
reads at 2am when a node will not come back.

The rig this shelf describes, stated once so the runbooks can refer to it without
naming anything: a **head node** (a GB10-class ARM box) that hosts the view and the
registry and mirrors the git bares; a second GB10-class box beside it on a 200G direct
link (the compute plane); a **dual-GPU workstation** (an RTX 5090 plus an RTX 4090,
x8/x8) that runs the primary interaction services; a **small CUDA node** (an RTX 4060
Ti class card) used as a second workstation; and an **integrated-GPU node** (a Strix
Halo class box, ROCm) used as the math bench and mobile fallback. Everything is wired
to one 10G management switch and addressed by name over a Tailscale overlay.

Hardware is described by class on purpose. The numbers in each runbook are that rig's
measurements; substitute your own where they differ.

## The runbooks

| runbook | what it is |
|---|---|
| `node-onboarding.md` | the repeatable pattern: bare Linux to a fabric-joined box. Start here. |
| `runtime-cutover.md` | migrating a live fabric from one repository layout to another, without downtime you did not schedule. |
| `network-core.md` | the management-plane spine: two planes, switch selection, install order, rollback. |
| `card-posture.md` | claiming an accelerator back from the fabric for a game, and handing it back. |
| `used-gpu-bench.md` | the function-and-power check that a used card earns before its price is discussed. |
| `bench-contract.md` | how one dual-GPU node holds services, takes summons, and stays honest as an instrument. |
| `nas-build.md` | the storage node: a mirror that is not itself a working node. |
| `striker-onboarding.md` | the same onboarding pattern pointed at a CUDA workstation, with the gotchas that cost real time. |
| `fabric-topology.md` | a dated snapshot of the whole rig. A later snapshot supersedes it. |
| `service-kit/` | the small pieces that keep services honest: venv rebuild, zombie check, boot-race drop-in. |

## The through-lines

Four lessons recur across the shelf. They are stated here because they are the reason
the runbooks exist, not decoration.

1. **Capture before you cut.** The single most expensive mistake in a live migration is
   moving a tree that carries work existing nowhere else. Snapshot the divergent state
   to a named directory and record what is in it before anything else happens.
2. **Silent failures are the enemy.** A started-but-not-enabled unit, a missing editable
   install, a unit that binds an address that is not up yet, a venv whose interpreter
   moved: every one of these looks healthy until the next restart, and every one is
   caught by a check that asks about the real thing rather than the bookkeeping.
3. **Ordering does not cross namespaces.** A system unit cannot be ordered behind
   another system unit at the user level. Poll for the condition you need instead. This
   generalizes well beyond the overlay address in `service-kit/wait-for-tailnet.conf`.
4. **Bench before price.** A used card earns its place through measurement, not
   reputation. The bench is free; run it first.

Floor: no em dashes, no ellipses. Every deployment-specific value in these documents is
a parameter with a documented default.
