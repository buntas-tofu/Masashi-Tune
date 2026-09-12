# DeepSeek V4 Flash NVFP4-DSpark: the characterization bench (2026-08-22)

The NVIDIA cut of DeepSeek V4 landed at 176.2 GB (46 shards + the DSpark
draft shard). It cannot serve on the primary node: NVFP4 kernels are sm_120 (Blackwell)
and the 4090 is sm_89 (Ada), and the weights alone are 3.1x the combined
VRAM. So the bench that puts numbers behind it is a checkpoint
characterization, computed from the index and config on disk, plus an
integrity pass that proves the pull is complete. Nothing below is taken from
marketing; every figure is computed from the checkpoint.

## Integrity (PASS)

Instrument: bench/deepseek_v4_flash_integrity.py

- 46 of 46 shards open as valid safetensors; all data regions complete
  (header + declared tensor bytes present on disk)
- 142,973 of 142,973 indexed tensors present and readable; zero orphans
- 43 of 43 layers present; 256 routed experts per layer, matching config
- DSpark draft shard valid: 9,313 tensors, 11.39 B params

One correction to the record: an earlier spot check claimed the safetensors
"magic byte" verified. safetensors has no magic; the first eight bytes are
the header length. The instrument now checks the actual invariant (header
parses, data region complete) and the verdict above is the real one.

## Parameter accounting (Tier 2, from the index)

| bucket | params | share |
|---|---|---|
| routed experts (256 x 43 layers) | 155.83 B | 89.3% |
| dspark draft head | 11.39 B | 6.5% |
| attention (MLA) | 5.10 B | 2.9% |
| shared experts | 1.08 B | 0.6% |
| embed + head | 1.06 B | 0.6% |
| TOTAL | 174.53 B | |

- Active params per token (core, no draft): 11.0 B (6 of 256 experts per
  layer). With the DSpark draft head engaged: 22.4 B.
- The handoff carried "284B MoE (13B active)". Measured from the index:
  174.5 B total, 11.0 B active. The 176 GB on disk is NVFP4-compressed
  expert mass (0.5 bytes/param on the routed experts), not a 284 B model.

## MLA KV physics (why 1M context is the point)

head_dim 512, qk_rope_head_dim 64, num_kv_heads 1 (MLA), 43 layers,
max_position_embeddings 1,048,576.

KV per token, all layers, fp16: 48.4 KiB = 47.2 MiB per 1k tokens.

For scale against the fabric's measured numbers: gemma-4-26B is 240 MiB/1k,
qwen3.5-27B is 80 MiB/1k, qwen3.8-27B computes to 62.5 MiB/1k. DeepSeek V4
Flash is 5.1x thinner than gemma and 1.7x thinner than the current face.
That is the whole 1M-context story in one ratio.

| context | KV fp16 | KV fp8 |
|---|---|---|
| 32,768 | 1.5 GiB | 0.8 GiB |
| 131,072 | 6.0 GiB | 3.0 GiB |
| 262,144 | 12.1 GiB | 6.0 GiB |
| 1,048,576 | 48.4 GiB | 24.2 GiB |

## Serving footprint (Tier 3 projection)

Weight footprint 176.2 GB. Total at context, fp16 KV / fp8 KV:

| context | total |
|---|---|
| 131,072 | 182 GB / 179 GB |
| 262,144 | 188 GB / 182 GB |
| 1,048,576 | 225 GB / 200 GB |

The dual-Blackwell build the operator framed ("dual spark running an nccl")
needs roughly 256 GB of combined HBM-class VRAM for the 1M headline at fp8
KV, or 224 GB at 262k. A single B300/GB300 node (NVIDIA's verified config,
TP 8 with expert parallelism) is the natural home; the DSpark variant adds
the draft head so one checkpoint is both target and draft model.

## DSpark (the speculative cut)

block_size 5, markov_rank 256, target layers 40-42, 11.4 B params. NVIDIA's
verified invocation: --speculative-config
'{"method":"dspark","num_speculative_tokens":7}' --kv-cache-dtype fp8.
The handoff's description of it as "semi-autoregressive speculative
decoding" stands; the checkpoint confirms the draft rides layers 40-42 of
the same backbone plus its own shard.

## Standing

Store, not serve, on the primary node. Asset banked in the
model store (moved out of the prunable HF cache). Instruments at
bench/deepseek_v4_flash_*.py.
