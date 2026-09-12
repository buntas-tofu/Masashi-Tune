# The session handoff protocol

A short, prescriptive method for carrying work across sessions. Long-running
work is done by many sessions, and the only thing that survives between them is
what was written down. This is how to write it down.

## Rules

One handoff per session, written at close, by the session that did the work.
No second author, no later reconstruction from memory.

The handoff is operational, not narrative. The narrative version is a
different artifact for a different reader. Keep them separate, and keep the
handoff dense.

Write the live state exactly, and prove it. Versions, memory figures, running
services, test counts. State it as read from the machine, not from a document.
A record read from a file fifteen days stale is how a whole session gets spent
chasing a window size that never existed.

Name every open decision as a question with its fork. "Is the newer base the
next serving model, or is it staged with the current one staying?" is a decision
the next session can answer. "Consider the upgrade" is not. An open decision
with no owner is how work scrolls off the edge of the world between sessions.

Separate settled from proposed. Mark which lines are ruled and binding, and
which are candidate. A handoff that presents a proposal as a decision is worse
than no handoff, because the next session will build on it.

List what is in flight and what it will do unattended. Background pulls,
scheduled jobs, half-landed changes. The next session needs to know what will
move on its own.

Record verification. What tests pass, what smoke was run, what was seen live.
A handoff that reports intent instead of evidence is a plan, not a state.

Pick one file-naming convention and never drift. A handoff cited by one name
and written under another costs every future session a grep, and the grep
fails, and the session hydrates on nothing.

Mark the carve points still open. The toggles, the deferred decisions, the
things explicitly left for later. An unmarked deferral looks like an
oversight.

## Discipline

The handoff is not a second source of truth. When it disagrees with a file, the
file wins and the handoff is corrected. It is a pointer to the truth, kept
fresh, and its only job is to make the next boot cheap.

The next session reads the newest handoff first, before anything else, and
starts from written truth rather than from whatever the model happened to
retain.

Floor: no em dashes, no ellipses.
