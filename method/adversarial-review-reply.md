# The adversarial reply: reviewing a plan as a peer

Status: active.

How to answer a plan that was written to be attacked. The companion to the
assumption register. The setting is the same: placement and scheduling across a
small fleet of machines. The method is the review, not the subject.

The reviewer's contract, stated up front: read the plan last, after the
sources it cites, and read enough of the surroundings that the reply can
contradict the plan with the plan's own files. Return a dated reply. Say on its
face whether the plan survives unchanged. It should not.

## Open by naming the verdict and the move

Start with what the review found in one or two sentences, then the classes of
defect. A good opening names the shape before the detail: the model is sound,
the per-machine arguments hold, and what the review found is one missing layer,
a class of items dropped in a handoff, and a handful of internal
contradictions, each one line to fix and each one able to mislead a fresh
reader today.

## Hunt specific failure classes

A generic review finds generic problems. A peer review checks the same few
failure classes every time, because they are the ones that recur.

A missing layer. The plan splits a concept halfway and stops. Here the plan
said the right sentence about weights following the window, then stopped one
layer short of the artifact registry underneath. A scheduling claim with no
registry to execute against is not a plan. Look for the layer the document
names and does not build.

Items dropped in the relay. When a plan passes through several documents and
authors in one night, each hop compresses and something falls out. The reviewer
lists what fell, and where it fell, and why it matters. This is the forgetting
class, and it is the reason a handoff chain needs one owner per decision.

Contradictions between the plan and the standing state. The plan presents the
proposed state as the standing one. A policy claims a set of two while a third
member is filed under a category the policy does not have. The plan's own
excluded options foreclose the answer to one of the plan's own attack prompts.

Arithmetic that contradicts a stated law. An estimate says a window fits a
card, and the same document's own resident load says the window sees half that.
When a number and a law disagree, the law is usually the survivor.

## Answer every attack prompt

The plan asked questions. Answer them, one per section, with reasons and a
decision by receipt where a decision is premature. Where a proposed change is
wrong, say why: a rule is bought with a hard lesson, vLLM-style memory
preallocation is static, and the simplicity of the rule is worth more than the
idle capacity. Where a change is right, name the instrument that decides it.

## The strongest move: typed constraints over an ordering

A common defect is a lexicographic ordering of placement rules where the rules
should be typed constraints. Ordering by stickiness, then headroom, then
ceiling fit picks wrong on a real workload, because the stickiest role is also
the one that gets evicted, so rule one argues against its own assignment. The
fix is not a new order. It is to make each rule a constraint with a scope:
stickiness constrains migration, never initial placement. Headroom constrains
admission. Ceiling fit chooses among the survivors. Same three ideas, no wrong
answers.

## Add the assumptions the register missed

A review that finds a missing layer owes the register entry for it. Name the
new assumption, its instrument, and its failure cost, in the same numbered
form the plan uses. A plan with a register invites the reviewer to extend it,
which is cheaper than arguing about prose.

## Name what survives

State what the attack did not touch, so the attack stays honest. The objective
function, the per-machine arguments including the counterintuitive ones, the
register structure itself, the reading order. A review that only subtracts
reads as hostile. A review that says "this paragraph is the best one and it
stands" earns the right to cut the rest.

## Close on sequencing

End with the order of operations if the verdicts land. Which phase grows which
small item. Which ruling must land before the plan is cited by anything else.
Where the surviving disagreements belong. A reply that ends without sequencing
leaves the work ownerless, which is the exact failure it was written to catch.

Floor: no em dashes, no ellipses.
