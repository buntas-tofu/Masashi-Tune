# Mining a private estate for public release

A method note on taking work that grew up in private and deciding, carefully,
what of it can honestly stand in public. The setting is one person's home
multi-model AI lab: a small fleet of machines, a control plane that routes
work across them, a long-term memory corpus, a bench that measures the models,
and a shelf of runbooks for building and keeping the rig.

The campaign's outcome was two public repositories, one for the machine and
one for the mind. This note is about the process, not the products.

## The shape of the problem

Private work accumulates texture. Secrets are the obvious hazard and the easy
one to look for. The harder hazard is the surround: machine names, paths, the
names of the human-shaped roles the system casts, the specific hardware map,
the small telling details that together describe a place. A working estate is
not a document. It is a place, and places carry more than their files.

Two mistakes are common and both are fatal to a clean release. The first is to
grep for a list of forbidden words and call it done. The second is to let the
person who wrote the material also certify its cleanliness.

## The waves

The campaign ran in waves, each one smaller and more decisive than the last.

Recon. Eleven read-only briefs mapped eleven slices of the estate: the guard,
the judgment harness, the deliberation schemas, the serving stack, the bench,
the fleet-ops gates, the runbooks, the memory architecture, the training
chapter, the narrative corpus, and the process and method corpus. Every brief
was read-only by rule. Nothing was mutated while it was being assessed.

Conferral. Three roles read the recon and argued over it in parallel. An
architect proposed a partition, an adversary attacked the architect's claims
and verified them against the tree, and a story curator read the same briefs
for narrative value. The adversary's job was to be right about the tree, not
agreeable, and its verification ledger became the factual basis for the rest
of the campaign.

Reconcile. One reconciler merged the three positions into a committed
partition, stating both sides of every disagreement, then a commitment with
reasoning, then a tag: this one resolves in build, that one needs a ruling.
The reconciler also carried the adversary's raised densities, the places where
the first pass had underestimated the scrub.

Deep review. Two independent stacks judged the committed proposal. One was a
local reasoning seat. The other was a frontier mixture-of-agents panel. They
did not read the estate, only the proposal, to keep the two comparisons
honest. Both returned the same verdict, proceed under hard gates, and both
independently landed on the same unresolved soft spots the adversary had
already flagged. That convergence was the most useful signal of the whole
run. A second opinion that finds what you already know is cheap. A second
opinion that finds the same gaps from a different direction tells you the gaps
are real.

Build. Only after the gates and the rulings did the staged build begin, in
fresh trees that were never clones of the source.

## The gates

The gates are the part worth stealing. Each one exists because a cheaper
version of it had already failed.

The token scan. An estate-vocabulary scan, matched on word boundaries and case
insensitively, to zero, with one expected-and-intentional list for the few
strings that are meant to survive, such as a license line. The measure is
counts before and after, not adjectives.

The survivor-carrier scan. A token scan cannot see everything that carries a
name. The survivors are the carriers a string search walks past: the git
commit author name and email, image metadata, document properties, notebook
cell outputs, archive interiors, lockfiles, container labels, and the file
names themselves. Scan those too, or the clean tree ships a dirty commit.

Re-author, never scrub. This is the doctrine that does the most work. Material
that is structurally contaminated cannot be washed clean, because the
contamination is the structure, not a coat of paint on it. A negative test
corpus harvested from real private attacks is contaminated by construction. A
document whose whole shape is a private place is contaminated by construction.
No amount of find-and-replace fixes that, and a scrub gives false confidence
that it did. The move is to rebuild the artifact from clean sources and record
the provenance of every part.

Number provenance. No number ships unless it is reproducible from a file in
the tree. A benchmark figure quoted in prose but measured on a tape that never
travels is, in public, a claim with no instrument behind it. This rule retires
a whole class of complaints at once.

Independent verification. The person or session that cleaned the tree does not
certify the tree. The scrub is verified by a second stack or a second seat, by
a full-tree scan that descends into the carriers above. Self-attestation is
not a gate.

A written zero standard. "Zero" needs a written, auditable meaning: zero live
secrets, zero reachable personal address, zero private-network literal, zero
legal name outside the ruled license line, zero excluded-corpus paths, zero
hostile licenses, zero references to the tools the private tree happened to
use. A number without a definition is not a standard.

## What it taught

The recon is cheap and the seam is expensive. Eleven read-only briefs and a
three-role conferral cost one evening. Deciding where one repo ends and the
next begins, and holding that line, is the part that took the real judgment.

Names are load-bearing. Public work reads best in plain vocabulary: well-worn
words for well-worn concepts. Invented names for ordinary things make a public
tree read like a private one with the labels filed off, which is exactly what
it is.

The danger is texture, not secrets. The grave risk is not a key in a file. It
is a place described so precisely that a reader could find it. Machine names,
paths, and small specifics add up to an address.

A grep is not a gate. It is one gate among several, and the most confident one
to over-trust.

Independent verification pays for itself immediately. When two systems with no
shared lineage converge on the same gaps, you stop arguing about whether the
gaps are real and start closing them.

Some material should hold. Work that is adjacent to a world outside the home
lab, or whose only honest form is a case study gated by a third party's
license, is not made safe by a scrub. It is held until it can be done
properly. Naming the holds explicitly keeps them from leaking back in.

Build fresh, and delete with intent. The source estate stays untouched and
read-only. The public trees are born new, with a neutral identity set before
the first commit. The stale copies are the ones that leak.

Floor: no em dashes, no ellipses.
