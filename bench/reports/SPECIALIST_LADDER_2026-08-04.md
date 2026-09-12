# The specialist ladder: what the bench does when the 5090 frees

**Staged 2026-08-04, 17:00, while the operations 2x2 held the card.** The
specialist kit is registered (nine staged seats, five serve scripts,
the bench contract); this is the run order that turns registration into
receipts. Every rung emits a manifest to the runs lane via `manifest.py`, one
model at a time on the measured card, co-tenants declared, temperature 0 on
anything scored. Floor: DMF. Label inference.

## Gates

- **G1, the card.** The operations setlist completes and the 5090 goes idle.
- **G2, the anchors.** `reid_dictionary_v2.json` passes the discriminating
  anchor rule (ANCHOR_CONTAMINATION item 2): field content present inside the
  truncation window, not merely a high stage 4 grade. Rungs 5 and 6 only.
- **G3, the rulings.** Contract laws 1 and 2 (free agency per card, the small-model
  split). Rung 4 only; rungs 1 through 3 run under the pinning as it stands.

## The rungs

**1. The sm_120 canary.** `serve-olmocr7b.sh` on GPU0, `/v1/models`, then one
OCR call on a captured PDF page. PASS means vLLM v0.20.0 serves consumer
Blackwell and the pinned tag holds fleet-wide; FAIL steps the tag forward per
the currency routine, controlled bring-up beside the known-good. Either way
the verdict closes contract open item 3 and lands as a dated line in
the onboarding runbook.

**RUNG 1 PASS, 2026-08-04 19:52.** Engine compiled (torch.compile 12.8s, CUDA
graphs profiled) and opened its API in roughly 40 seconds; OCR on a local
SCF guide page returned 2,399 characters in 22.6s with a clean stop, tables
emitted as structured markup. Manifest in the runs lane; olmocr7b flipped
staged to lazy, unit installed disabled on the primary node. One scheduling fact banked:
vLLM's default memory pool took 29.6G of the card for a 9.4G model, so
co-tenant summons pass --gpu-memory-utilization explicitly (contract law 7).

**2. Serve-path smokes, one guest at a time on GPU0.** guardian8b, gptoss20b,
nemotron-embed, nemotron-rerank through their scripts; then the
verify-then-serve trio (granite pair, promptguard) attempted on vLLM with the
CPU-service fallback named if refused. Each smoke records load time, measured
VRAM against the contract table's Tier 3 estimate (update the table), one
bounded task, unload. Each pass flips that seat staged to lazy in the roster,
lands its unit, and refreshes the fleet capture, board spec updated in the
same edit.

