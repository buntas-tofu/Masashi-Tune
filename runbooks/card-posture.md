# Card posture: taking an accelerator back for a game

A small layer that lets a node's fabric give one of its GPUs back to the operator for a
while, stop the services that were using it, and hand it back exactly as it was. Built
because the operator has time for Steam again and the workstation's 5090 was 21 GiB into
a vision service.

The ask was small and the shape underneath it was not: "regain all available VRAM on the
workstation's 5090 for gaming, and the inverse." What that needs is a way to say a card
belongs to something other than the fabric for a while, have the fabric believe it, and
have it be exactly reversible.

The shipped tools are `../ops/gpu-claim` and `../ops/gpu-game`.

## What it does

```
gpu-claim                        what this node's cards are doing
gpu-claim claim 5090 -r "Elden Ring"
gpu-claim release 5090
```

Measured on the dual-GPU workstation the day it landed: claim 1.07s, release 0.17s, both
services answering again 4s after release. 20.5 GiB recovered, the card going from 9.0
GiB free to 29.4 GiB.

The 1.9 GiB still held after a claim is the desktop session. The card drives the display,
so that is correct, and the drain check knows to ignore it (the foreign-process rule
below).

## Steam

Paste into a game's launch options, keeping the placeholder:

```
/absolute/path/to/ops/gpu-game %command%
```

It claims before the game starts and releases when it exits, including on a crash,
Steam's stop button, and a kill from the overlay. Knobs, all optional:

| variable | default | what it does |
|---|---|---|
| `GAME_CARD` | `5090` | which card to claim |
| `GAME_REASON` | the executable's name | what the claim records |
| `GAME_FORCE` | unset | launch even if the claim fails |
| `GAME_QUIET` | unset | no desktop toast on the happy path |

It refuses to launch on a failed claim rather than launching into a card that does not
have the memory you expected. That failure presents as stutter twenty minutes in, which
is unreadable; a launch that does not happen is a signal.

Claim and release fire a `notify-send` toast, because a launch option's stderr goes into
a log nobody reads at the moment it matters. `GAME_QUIET=1` silences the routine pair and
deliberately does **not** silence a failed release: that one means the services are still
rested and the fabric is quietly missing its front end until somebody notices.

### The race the TERM path had

The obvious wrapper shape is `claim && exec "$@"`, and it is wrong twice.

`exec` replaces the shell, so the EXIT trap never fires and the card stays claimed until
somebody notices the fabric is gone. So the game runs as a child and the wrapper waits on
it.

The second one only showed up on the first stop-button test. **A trapped signal
interrupts `wait`:** bash returns 128+N the instant the handler runs, while the game is
still tearing down and still holding the card. The release fired there, restarting 20 GiB
of services into memory the game had not given back, which is the exact collision this
tool exists to prevent, arriving through the back door on every use of the stop button.
Fixed by polling until the child is genuinely gone (bounded at 60s) before letting the
EXIT trap release. Verified against a game that takes five seconds to die: the release
now lands after the game is down, not four seconds ahead of it.

## The board

The board grows a card tile per declared card, above the services that sit on it: free
memory as the gauge, one button that reads CLAIM IT or GIVE IT BACK. A rested service
reads `resting - Elden Ring` in the calm accent, not a failure state in red, because the
board's red has to keep meaning "this broke by itself".

## Where the truth lives

The card roster file, one of the roster files the registry loads. Before it, a service's
card was recorded in three unrelated places and nowhere authoritative: a device UUID
inside a serve script, `CUDA_VISIBLE_DEVICES` in a unit, and `--gpus device=N` in a
docker run. The node roster claimed "the roster stays the truth for which service is
pinned where" while carrying no such field.

It had already drifted. The service roster said one service was pinned to the 4090 from
before a split moved it to the 5090; its unit and `nvidia-smi` both said 5090 for the
four days that comment said otherwise.

**Identity is the UUID, never the index.** The two orderings on this workstation are
genuinely reversed: `nvidia-smi` and `CUDA_DEVICE_ORDER=PCI_BUS_ID` put the 5090 at 0,
llama.cpp's CUDA enumeration puts it at 1. The serve script pins by UUID and says why.
The `smi_index` is recorded because the docker services pin with it, labeled as what it
is.

