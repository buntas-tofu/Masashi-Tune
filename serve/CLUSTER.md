# Distributed serving: the four-node face

Status: DRAFT, not published. Written 2026-10-30. Sections 5 and 8 are
deliberately empty. Everything else rests on a read-only pass against the live
cluster on that date, on two operator-approved completion probes, and on the
vendored launch toolkit, a community DGX Spark vLLM Docker project cloned
locally.
Authority: Tier 2 for anything read from a file or a live system, Tier 3 for
observations labeled as such, Tier 1 for operator rulings.
Floor: DMF. No em dashes, no ellipses. Label inference.

---

## 1. What this chapter covers

This is the shape of the face the rig runs now: one model split across four
nodes, launched by a recipe, checked by a ladder, and measured by instruments
that live elsewhere in this tree. It does not re-teach the bench discipline. A
reader who wants the method should read the bench contract first, because the
discipline is what survives a model swap and this chapter is only one instance of
it.

The chapter has one constraint that shapes every section. It quotes only what a
stranger could reproduce. Where the rig cannot yet produce a number, the section
says so and stays empty. That is not modesty. It is the same rule the rest of the
repository runs on, applied to the one place where a plausible number is easiest
to borrow.

## 2. The topology

Four identical GB10 nodes, each a 128GB unified-memory box, joined by
ConnectX-7. One vLLM server runs in tensor parallel 4 under ray. Rank 0 answers
the API on the head node and the other three are workers. The launcher derives
ranks, node count, and the coordination address from the parallelism flags, so
the serve command never carries them. A reader who types `--node-rank` or
`--master-addr` into the serve line is fighting the launcher, and the launcher
will win in a way that looks like a hang.

On every node the container is `vllm_node` from the `vllm-node` image, and it
sits in `sleep infinity` while vLLM is started through `docker exec`. That
pattern matters more than it looks. It keeps the container alive across a
restart of the server, and it also means the server's stdout belongs to whatever
session ran the exec, not to the container. Section 5 pays for that detail.

Ray reports four active nodes, and the view is the same from every node, which
makes the ray check a single call rather than four. One nuance a reader will
otherwise misread: the toolkit changed its multi-node default to no-Ray in July,
and this face runs ray anyway because the recipe asks for it explicitly. Two
mechanisms, both supported, and the chapter should say which one it means.

## 3. The launch

The recipe file is the intended state. The live process line is the actual
state. A keeper needs both, because they differ here and the difference is the
whole story of the cutover.

The shipped recipe for this model class asks for a 32768 token context and 8192
batched tokens, with tensor parallel 4, fp8 KV cache, prefix caching, and a
memory reservation of 0.78. The live face runs the same geometry at
`--max-model-len 262144 --max-num-batched-tokens 32768`. That is not drift. The
recipe's context is the conservative value that boots anywhere, and the face is
served at the context the practice actually needs. Written down plainly, the
override survives the next keeper. Left as a mystery, it gets "corrected" back
to 32768 by someone with good intentions and no context.

The launch is also where the toolkit's most dangerous failure lives, and it
announces nothing. Run the recipe with `--dry-run` anywhere other than the
cluster head, and autodiscovery fails, the runner falls back to solo mode, and it
prints a complete and plausible command with tensor parallel forced to 1 and the
recipe's conservative context. Nothing in that output says the topology is
missing. A reader could paste it and wait a very long time for a 397B model to
fit on one node. The dry run is trustworthy on the head node and nowhere else,
and the chapter has to say that next to the command rather than in a footnote.

## 4. The model and the caller

The face is `/models/qwen35-heretic`: Qwen3.5-397B-A17B in INT4 AutoRound,
locally abliterated. The served model id is the filesystem path, and every
OpenAI client receives it verbatim. A path is not a name. A client that hardcodes
it inherits the directory layout of one node, and a future keeper who moves the
weights breaks every caller without changing a single flag. The fix is a served
model name plus a restart, which is an operator decision, so this chapter records
the wart and does not paper over it.

The second contract is more expensive to discover. The face thinks before it
answers. A request that does not disable thinking spends its completion budget in
the reasoning field. Measured on 2026-10-30: "reply with the single word OK" at
max_tokens 8, 64, and 256 returned `content: null` with `finish_reason: length`
every time, and the 256 token case contains a 256 token essay about how to say
one word. The text, when it arrives, lands in `message.reasoning` rather than
`content`.

With `chat_template_kwargs: {"enable_thinking": false}` the same prompt answers
in 0.16 seconds, two completion tokens, `content: "OK"`, finish reason stop. So
a caller has two honest options: disable thinking, or budget for it. What a
caller must not do is send a small max_tokens, receive an empty string, and
believe the face is broken. A healthy 200 with no content is worse than an error,
because nothing in the response asks to be read as a failure. This repository
already documents the same family of trap for the math vessels in
`serve/README.md`. The rule generalizes: a generation budget has to cover the
thing the model does before it answers.

## 5. Memory and KV

The live shape reserves 0.78 of each node's unified pool with fp8 KV at 262144
tokens of configured context. At that geometry the binding constraint is the KV
budget, not the weights, and the honest unit of accounting is per-node memory at
a stated occupancy rather than a percentage of a pool that moves.

This section carries no numbers yet, for a reason that belongs in the record. The
server was launched through `docker exec`, its stdout is a pipe into a session
that no longer exists, and `docker logs vllm_node` holds twenty-two lines of
nothing. The startup lines that report KV cache size and load time are gone.
Metrics expose usage but not capacity. Every number this section wants lives in a
transcript that no longer exists, so the section waits for a relaunch under a
persistent log. Until then a reader gets the shape, the reservation, the dtype,
and the rule: launch under tmux or a log file, or the face's own startup
evidence is unrecoverable.

