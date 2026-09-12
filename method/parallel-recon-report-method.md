# The parallel recon report: a method note

Status: active.

How to produce an honest snapshot of a large, fast-moving workspace in one
evening. Extracted from a full-workspace sweep and stripped to the transferable
method.

## The move

Split the workspace into areas and run one read-only reader per area, in
parallel. Each reader owns exactly one area and returns the same five fields,
every time: state, motion, in-flight work, risks, and focus candidates. Each
field carries dates and paths. Uniform output is the point. It is what makes
six independent reads comparable to each other and to the maps.

## The orchestrator's job

The orchestrator does not repeat the readers' work. It does three things.

Verify the sharp edges live. Where a reader reports a hard fact, probe it
directly: a node reported offline is confirmed by three independent probes
agreeing, a data gap is measured in bytes, a draft is confirmed to exist
durably on disk. A self-report is a claim, not a verdict, and the cheap probes
are exactly where the report earns its authority.

Reconcile disagreements. When readers disagree, or a reader disagrees with the
standing map, disk wins. Say so in the report, and say which source won.

Label inference. Every inference in the report is marked as one. Everything
else is dated observation. A reader may infer; the report must not let an
inference pass as a measurement.

## What the report carries

The read, up front: what changed, and the cost of the velocity, in three
places. Then the areas, one section each. Then the cross-cutting threads that
span areas, because those are the findings no single reader can see. Then a
ranked short list for the week ahead, split by where the owner will be. Then a
decision queue with the cheapest next step for each. Then the small dated loose
ends.

A method note at the end states the shape: how many readers, that each was
read-only, what the orchestrator verified live, and that disk wins over the
maps.

## Status line

The report says on its face that it is a snapshot, not a second source of
truth. The maps stay the owner's. When the report disagrees with a linked
source, the source wins and the report is corrected.

Floor: no em dashes, no ellipses.
