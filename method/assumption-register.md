# The assumption register: writing a plan that can be attacked

How to write a plan a reviewer can do real work on. The setting used here is a
scheduling problem: deciding which workloads run on which machines across a
small fleet, where the machines differ in accelerators, memory, and role, and
the workloads differ in how hot, how deep, and how latency-sensitive they are.
The method is general and does not depend on the workload.

The premise is blunt. A plan that survives review unchanged was not reviewed.
Write to be attacked.

## 1. One objective, stated once

Open with the objective as a single sentence, and say plainly what the
objective is not. Here: maximize the effectiveness ceiling per workload, each
job placed where its measured rate or capacity is highest. Not model count. Not
utilization for its own sake. A one-line objective that names its own
anti-goals is much harder to argue past.

## 2. Hard constraints, none negotiable inside the plan

List the constraints that are not up for trade inside this document. Data that
must never leave the private network. The set of always-on roles. The role that
must never rest. The rule that a session in flight never migrates mid-window.
Each is a wall the plan may not route around, only plan within. Anything that
would move a wall is a separate decision, not a local choice.

## 3. The state as proposed, not as it stands

This is the single most common failure, and it is a subtle one. If the plan
describes the target state while the fleet is currently in a different state,
label it. A reader who takes the proposal for the present believes an end state
already exists. Title the section "as proposed," or mark every row that differs
from today. A stale line in a plan poisons every session that hydrates on it,
which is the same law the plan exists to serve.

## 4. Per-machine rationale

For each machine, one paragraph on why its assignment maximizes. The good ones
are counterintuitive and worth writing down precisely for that reason. A node
assigned nothing on purpose, because an empty machine is what lets several
occasional windows coexist without conflict, is a rationale. The fastest
accelerator given one hot role and nothing else, because any co-resident either
evicts the hot role or starves its cache, is a rationale. Maximizing a machine
can mean maximizing its emptiness.

## 5. The assumptions register

Number every assumption and make each one falsifiable with a named, cheap
test. This register is the heart of the method. A register entry has three
parts: the assumption, the instrument that would falsify it, and the cost of
being wrong.

Examples of the shape, generic to the setting:

- A1. The memory figures are estimates. Falsify with a per-role memory read,
  ten minutes. If wrong, a placement moves.
- A2. Wake latency for a demoted role is acceptable. Falsify with a week of
  telemetry. The residency decision waits on it.
- A3. One of two undecided mechanisms will pass its bench. If both fail, the
  constraint that depends on them needs a third mechanism, not a workaround.
- A4. The per-token cache cost for a large role is unmeasured, and every
  multi-machine depth claim inherits that hole. Falsify with a direct receipt.
- A5. The inter-machine decode tax is unmeasured. The depth windows assume it
  lands tolerable. The firing spec measures it.

The discipline: an assumption with no instrument is a wish. An assumption
whose failure cost is unstated cannot be ranked.

## 6. Accepted costs, named so they are choices

Every plan has costs. Name them, so they read as decisions and not as
oversights. An occasional capability now runs only inside claim windows. A
depth window displaces a resident role for its duration until hardware is
added. A demoted math role now pays a wake latency until telemetry speaks. The
small accelerator takes no heavy work however idle it sits.

## 7. Options excluded on purpose

List the roads not taken, and why. This is where a reader learns the plan is a
choice and not a default. Widen the transport past the current mode: named
future decision, not drift. Move the view off its welded home: the whole welded
group moves together or not at all. Replace a card: kills a plane. Each line is
one sentence and it converts a suspicious absence into a stated decision.

## 8. Attack prompts for the reviewer

End with the questions you most want answered. Ask for the workload where the
placement ordering picks wrong. Ask whether a rule under-uses capacity. Ask for
the single point of failure the plan does not name. A plan that hands the
reviewer its own sharpest questions gets a better review than one that hopes
the reviewer will not look.

## 9. A reading order

List the sources a reviewer should read before the plan, and put the plan
last, as the target. An hour of ordered reading makes the review cheap and
sharp; an unordered pile makes it shallow.

Floor: no em dashes, no ellipses.
