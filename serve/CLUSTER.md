# Distributed serving: the four-node face

Status: published draft. Written 2026-10-30, updated 2026-11-03 with the
numbers and the launch shape from a relaunch captured under `docker logs`.
Everything else rests on a read-only pass against the live cluster on
2026-10-30, on two operator-approved completion probes, and on the vendored
launch toolkit, a community DGX Spark vLLM Docker project cloned locally.
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

On every node the container is `vllm_node` from the `vllm-node` image, created
by the launcher with `--rm`, which means a container whose foreground process
exits is removed rather than left stopped. The first version of this face ran
vLLM as a `docker exec` child while the container's foreground process was
`sleep infinity`. That shape keeps the container alive across a server restart,
and it also means the server's stdout belongs to whatever session ran the exec,
not to the container. Section 5 pays for that detail: the containers were
removed, and the startup transcript inside them went with the containers.

The shape this chapter recommends, and the one the numbers in section 5 come
from, runs the server as the container's own foreground process through the
launcher's `--launch-script`. Then `docker logs` is the startup transcript, and
a crash reads as a dead container instead of a healthy API with empty answers.
The trade is real and worth stating: with `--rm`, a server crash costs the
container, so the log has to be captured before the next incident, not after it.

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
the wart and does not paper over it. Ruled 2026-11-03: the path stays for now,
so that callers are not broken in exchange for tidiness.

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

Measured 2026-11-03, from one boot whose transcript was captured rather than
lost. These are single-boot figures with a file behind every one of them, which
is the bar; they are not averages and they are not a benchmark.

| measure | value |
|---|---|
| weights in memory, each node | 49.39 GiB |
| KV cache available, rank 0 | 30.11 GiB |
| KV cache available, each worker | 25.82 GiB |
| GPU KV cache size, cluster | 3,132,033 tokens |
| maximum concurrency at 262144 per request | 11.95x |
| CUDA graph capture | 32s, 3.83 GiB |
| weight load, rank 0 | 304.67s |
| model load, rank 0 | 348.69s |
| model load, fastest worker | 190.14s |
| engine init to API ready | 9m28s |

Rank 0 holds more available KV than the workers. The engine reports per rank,
and rank 0's figure is the one a reader should quote for the API node, but the
cluster total is what sets concurrency, and 3,132,033 divided by 262,144 is the
11.95x the engine prints. The load spread across four identical nodes is roughly
1.8 to 1 between the fastest worker and rank 0. Do not read that ratio as a
hardware property yet; it is one boot, from local storage, with no warm-cache
control.

Startup is loud but not alarming, and the classes are worth knowing so a keeper
does not chase them. Fifty-nine warnings during weight load report a float16
scale being loaded into a differently typed parameter, which the loader coerces.
Four classes sit beside them: the ray cluster's token authentication is disabled
in this deployment, custom collectives are off because not every rank has an
MNNVL-capable GPU, FlashInfer all-reduce is off at world size 4, and the model's
own `generation_config.json` overrides vLLM's default sampling parameters. That
last one is caller-facing: a client that assumes vLLM defaults is assuming
wrong.

This section failed once before it worked, and the failure is part of the
record. The first attempt at these numbers was made against a server launched
through `docker exec` while the container's foreground process sat in `sleep
infinity`. Its stdout was a pipe into a session that no longer existed, and
`docker logs vllm_node` held twenty-two lines of nothing. When that server went
down, the containers were removed with it, and any transcript that had landed in
the container layer went too. Metrics expose usage but not capacity, so the
section could not be written from the live system either.

The rule is therefore not "launch under a log file". It is: run the server as
the container's own foreground process, and read `docker logs`. A face launched
inside a container that outlives it has no transcript and no witness.

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
toolkit addresses with a model-specific mod. The symptom itself is still not
captured verbatim, and the honest record says why: with the mod present in the
image, the 2026-11-03 boot names the Marlin path without failing. The log shows
`MarlinLinearKernel for AutoGPTQLinearMethod`, the `MARLIN` WNA16 MoE backend,
and `MarlinExperts` on every rank, and no error beside them. So a reader gets
the healthy path and knows which mod makes it healthy, but cannot yet see what
happens without it.

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
treat its output as fiction. And launch the server as the container's own
process, because a face that cannot show its own startup lines cannot answer the
next question anyone asks about it.

## 8. The measurement slate

The slate is six lines. Two graduated on 2026-11-03, because a boot was captured
that measured them. Four still wait on an instrument and a manifest.

Graduated, with the figures in section 5: cold start and load time from local
storage, and KV memory per node at fp8 with a stated occupancy.

Still waiting:

- Prefill and decode throughput at 4k, 32k, 128k, and 262144.
- Tensor-parallel scaling at one, two, and four nodes.
- Restart behavior when a worker is lost mid-run.
- An adapter A/B on this substrate, once the training lane produces one.

Each of the four needs the same instrument built with the repo's discipline: one
tool, one job, one self-test, and a manifest per run. None of them needs another
relaunch, and none of them graduates from a probe.

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
- Record the Marlin TP4 symptom verbatim from a log. That needs a boot without
  the mod, which is a deliberate failure injection, not a routine relaunch.
- Capture a second boot's load times on a warm cache, so the rank 0 spread in
  section 5 stops being a single observation.

## Appendix C. Session receipts, 2026-11-03

T7, the face relaunched under a captured log. The server was stopped and then
started as the container's own foreground process, per section 5. The stop
completed in 11 seconds. Within about two minutes the container had been removed
on all four nodes: the launcher creates it with `--rm`, and the foreground
process ended. The exact signal that ended it is Tier 3 and unproven. The model
weights were never in the container layer, they are mounted read-only from the
host, so nothing was lost but the container and the log inside it.

T8, the rebuild and the numbers. Image digest verified identical on all four
nodes before launch (sha256 a1fc4f18d3cb1671986feb92b05243ecd31a21957dd64e28da5c9e6125733aa0).
Engine init at 23:12:19 UTC, application startup complete at 23:21:47 UTC, so
9m28s from init to a live API. Weight and model load, 304.67s and 348.69s on
rank 0, 190.14s on the fastest worker. Graph capture 32s at 3.83 GiB. KV 30.11
GiB on rank 0 and 25.82 GiB per worker, 3,132,033 tokens cluster-wide, 11.95x
concurrency at 262144.

T9, post-rebuild verification. `serve/verify-face.sh` with all four nodes and
RAY_MIN=4: health, model id and 262144 context, container running on four, ray
four active, 0 failures, 0 undecided. Caller contract re-probed with thinking
off at max_tokens 16: `content: "OK"`, finish reason stop, 2 completion tokens,
0 reasoning tokens.

The startup transcript behind T8 and T9 is 82K of log, sha256
dc1239574b355f9cc174fdc25a5a10619a2b1981908b780db7f987dbd794d628. It is held
in the operator's estate rather than shipped here, for the same reason the run
tapes are: it carries node addresses and deployment paths. The figures it
supports are quoted in section 5.
