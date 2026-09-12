# Fail visibly: the sunset of a silent background sweep

A short postmortem for a maintenance task that was turned off by decision. The
lesson is not that the task was hard. It is that the task failed silently for a
long time, and the silence is why it lived as long as it did.

## Context

A periodic background job read text files from the estate and fed them to an
embedding index, so that the memory layer could search estate text. It ran on
the busiest machine in the fleet, on an interval, unattended.

## What died

One job: the estate sweep. Disabled at runtime through the code's own kill
switch, a service drop-in that set the interval to zero so the job was never
created. Nothing else was touched. The hosting service, which also serves
files, vitals, logs, and other sweeps, stayed up.

## Why, measured

The numbers made the decision, not a preference.

- The job consumed roughly two hours of CPU per day in bursts that reached the
  mid nineties and made the desktop stutter.
- The embedding endpoint rejected inputs above roughly two and a half thousand
  characters with an error, and estate chunks ran two to four thousand. In one
  profiled pass, about 88 percent of embeds failed (738 of 837).
- The failure was swallowed. The code never persisted the errors, so every pass
  re-read up to two hundred files and re-attempted about 3,400 dead embeds.
  Success receipts went to a logger with no handler, so nothing ever reached
  the journal.
- Per-embed cost was amplified by building a fresh client and TLS context on
  every call (837 of them, about 60 percent of pass CPU in the profile).
- The file walk was deterministic and rescanned the same first two hundred
  files every pass. After twenty five hours, only 178 files had been indexed.

## State left behind

The partial index stays on disk and stays queryable. It is simply no longer
fed. The hosting service stays up. The feature is a re-measurement candidate,
not a mistake to delete.

## Revert

Delete the drop-in, reload the service manager, restart the service. The code
is untouched.

## The lesson

A background job that cannot fail loudly is a job that burns resources
invisibly. This one swallowed its errors, logged only its successes, and
reported progress that never advanced, because it walked the same prefix every
pass. Every signal that should have caught it was either absent or was written
somewhere nobody read.

The rules that follow:

- Persist failures. An error that is caught and dropped is a metric you chose
  not to have.
- Count the failures that will repeat. A pass that retries thousands of
  identical dead work is telling you something specific about the input.
- Give the job a progress signal that stands still when the job is stuck. A
  walk that rescans the same prefix has no way to look wrong.
- Bound the input to what the downstream can actually accept, at the boundary,
  once, instead of failing per item forever.
- Alert on cost, not on absence. The task was always "healthy" by any liveness
  check. It was healthy and useless at the same time.

Fail hard and visibly rather than soft-failing with plausible but wrong output.
The soft failure here was not a wrong answer. It was two hours of CPU a day and
a flat progress line that everyone read as work.

Floor: no em dashes, no ellipses.
