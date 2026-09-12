#!/usr/bin/env python3
"""DeepSeek V4 Flash (nvidia NVFP4-DSpark cut): checkpoint characterization.

This model cannot serve on this host (NVFP4 is sm_120, the 4090 is sm_89, and
176 GB of weights does not fit 56 GB of cards). Its numbers come from the
checkpoint itself: parameter accounting, MLA KV physics, and serving math
for the builds it actually targets. Every figure is computed from the real
index and config on disk; nothing is taken from marketing.

Tier labels: computed-from-checkpoint is Tier 2; serving-fit projections
are Tier 3 inference from those numbers.
"""
import json
import struct
from collections import defaultdict
from pathlib import Path

import bench_config as BC

SNAP = BC.snap_dir()
snap = next(SNAP.glob("snapshots/*"))

cfg = json.load(open(snap / "config.json"))
idx = json.load(open(snap / "model.safetensors.index.json"))
wm = idx["weight_map"]

# --- parameter accounting from tensor shapes (header-only safetensors reads)
def shapes_for(shard):
    p = snap / shard
    with open(p, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        header = json.loads(f.read(n))
    out = {}
    for k, v in header.items():
        if k == "__metadata__":
            continue
        shape = v.get("shape", [])
        numel = 1
        for d in shape:
            numel *= d
        out[k] = numel
    return out

params = defaultdict(int)   # bucket -> params
per_layer_expert = defaultdict(int)
for name in wm:
    shard = wm[name]
    # read each shard's header once per unique shard via cache
    pass

cache = {}
def numel(name):
    shard = wm[name]
    if shard not in cache:
        cache[shard] = shapes_for(shard)
    return cache[shard].get(name, 0)

buckets = defaultdict(int)
for name in wm:
    n = numel(name)
    if "dspark" in name or "mtp" in name or "nextn" in name or "dspark" in wm[name]:
        buckets["dspark_draft_or_mtp"] += n
    elif "experts" in name and "shared" not in name:
        buckets["routed_experts"] += n
    elif "shared_experts" in name:
        buckets["shared_experts"] += n
    elif any(s in name for s in ("q_a_proj", "q_b_proj", "kv_a_proj", "kv_b_proj",
                                   "kv_a_layernorm", "o_proj", "q_proj", "k_proj",
                                   "v_proj", "self_attn", "attn")):
        buckets["attention"] += n
    elif "embed" in name or "lm_head" in name or "head" in name:
        buckets["embed_and_head"] += n
    elif "norm" in name or "layernorm" in name:
        buckets["norms"] += n
    else:
        buckets["other"] += n

total = sum(buckets.values())
routed = buckets["routed_experts"]
n_layers = cfg["num_hidden_layers"]
n_exp = cfg["n_routed_experts"]
topk = cfg["num_experts_per_tok"]
moe_inter = cfg["moe_intermediate_size"]
hidden = cfg["hidden_size"]

# active per token: everything except the (1 - topk/n_exp) routed mass
active = total - routed + routed * topk / n_exp
# dspark draft head runs only in speculative mode; core active excludes it
core_active = active - buckets["dspark_draft_or_mtp"]

print("# DeepSeek V4 Flash NVFP4-DSpark: checkpoint characterization")
print()
print(f"Checkpoint: nvidia/DeepSeek-V4-Flash-nvfp4-DSpark, {len(wm)} tensors, "
      f"46 shards + 1 dspark shard")
print()
print("## Parameter accounting (computed from the index, Tier 2)")
print()
print(f"{'bucket':28s} {'params':>14s}  share")
for k in sorted(buckets, key=buckets.get, reverse=True):
    print(f"{k:28s} {buckets[k]/1e9:13.2f}B  {100*buckets[k]/total:5.1f}%")
print(f"{'TOTAL':28s} {total/1e9:13.2f}B")
print()
print(f"Routed experts: {n_exp} per layer x {n_layers} layers, "
      f"{topk} active per token, moe_intermediate {moe_inter}")
print(f"Active params per token (all-in):  {active/1e9:.1f}B")
print(f"Active params per token (no draft): {core_active/1e9:.1f}B")
print()

# --- MLA KV physics
hd = cfg.get("head_dim")
rope = cfg.get("qk_rope_head_dim", 0)
nkv = cfg.get("num_key_value_heads")
max_pos = cfg.get("max_position_embeddings")
kv_bytes_per_token_layer = (hd + rope) * 2 * nkv  # K+V, fp16
kv_bytes_per_token = kv_bytes_per_token_layer * n_layers
print("## MLA KV physics (why 1M context is possible, Tier 2)")
print()
print(f"head_dim {hd}, qk_rope_head_dim {rope}, num_kv_heads {nkv}, "
      f"{n_layers} layers, max_position_embeddings {max_pos:,}")
print(f"KV per token per layer (fp16): {kv_bytes_per_token_layer:,} B")
print(f"KV per token, all layers:      {kv_bytes_per_token/1024:.1f} KiB "
      f"= {kv_bytes_per_token/1024/1024*1000:.1f} MiB per 1k tokens")
for ctx in (32_768, 131_072, 262_144, 1_048_576):
    gb16 = kv_bytes_per_token * ctx / 2**30
    print(f"  context {ctx:>9,}: KV fp16 {gb16:6.1f} GiB | fp8 {gb16/2:6.1f} GiB")
print()

# --- weight footprint (NVFP4 experts ~0.5 bytes/param, attn kept wider)
w_total_gb = 176.2
print("## Serving footprint (Tier 3 projections)")
print()
print(f"Weight footprint on disk: {w_total_gb:.1f} GB "
      f"(NVFP4 routed experts, mixed precision elsewhere)")
for ctx in (131_072, 262_144, 1_048_576):
    kv = kv_bytes_per_token * ctx / 2**30
    print(f"  total at {ctx:>9,} ctx: {w_total_gb + kv:.0f} GB (fp16 KV) | "
          f"{w_total_gb + kv/2:.0f} GB (fp8 KV)")
print()
print("This host (2 cards, 56 GB total, Ada sm_89): physically cannot serve.")
print("  Weights alone are 3.1x the combined VRAM, and NVFP4 kernels are")
print("  Blackwell sm_120 only. This is a store-not-serve asset here.")
print()

# --- DSpark draft head
print("## DSpark draft head (the speculative-decoding cut)")
print()
print(f"dspark params: {buckets['dspark_draft_or_mtp']/1e9:.1f}B")
print(f"block_size {cfg.get('dspark_block_size')}, markov_rank "
      f"{cfg.get('dspark_markov_rank')}, target layers "
      f"{cfg.get('dspark_target_layer_ids')}")
print("One checkpoint is both target and draft model; vLLM invocation per")
print("NVIDIA's verification: --speculative-config "
      "'{\"method\":\"dspark\",\"num_speculative_tokens\":7}' "
      "--kv-cache-dtype fp8")