**RUNG 2 RUN, 2026-08-05 afternoon. Six of six serve; four flipped lazy with
units; the granite question answered.** Guests ran beside the embedding service, newly resident
on GPU0 after the Law 2 split executed the same hour; every script now
carries an explicit GPUMEM per law 7 (none did before, the scripts predate
the canary's lesson).

- guardian8b PASS: 63s to API, 24.3G at 0.75 pool. The 4.1 judge contract is
  criteria-in-system-prompt (BYOC); the 3.x guardian_config template kwargs
  are silently inert against 4.1's generic template, and the first smoke
  proved it by getting a bread recipe instead of a verdict. With criteria in
  the system prompt: discriminating Yes/No verdicts, ~17s first-call warmup,
  0.23s hot.
- gptoss20b PASS: 51s to API, 24.8G at 0.75 pool, clean stop at temperature
  0; harmony lands replies in plain content, no reasoning_content
  side-channel on a simple ask.
- nemotron-embed PASS after two real findings: this v0.20.0 tag has NO
  --task flag (aborts at argparse; the pooling contract is --runner pooling
  with --convert auto), and the model needs trust-remote-code like its
  rerank sibling. 27s to API, 3.3G, dim 2048.
- nemotron-rerank PASS with a calibration note: 27s, 3.3G, /v1/score orders
  correctly (relevant above bread) but absolute scores sit near zero (top
  0.035). Order-consumers fine; threshold-consumers calibrate first.
- granite-embed PROVEN on vLLM ad hoc: ModernBERT class serves on --runner
  pooling, 24s, 1.3G, dim 768. The verify-then-serve caveat is resolved; a
  serve script waits for a consumer.
- granite-rerank PROVEN: 24s, 1.3G, and a usable absolute scale (0.61 to
  0.79, order correct), the saner calibration of the two rerankers.
- promptguard: weights discovered ON DISK since 08-02 (the pending-Meta
  line was stale); its transformers CPU service remains the open build.

One unit-layer catch landed with the flips: systemd user units do not
inherit the login PATH, and the serve scripts resolve HOST via the
snap-installed tailscale CLI, so all five guest units (the four new plus
olmocr7b's, latent since install) carry /snap/bin on an explicit PATH line.
Same blindness class as the machine gate's tailscale probe on this node.

**3. The cross-card calibration pair** (contract item 4). E4B UD, the frozen
120-record operations sample, GPU0 against GPU1. The pure pair wants the primary carrier
stopped for roughly ten minutes; if the window is wrong for that, run with
co-tenancy declared and say so in the manifest. Deliverable: the Blackwell
against Ada offset on latency AND agreement, which is the number that governs
whether a scored stage may ever span the two cards. Until it exists the
contract's answer stays no.

**4. The embedding-offset calibration** (contract item 6, after G3). E4B phase on
GPU0 with the embedding service idle against it replaying a REAL gather's call rate, not the
231k-call ceiling. This prices law 3's "routine setlists may run beside the embedding service"
clause honestly.

**5. The local PDF lane opens.** olmOCR's first real summon: the four known
binary anchors from v1 first, decoded output paired against build_anchors'
own text extraction as ground truth, then the 43 contaminated captures
(ANCHOR_CONTAMINATION item 3). A registrant whose only capture is undecoded
bytes carries a stage 4 grade derived from binary; this rung is the fix, and
it is the first bench guest paying rent on local content.

**6. The specialist setlist proper.** The task ladder crossed with the model
ladder on v2 anchors plus fresh operations records: bounded schema-fill, open
extraction, doc-parse, across e4b-ud, the 26B, gptoss20b, and olmocr7b on the
PDF rungs. The 4B-against-26B crossover question, now askable because the
anchors discriminate, and the specialists placed on the same axes the
carriers were. Extending setlist.py's TASKS for the new serve shapes is part
of this rung, not a prerequisite of the earlier ones.

## Addendum, 2026-08-04 evening: two rungs the re-scope adds

**7. The mini audition (E2 class, the synapse restoration).** The operator's
ruling returns the small models to their inverse-parallelism role, bounded work
only, and greenlights auditioning smaller: the original design named E2 class
as possibly sufficient. Zoo sweep for current candidates FIRST, no pulls
without the list. The matrix is the FULL silicon scope at the operator's
direction: both primary-node cards separately (Blackwell and Ada are different
instruments), the twin GB10 nodes, Strix Halo, the 4060 Ti node's Ada, and CPU arms (the
9950X at minimum), because the design said CPU-plus-GPU-paired feeders and a
zero-VRAM shadow is worth pricing. Tasks: the bounded rung ONLY, because that
is the role. Grade on self-consistency at temperature 0, parse, latency, and
always-on footprint. E4B UD is the incumbent baseline. Card:
minis-synapse-rescope.

**First candidate pulled and serving, 2026-08-04 20:30.** unsloth
gemma-4-E2B-it UD-Q4_K_XL plus mmproj-F16 eyes, commit-pinned 0314792d,
sha-verified, SOURCE.txt in the store, UD not QAT by the same day's swap
lesson. Serving on GPU0 at :8089 under the freshly ruled law 1. First pulse:
0.354s round trip on a bounded one-liner at temperature 0 against the E4B's
1.98s single-model baseline on the same card, roughly 2.7G resident. The
bounded heat against the incumbent on the frozen 120-record operations sample
is the next run, and the embedding split executes after it by the operator's
sequencing.

**RUNG 7 FIRST HEAT, 2026-08-04 21:32 (run 20260804T211908, manifest in the
runs lane).** Paired arms, 240 calls each, zero errors, temperature 0, two
passes, digest cf6189527c3c3f86, both arms landed GPU0.

| arm | parse | self-J | median | p95 | file |
|---|---:|---:|---:|---:|---:|
| e4b-ud (incumbent) | 100% | 97.5% | 1.96s | 2.56s | 4.8G |
| e2b-ud (challenger) | 100% | **99.2%** | **1.37s** | **1.68s** | 3.0G |

Cross-arm: dates identical on 119 of 120 (the one diff is a judgment call,
2020-as-program-name); record_type 74 percent, synonym-class variation. The
program field looked like the story at 33 percent agreement and it was, in
the challenger's favour: of 80 disagreements, 70 are the incumbent answering
unknown where the E2B named a program, and ALL SEVENTY are literally present
in the document head, verified string-by-string against the source. Zero
ungrounded commits. The E2B missed 7 the incumbent caught. On the designed
synapse task this is not parity, it is an upset: better grounded extraction,
better self-consistency, 30 percent faster, 34 percent tighter tail, smaller.

Caveats carried, not smoothed: one task shape, one sample, one silicon;
cross-silicon arms owed before any fleet decision; the incumbent arm ran our
one-revision-stale UD copy (currency flag in its dossier). The vision arm is
STRUCK by operator ruling the same evening: the synaptic layer carries no
imagery by design (a carrier parses deterministically, hands off, sheds, and
wipes; eyes belong to the face and the vision seats), so synapse serves drop
the mmproj and the swap gate instead verifies that no live caller sends
images to a carrier port and that the view's default vision picker resolves
to real vision seats. FOR UPSTREAM queued in the e2b dossier: the field's
E2B data is mostly a QAT quant that no longer loads in llama.cpp.

**SWAP DIRECTED (operator, same evening):** the heat's data rules that the
E4B minis can be swapped board-wide, behind the gates: cross-silicon bounded
arms, the no-imagery-callers check plus vision=false on synapse seats,
distribute-flip-verify by the proven UD pattern, sustained stability after.

**GATE 1 COMPLETE, 2026-08-04 23:59 (run cross_silicon_20260804T222841,
manifest in the runs lane). PASS, with a finding the house laws will keep.**
1,920 calls across the four carrier hosts, zero errors, paired arms beside the
resident seats, eyeless serves.

| home | arm | parse | self-J | median | p95 |
|---|---|---:|---:|---:|---:|
| ada-4090 | e2b / e4b | 100 / 100 | 95.8 / 99.2 | 1.65s / 2.63s | 1.9 / 3.2 |
| gb10 hub | e2b / e4b | 100 / 100 | 95.8 / 99.2 | 4.26s / 7.30s | 4.9 / 8.6 |
| gb10 specialist | e2b / e4b | 100 / 100 | 95.8 / 99.2 | 4.75s / 7.35s | 5.4 / 8.7 |
| strix halo | e2b / e4b | 100 / 100 | 97.5 / 99.2 | 4.84s / 8.55s | 5.8 / 10.9 |

What holds everywhere: 100 percent parse, a 35 to 45 percent speed win, and
the integrity result, EVERY E2B program commit grounded in the source on
every silicon (78/78, 41/41, 44/44, 44/44, 42/42). The model never invents;
platforms change how often it commits against abstaining. The Blackwell run
was its most committal host (78 named) and the carrier hosts run 41 to 44,
still roughly three times the incumbent's 10 to 15 on those same homes. The
upset shrinks and does not reverse. Cost, stated plainly: the incumbent is
steadier per platform (self-J 99.2 uniform against 95.8 to 97.5).

**The finding: E2B answers are platform-determined, not noisy.** The twin nodes
(same silicon, same llama.cpp build d05fe1d) agree 120 of 120, perfect
determinism; across platforms agreement drops to 72 to 78 percent where the
E4B holds about 92. Platform here means silicon plus serving build (the primary node
9138, the twin nodes d05fe1d, the AMD node e48034d vulkan; the confound is not separable
tonight and does not need to be, because the deployment condition includes
both). Consequence for the synapse design: with a small model, one
instrument one reader applies at PLATFORM granularity. A scored stage never
spans platforms on E2B, and cross-node aggregation of synapse tags treats
each node's platform as its own instrument, which the manifest fingerprints
already make recordable. FOR UPSTREAM updated: five-platform,
three-build, sha-verified same-weights data on temperature-0 cross-platform
commit-rate sensitivity in a 2B is a control almost nobody can run.

Flip ruling is the operator's, morning, with the nestle's endurance windows
beside this.

**THE NESTLE, complete 2026-08-05 04:45 (run nestle_20260804T223742,
manifest in the runs lane).** E2B resident on the 5090 for six hours,
eyeless, clean card, the frozen sample looped serially at temperature 0:
**16,270 calls, zero errors, zero restarts.** Median 1.35s in every one of
thirteen half-hour windows to two decimals, p95 1.65s flat, parse 100
percent throughout, first-window to last-window drift +0.0 percent. Hour six
equals hour zero exactly. The endurance half of the full measurement set is
in: the challenger does not drift, does not degrade, and holds the card's
first-hour rate all night, which is the same license the chair and the GB10
earned and the strongest flat table this bench has produced. The physical
half agrees (839 samples over the window): the 5090 held median 65C, max 73,
at median 323W of its 575W cap, 56 percent of envelope with ten degrees of
headroom, the body as flat as the table.

**GATES 2 AND 3 EXECUTED, 2026-08-05 morning (operator: "clear to flip the
lineup").** Gate 2 verified before the flip: no live caller sends imagery to
a carrier port (the client apps reference carrier names for display only),
the explicit-seat vision path 400s loudly on an eyeless seat, and the
default picker resolves gemma-26b first, then the vision seat, then olmocr7b: the
face holds the eyes. Gate 3: gemma-4-e2b registered eyeless, four
seats flipped, board spec in the same edit, the carrier serve script to the E2B
with no mmproj, three node pulls, four restarts, four wire verifications,
and four word-perfect temperature-0 generates ("carrier online"). The fleet view
restarted; registry confirms vision False on all four carriers. The vision seat
keeps the E4B and its eyes by design; E4B UD stays on every store as the
one-generation rollback, QAT behind it as the second.

**Gate 4, the production soak:** the carriers now serve E2B under the daily
gates (odometer, recorder, morning report, the five integrity gates). The
first production day is the soak, and the platform-determinism finding
rides with it: each carrier's tags carry its platform as instrument
identity. Campaign remains open until the first clean morning report over
the new lineup.

**8. The code-seat heat (portfolio-scoped).** Replaces the Devstral
presumption (portfolio ruling: no single campaign directs the hardware).
Candidates on disk first: the staged code candidate, gpt-oss-20b, the 26B, the twin nodes as judgment
reference; Devstral held as a candidate pending this rung. Tasks drawn from
the project corpora, not one campaign's shape; graders are the gate harnesses
where they exist and the twin nodes elsewhere. The winner claims the code lane,
and only then does any pull conversation open. Card:
portfolio-over-campaign-hardware.

## Standing method

The setlist runner's own laws carry: assert the physical GPU before
measuring, keep voided rows, phase load cost is scheduling data. Anything
this ladder measures lands in the runs lane the same day it is measured,
because a result without its configuration is the failure mode this room
spent the week closing.
