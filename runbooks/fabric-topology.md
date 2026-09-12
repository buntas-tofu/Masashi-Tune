# Fabric topology: a dated snapshot

**Current-state caveat: this is a snapshot, not the live map.** It records the rig as it
stood on the date named below, taken from machine profiles and the live board on that
date rather than from the maps. A later snapshot supersedes it, and the living description
of the rig is whatever the operator's own notes say today. Read it as an architecture
narrative and a worked example of a heterogeneous small fabric, not as an inventory to
trust.

**Snapshot date: 2026-08-08** (roughly one week after the dual-GPU workstation joined the
network).

Floor: no em dashes, no ellipses. Label inference.

## The frame

Five nodes, four CPU architectures, accelerators from three vendors (CUDA on the consumer
boxes, ARM-CUDA on the twin accelerators, ROCm on the integrated-GPU node). Roughly 450GB
of addressable model memory across the rig. One control plane, two physical networks, a
few dozen registered services. The operator conducts from the dual-GPU workstation; the
deep reasoning services live on the twins; the face service had just moved to the
workstation.

## The silicon

| role | CPU | accelerator | memory | CUDA | what it does |
|---|---|---|---|---|---|
| dual-GPU workstation | Ryzen 9 9950X (16C/32T) | RTX 5090 (32G, 575W) plus RTX 4090 (24G, 480W), both PCIe x8 | 56G VRAM | 13.2 | the operator's chair; hosts the face service |
| head node | Cortex-X925 (20C, ARM) | GB10-class accelerator | 128G unified | 13.0 | the view, and mirrors the git bares |
| second twin | Cortex-X925 (20C, ARM) | GB10-class accelerator | 128G unified | 13.0 | the bench half of the compute pair |
| small CUDA node | i7-14700F (28T) | RTX 4060 Ti (8G, 160W) | 8G VRAM | 13.2 | second workstation, a resident vision service |
| integrated-GPU node | Ryzen AI MAX+ 395 (Strix Halo, gfx1151) | Radeon 8060S (ROCm) | 130.5G unified | ROCm | the math bench |

Drivers: 595.84 on the consumer-CUDA boxes, 580.159.03 on the twin accelerators. Kernels:
a vendor kernel on the twins, a mainline line elsewhere. Per-node home directories differ
by username convention, so every unit is `%h`-relative and no path hardcodes a home.

The workstation's cards sit at the x8/x8 split (both negotiate PCIe width 8, the 5090 on
gen5, the 4090 on gen4), which is the free-agency arrangement: nothing resident by
default, the cards carry the document, RAG, and burst work. The GB10 boxes report their
accelerator as unified memory rather than discrete VRAM, which is why the profiles show
VRAM N/A for them; the 128G is shared CPU-GPU LPDDR5X.

## The two planes

Two separate physical networks, and confusing them is the standard misread.

- **Compute plane.** A 200G direct attach link between the two twin nodes, the NCCL
  fabric. Confirmed live: the twin interfaces both negotiate 200000 Mbit. The head node is
  the pair's passthrough head; the second twin's heavy egress crosses this link, so its own
  ethernet stays deliberately light. Sacred; nothing touches its cables. **Underexercised
  by design so far:** it is built for a tensor-parallel deep-judge workload that has not yet
  needed to span two nodes.
- **Management plane.** 10G ethernet plus the Tailscale overlay, for the view, the keepers
  on port 9000, SSH, model pulls, and memory sync. A 10-port 10G switch is the basement
  spine: the twins at 10G, the small CUDA node at 2.5G, the workstation at 10G, and the
  integrated-GPU node on a Thunderbolt 10G adapter. Interim by design until the fiber drop
  is drilled: the basement island rides one wireless backhaul hop to the upstairs main.
  Runbook: `network-core.md`. DNS note: the overlay distributes both major public
  resolver sets to every client because Tailscale expands recognized public resolvers at
  the distribution layer, regardless of the stored config; only an in-house resolver
  distributes exactly what it is pointed at.

## The serving stack

- **llama.cpp**, byte-identical rig-wide since a normalization pass. Every GGUF service
  reports the same version string.
- **vLLM** (docker, `vllm/vllm-openai`), the twins at a large NVFP4 model and the
  workstation's vLLM guests (guard, OCR, the bench).
- **Control plane.** The view on the head node, loopback port 8088, fronted on the overlay.
  The registry is config-as-identity in the roster TOMLs. The keeper is the per-node agent
  on port 9000. Clients talk to the view, never a service directly.
- **The daily gates.** Unit drift (all units `%h`-relative, zero portability), machine
  profiles, storage reconcile, model-zoo integrity, and an inference-parameter brief. The
  morning report reads them at 05:52.
- **The guard lane.** A two-tier injection defence: a small Prompt Guard screen on CPU
  (port 8087) plus a Granite Guardian 4.1 8B escalation tier (port 8092). The screen
  catches clear attacks and routes identified templates to the reasoner; the tier judges
  intent where a score cannot.

## The services (a few dozen registered)

**Deep reasoning, always on.** A 120B-class NVFP4 model on each twin, one uniform
substrate, the heavy judgment and adjudication.

**Face and vision.** A 26B-class MoE model resident on the workstation's 5090 as the front
of house, served with reasoning off, and an E4B-class vision service on the small CUDA
node.

**Specialists.** A math model and a coding model on the integrated-GPU node, plus its math
bench guests, all lazy, routed by measured excellence.

**The synapse layer.** Small embedding models, one per node, and small familiar halves, all
E2B-class after a flip. The inverse-parallelism tagging fabric.

**The workstation's free-agent shelf (staged, lazy, on summon).** An OCR model, a guard
model, a 20B general model, embedding and rerank pairs, a prompt guard. Nine specialists on
one NVMe, most never yet woken in production. The wide aperture made physical.

**External.** One off-rig referee model, the only non-sovereign route, used for second
opinions.

## Storage

Per-node model stores: a shared mount on the appliance nodes (they serve from the mount by
decision), a data disk on the workstation and the integrated-GPU node, and a home tree on
the small CUDA node. The workstation's shelf is the largest at roughly 250GB, holding the
free-agent zoo plus the face vessels and their pins. The vault estate and the frozen legacy
era live off the serving path; a reconciler tracks which concern holds HEAD and which
mirror it, with one deliberate unbacked item (the ROCm wheels on the integrated-GPU node).

## The workstation's first week

The arc this snapshot closes:

- day 1: the workstation build, the 5090 and 4090 installed and proven on vLLM.
- day 2: the chair moves, the topology stamped, the casting sweep run.
- day 3: the instruments turn around, units recorded, the daily gates lit.
- day 4: the synapse restoration, the small models re-scoped and auditioned.
- day 5: the embedding and familiar services come online.
- day 6: corrections, the twins measured, llama.cpp normalized, the guard screen built.
- day 7: the face bench, the residence ruled to the 5090, the guard grew its second tier.
- day 8: the face service moved to the workstation, the topology settling.

## Where it points

Three things standing at the snapshot, named without a decision attached:

1. **The compute fabric is a loaded gun not yet fired.** 200G between two 128G twin boxes
   is specced for a tensor-parallel deep-judge workload that so far has always fit on one
   node. Capability waiting for a workload worthy of it.
2. **The ARM-CUDA architecture is under-represented in the model field.** Unified ARM-CUDA
   at 128G is a serving profile the open-weight selection does not yet fit cleanly. The hunt
   continues.
3. **The free-agent shelf is philosophy as inventory.** Nine specialists staged, cheap to
   hold, mostly idle. The wide aperture working as designed, and worth a periodic honest
   look at which are earning their NVMe as the topology settles.