## 6. Three failures worth the space

Three things cost time at cutover, and each one has a receipt.

The first is RoCE v2 GID selection. The IPv4 GID index is not uniform across
nodes and is not stable across reboots, because a node's GID table can gain a gap
and shift the IPv4 entry from one index to another. A single global
`NCCL_IB_GID_INDEX` then breaks initialization on the mismatched node, which
surfaces as `unhandled system error` on the first all-reduce and collapses the
tensor parallel group. The local toolkit clone carries a commit that detects the
GID per node and injects the right index. As of 2026-10-30 that patch exists
nowhere upstream, which means a stranger following this chapter cannot have it.
The operator has held the upstream contribution, so the chapter records the
symptom and the shape of the fix and leaves the patch where it lives.

The second is the Marlin kernel constraint at tensor parallel 4, which the
toolkit addresses with a model-specific mod. The chapter needs the symptom, not
only the mod's name, or a reader hits it and cannot connect the two.

The third is the driver. The toolkit pins 580.x and records a CUDAGraph capture
deadlock on 590.x with GB10 unified memory. That is a hard requirement with a
date on it, not a preference.

## 7. The verification ladder

A keeper checks a face in a fixed order, cheapest first: the container is
running, ray sees the expected node count, the API answers, the served model id
and context are the ones intended, one short completion returns content, and then
a measured run. Each rung has to be able to say no. `serve/verify-face.sh`
implements the sequence read-only, with neutral defaults and an environment
contract for host, port, nodes, container name, expected model, and minimum ray
count. A rung that cannot be decided reports UNKNOWN, never PASS, because a
checker that fails open while answering success is worse than no checker.

The script earned its structure on its first run. Every rung reached the face,
and the model-id rung failed, because the parser grabbed the permission id
instead of the model id. The defect was in the instrument, not the face, and
because each rung reports separately, the failure was legible in seconds. That
is the argument for per-rung reporting and against a single green light.

Two rules come out of the same day. Run the recipe dry-run on the head node, or
treat its output as fiction. And launch under a persistent log, because a face
that cannot show its own startup lines cannot answer the next question anyone
asks about it.

## 8. The measurement slate

Empty by design. The slate is six lines, each waiting on an instrument and a
manifest:

Prefill and decode throughput at 4k, 32k, 128k, and 262144. Tensor-parallel
scaling at one, two, and four nodes. Cold start and load time from local
storage. KV memory per node at fp8 with a stated occupancy. Restart behavior
when a worker is lost mid-run. And an adapter A/B on this substrate, once the
training lane produces one.

Two provisional observations exist in the appendix, clearly labeled. They are
not slate numbers. A number graduates when a file in the tree reproduces it,
which is this repository's law and outranks any schedule.

---

## Appendix A. Session receipts, 2026-10-30

T1, offline suite, run from cloud with PyYAML supplied in a scratch virtual
environment (the default interpreter on this box has no pip): 467 tests, 465
pass, 3 skipped, 2 environment failures, 0 product failures.

- `test_memory_profile_mod` fails because the mod's subprocess interpreter has no
  PyYAML. Environment, not the mod.
- `test_setup_cluster` errors on its own SSH fixture because the temporary home
  under the scratch path trips the ownership and mode check. Environment, not
  the setup code.

T2, recipe dry-run, run from cloud rather than the head node: autodiscovery
failed, the runner fell back to solo mode, and it printed a complete launch
command with `--tensor-parallel-size 1` and `--max-model-len 32768`. The live
face runs tensor parallel 4 at 262144 with 32768 batched tokens.

T3, `serve/verify-face.sh`, first run: the model-id rung parsed the permission id
instead of the model id. Corrected, second run: health, model id and 262144
context, container running on all four nodes, ray showing four active nodes, and
metrics reporting zero KV usage against 159 served requests. Exit 0.

T4, KV occupancy: not obtainable. `docker logs vllm_node` holds 22 lines because
the server was launched by `docker exec`, so its stdout is a pipe into a session
that no longer exists. Metrics expose usage (`vllm:kv_cache_usage_perc`) but not
capacity.

T5, live completion probes against the head node's API port:

- Thinking on, max_tokens 8, 64, and 256: `content: null`, `finish_reason:
  length` in every case. Text arrives in `message.reasoning`.
- Thinking off, max_tokens 16: 0.16 seconds, 2 completion tokens, `content:
  "OK"`, `finish_reason: stop`.
- Prefill probe, thinking off: 24,620 prompt tokens in 7.11 seconds of wall
  time, roughly 3,460 input tokens per second.
- Decode probe, thinking off, 200 completion tokens in 4.86 seconds of wall
  time, roughly 41 output tokens per second, against the recipe's published note
  of about 37 tokens per second single user.

The two throughput figures are single-shot probes, not bench numbers. They have
no manifest, no repetition, and no warm-run control.

T6, the RoCE patch: local only. Origin has moved to 8626c96 (2026-10-29, six
commits past the local origin ref), and `detect_node_gid` appears nowhere
upstream. Ruling, 2026-10-30: upstreaming held. Do not propose it again until the
operator raises it.

## Appendix B. Open work

- Build the bench instrument for the slate, with a manifest per run.
- Decide the served model name and schedule the restart that applies it.
- Relaunch the face under a persistent log so the KV and load-time lines exist.
- Record the Marlin TP4 symptom verbatim from a log, which needs the same
  relaunch.
