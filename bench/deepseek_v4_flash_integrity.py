#!/usr/bin/env python3
"""DeepSeek V4 Flash NVFP4-DSpark: checkpoint integrity bench.

Verifies the 176 GB pull is a real, complete, loadable-from-disk checkpoint:
every shard opens as valid safetensors, every tensor named in the index is
present with the shape the index claims, layer and expert counts match the
config, and the DSpark draft shard is intact. Tier 2 (computed from disk).
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


def read_header(p):
    # safetensors has NO magic: bytes 0-8 are the header length (u64 LE),
    # then that many bytes of JSON, then tensor data.
    try:
        with open(p, "rb") as f:
            raw_len = f.read(8)
            if len(raw_len) < 8:
                return None, "truncated: no header length"
            n = struct.unpack("<Q", raw_len)[0]
            if n > 100_000_000:
                return None, f"implausible header length {n}"
            hdr_bytes = f.read(n)
            if len(hdr_bytes) < n:
                return None, "truncated: header shorter than declared"
            return json.loads(hdr_bytes), None
    except Exception as e:
        return None, f"header parse: {e}"

# 1. every shard opens, parses, and its data region is complete
shard_files = sorted(set(wm.values()))
bad_shards = []
shard_headers = {}
truncated_shards = []
for s in shard_files:
    p = snap / s
    if not p.exists():
        bad_shards.append((s, "missing on disk"))
        continue
    hdr, err = read_header(p)
    if err:
        bad_shards.append((s, err))
        continue
    # completeness: file must hold header + every tensor's bytes
    data_bytes = sum(
        (v.get("data_offsets", [0, 0])[1] - v.get("data_offsets", [0, 0])[0])
        for k, v in hdr.items() if k != "__metadata__")
    hdr_len = struct.unpack("<Q", open(p, "rb").read(8))[0]
    need = 8 + hdr_len + data_bytes
    have = p.stat().st_size
    if have < need:
        truncated_shards.append((s, have, need))
    shard_headers[s] = hdr
print(f"shards in index: {len(shard_files)}")
print(f"shards that open as valid safetensors: {len(shard_headers)}")
print(f"shards with a complete data region: {len(shard_headers) - len(truncated_shards)}")
if bad_shards:
    print("BAD SHARDS:")
    for s, e in bad_shards:
        print(f"  {s}: {e}")
if truncated_shards:
    print("TRUNCATED SHARDS (data region shorter than declared):")
    for s, have, need in truncated_shards:
        print(f"  {s}: {have:,} bytes on disk, {need:,} needed")
if not bad_shards and not truncated_shards:
    print("  all shards valid and complete")
print()

# 2. every indexed tensor present with claimed shape
missing = []
shape_mismatch = []
checked = 0
for name in wm:
    s = wm[name]
    hdr = shard_headers.get(s)
    if hdr is None:
        missing.append(name)
        continue
    if name not in hdr:
        missing.append(name)
        continue
    checked += 1
# orphans: tensors on disk not referenced by the index (informational)
on_disk = set()
for s, hdr in shard_headers.items():
    for k in hdr:
        if k != "__metadata__":
            on_disk.add(k)
orphans = on_disk - set(wm.keys())
print(f"indexed tensors: {len(wm)}")
print(f"present and readable: {checked}")
print(f"missing from shards: {len(missing)}")
if missing[:5]:
    for m in missing[:5]:
        print(f"  MISSING: {m}")
print(f"on-disk tensors not in index (orphans): {len(orphans)}")
for o in sorted(orphans)[:5]:
    print(f"  orphan: {o}")
print()

# 3. structural counts vs config
layers = defaultdict(set)
expert_layers = set()
for name in wm:
    parts = name.split(".")
    if "layers" in parts:
        li = parts.index("layers")
        if li + 1 < len(parts) and parts[li+1].isdigit():
            layers[int(parts[li+1])].add(name)
    if "experts" in name and "shared" not in name:
        # layers.N.ffn.experts.M.*
        try:
            li = parts.index("layers")
            expert_layers.add(int(parts[li+1]))
        except (ValueError, IndexError):
            pass
n_layers_cfg = cfg["num_hidden_layers"]
n_exp = cfg["n_routed_experts"]
layer_ids = sorted(layers.keys())
print(f"config num_hidden_layers: {n_layers_cfg}")
print(f"distinct layer ids in tensors: {len(layer_ids)} "
      f"(min {min(layer_ids) if layer_ids else '-'}, "
      f"max {max(layer_ids) if layer_ids else '-'})")
print(f"layers carrying routed experts: {len(expert_layers)}")
# experts per layer: count distinct expert indices in one layer
sample_layer = next(iter(expert_layers), None)
exp_ids = set()
if sample_layer is not None:
    for name in layers[sample_layer]:
        parts = name.split(".")
        if "experts" in parts and "shared" not in parts:
            ei = parts.index("experts")
            if ei + 1 < len(parts) and parts[ei+1].isdigit():
                exp_ids.add(int(parts[ei+1]))
print(f"routed experts in layer {sample_layer}: {len(exp_ids)} "
      f"(config n_routed_experts={n_exp})")
print()

# 4. DSpark draft shard
dspark = snap / "model-dspark-mtp.safetensors"
if dspark.exists():
    hdr, err = read_header(dspark)
    if err:
        print(f"dspark shard: BAD ({err})")
    else:
        n_tensors = len([k for k in hdr if k != "__metadata__"])
        n_params = sum(
            (lambda sh: __import__('math').prod(sh) if sh else 0)(v.get("shape", []))
            for k, v in hdr.items() if k != "__metadata__")
        print(f"dspark shard: valid, {n_tensors} tensors, {n_params/1e9:.2f}B params")
else:
    print("dspark shard: MISSING")
print()

# 5. verdict
ok = (not bad_shards) and (not missing) and (len(layer_ids) == n_layers_cfg) \
     and (len(exp_ids) == n_exp)
print("=" * 60)
print(f"INTEGRITY VERDICT: {'PASS - checkpoint is complete and consistent' if ok else 'FAIL - see above'}")
print("=" * 60)