## The four rules the posture layer will not break

**It never guesses on the way back.** A claim records exactly which services it stopped;
a release restarts exactly those. Not "everything pinned to the card", because a service
that was already down before the claim was down for a reason, and reviving it on release
would be the posture layer inventing state it never observed.

**It verifies against the silicon, not its own bookkeeping.** Stopping a unit is not the
VRAM coming back: systemd returns as soon as the process is signalled. A claim polls
`nvidia-smi` for compute processes on the card's UUID and reports what it actually saw,
including the case where something would not leave. Processes matching the foreign list
(Xorg, gnome-shell, wayland, steam, soffice) do not count against the drain, because a
desktop session on the claimed card is normal and is what the game is about to join.

**It survives a restart.** The claim lives in a small JSON file under the user's config,
written atomically, because the service units are `WantedBy=default.target` and come back
at the next login whether or not anything remembers why they stopped. The keeper
re-enforces on a 30s reconcile while any claim is live. That reconcile also covers the
login race: keeper and services are both wanted by `default.target` with nothing ordering
them, so a single startup pass is not enough. Verified by hand-starting a service behind
the interlock's back and watching the keeper put it down again with a log line.

**A claimed card refuses wakes.** `POST /service` returns 409 for start and restart on a
service whose card is claimed, naming the card, the reason, and how to release. Stops are
always allowed. Without this, a lazy summon or a board-triggered restart lands 20 GiB on
the card mid-game. Verified: the service on the claimed card was refused, the service on
the other card restarted normally.

## Endpoints

```
GET  /posture    cards on this node, occupancy, any claim
POST /posture    {"card": key, "action": "claim"|"release", "reason": str}
```

Card-scoped rather than node-scoped on purpose: a two-card workstation's cards are
independent, and a game wants one of them. The other card keeps serving through a claim
on the first, which is the whole point of splitting services across the two cards.

Authority is the keeper's own, one level up from a service: only cards on this node, only
through units named in the registry, only start and stop.

## Decisions taken, and what they cost

**A small service rests rather than relocating to the other card.** It is only hundreds
of MiB and the second card has room, so moving it was on the table. Against it: it needs
a runtime card-override mechanism, and it re-creates exactly the contention class the
split was executed to retire (two services sharing a card measured up to 61 to 92 percent
latency at the larger service's ceiling). Cost of resting it: one layer of the fabric is
quiet during a game. Other nodes serve the same layer, so it is close to free.

**Explicit trigger plus a Steam wrapper, no process watcher.** A daemon sniffing for game
processes covers more launchers and can pull a card out from under a service
mid-inference. The launch-option wrapper is explicit by configuration, which is the same
coverage for Steam without the class of surprise.

## Not done, and deliberately

- **Only the dual-GPU node declares cards.** Every other node is unified memory or single
  card, so the question does not arise. Others add entries when a probe confirms a UUID,
  never before.
- **No relocation path.** Ruled out above. If it is ever wanted, the mechanism is an env
  file the units read, not a runtime drop-in (drop-in content is deliberately never
  recorded by the drift gate, because one drop-in holds an API key).
- **The second card is reservable but never claimed by default.** A game wants one card,
  and the service on the other costs it nothing. Declared reservable so the choice stays
  the operator's rather than being decided by omission.

## Found on the way in, fixed in passing

The roster golden test was failing three ways before any of this was written, and the
third one mattered most.

1. A service's move to a new node never landed in the spec: node, serve script,
   throughput, and description were all still the old node's.
2. A service's `serve_script` and `unit`, declared in the data earlier, never landed
   either.
3. `test_port_collision_refused` had stopped testing anything. It doctors the roster by
   moving a model onto another service's port to force a collision, and the guard is per
   (node, port) by design. When the service moved, that port came free, the doctored
   roster loaded clean, and the test asserted an error that was never going to be raised.
   **A service move silently disarmed a validation test.**

The third is now cased against a service resident on the same node as the model, and the
doctoring helper asserts that its transform actually changed the file. A doctoring helper
that cannot prove it doctored is not an instrument.

Floor: no em dashes, no ellipses.
