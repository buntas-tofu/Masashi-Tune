# The syslog flood: a postmortem

A short postmortem for a logging incident on a workstation. The raw system
logs are incident data and are not reproduced here. This is the sanitized
narrative.

## What happened

A desktop shell entered a garbage-collection storm and wrote a very large
amount of system log in a very short window. The estimate from the capture is
about 14 GB of log, on the order of 23 million lines, inside a 98 second
window. A second capture from a different machine shows the quieter sibling of
the same class: a steady stream of a repeating kernel denial written into a
log that was not rotating.

## Timeline, as reconstructed

Peripherals reconnected. Within seconds the storm began. The shell emitted the
same message millions of times: it was attempting to call back into its script
engine during the sweeping phase of garbage collection, most likely because a
window or widget actor was not destroyed with its destroy signals connected.
The shell blocked the callback rather than crash, and each blocked call wrote a
multi-line stack trace naming the offending signal. The first such line named a
window monitor event on the display object.

The capture is the pre-truncation evidence: a handful of raw storm lines, then
a count of the full window.

## Impact

Log volume alone is enough to fill a disk and take down unrelated services that
share it. The machine also stuttered under the write load.

## Root cause

Labeled inference, from the repeating message: the shell was not tearing down
window and widget actors with their destroy signals connected, so each
collection sweep kept finding live callbacks and blocked each one loudly.
Suspected trigger is the peripheral reconnect, but the trigger is the fuse, not
the fault.

## What would have caught it

A log rate limit on the offending service, so one noisy source cannot consume
the whole disk. A flood guard on the journal that trips on write rate, not just
on free space. Rotation that actually runs, verified by a receipt, because the
second capture shows a log that quietly grew without it. And an alert on log
growth rate, which is the signal that was present and unread.

## The lesson

The storm was loud in the log and silent everywhere else. Nothing surfaced the
failure until disk pressure, at which point the loudest path had already been
recording the proof for ninety eight seconds straight. A flood is a signal that
the loud path worked and the quiet path did not. Rate-limit the loud path, and
watch the rate, not the total.

Floor: no em dashes, no ellipses.
