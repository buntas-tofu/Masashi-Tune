# Network core: the management-plane spine

The 10G switch that every node wires to, why it is safe to touch, and how to install it
without taking the fabric down. Companion to `runtime-cutover.md` and `node-onboarding.md`.

## The one hard rule

If the rig has a separate high-speed compute link between two nodes (here, two
GB10-class boxes joined by a 200G ConnectX-7 direct attach cable, the NCCL fabric),
**do not touch it.** Nothing in this runbook goes near a QSFP DAC cable. This is the
ethernet management plane only: each node's RJ45, any USB-C network adapter, the gateway
uplink, and the wireless access points.

## Two planes, so it is clear what is safe

- **Compute plane.** The 200G direct link between the two twin nodes. Untouched. Where a
  twin is the pair's passthrough head, the other twin's heavy egress crosses this link,
  so the second twin's own ethernet stays deliberately light. Sacred; nothing here
  touches its cables. On the real rig this plane is under-exercised by design, built for
  a tensor-parallel workload that has not yet needed to span two nodes.
- **Management plane.** 10G ethernet plus the Tailscale overlay: the view, the keepers,
  SSH, model pulls, and memory sync. This is what the core switch serves.

The fabric addresses itself by name over Tailscale, an overlay. Reshuffling the physical
LAN under it is transparent as long as each node keeps a path to the overlay. Move one
cable, verify, move the next. Low risk by construction.

## Before you unplug anything

1. Identify today's router and DHCP source. That box keeps its job. The switch is a dumb
   layer-2 spine below it, not a router.
2. Note the subnet. **Keep it.** The switch changes cabling, not addressing.
3. Cables: 10G over twisted pair needs Cat6a. Cat5e and Cat6 may negotiate down, so use
   Cat6a for every link you intend to run at 10G.
4. Know your ports before you trust them. On the wireless access points used here, only
   the yellow ports are honest LAN. A blue WAN-capable port is carrier-up and bridges
   nothing, which reads as a dead cable and is not. This trap cost time twice.

## Install order (least critical first, verify between each)

1. Rack and power the switch. Uplink it to today's router or gateway: prefer a 10G SFP+
   port (DAC or fiber module) if the gateway accepts one, else an RJ45 port.
2. **The least critical node first.** Move its cable to the switch and confirm the
   overlay and its services answer.
3. Next node. On this rig the second twin negotiated 10G; on a node whose heavy egress is
   deliberately carried by the compute-plane passthrough, do not chase 10G here unless
   you are deliberately decoupling it.
4. The head node last, or during a lull: it hosts the view, so expect a brief client
   blip. Confirm the view and the registry return.
5. Any node on a slow USB-C adapter: move its uplink to the switch and accept the adapter
   ceiling until a multi-gig adapter lands.
6. Demote the mesh access points to AP mode, each wired to a switch port. They become
   wireless coverage only; the fabric no longer rides them.

## Verify (end state)

- Every wired port reads 10000; a 2.5G node reads 2500; a USB-C dongle reads per dongle.
- The compute plane is unchanged: the direct-link interfaces still read 200000, carrier
  up.
- Fabric health: the board shows every service alive, the view routes, memory writes land.
- The overlay is green on every node.

## Rollback

Any node that loses the fabric: move its cable back to where it came from. Physical plus
overlay, so rollback is one re-cable and no config unwind.

## Switch selection

A dedicated cool room removes the usual homelab objection to 10GBASE-T (heat, noise, a
fan), so all-copper is on the table here where it would be wrong in a closet lab.

**Chosen (2026-07-18, open-box, $300): an 8x 10GBASE-T multi-gig plus 2x 10G SFP+
unmanaged switch, 200 Gbps non-blocking backplane.** It beat the priced alternative on
both port count and price. The unmanaged trade is deliberate and reversible: a flat
sovereign management plane needs no VLANs, and if segmentation is ever wanted, a managed
switch is added then and this one redeploys as an edge switch, never a sunk cost. The two
SFP+ ports are free headroom (fiber or DAC uplink, or growth).

Backplane note: 10 ports x 10G x 2 (full duplex) = 200 Gbps, so the switch is line-rate
on every port at once and is never the bottleneck; each node's own NIC is the ceiling.
Do not conflate this 200 Gbps aggregate management fabric with a compute plane's 200G
per-link interconnect. Same number, separate animals.

Candidates considered (kept for provenance): an 8x 10G RJ45 plus 4 combo, L3-managed,
dual-PSU unit at about $599 (the do-it-once managed core, deferred because a flat plane
does not need managing yet), and an 8x 10G multi-gig plus SFP+ combo, unmanaged, at
about $400 (superseded by the chosen switch for more ports and less money).

Sizing for growth: four nodes on RJ45 plus one uplink leaves three RJ45 and one SFP+
free, comfortable for the next two nodes and an access point or two.

## USB-C adapters, if a node has one

Multi-gig over USB-C is a real path with real limits. An RTL8153-class adapter is a hard
1G ceiling, and a 4K display on the same hub can drop USB data to 2.0. RTL8156 (2.5G) is
long-supported in-tree; RTL8157 (5G) is newer, so confirm the chipset before buying or
keep the vendor driver as a fallback. True 10G needs USB4 or Thunderbolt. Two install
conditions: plug directly into a 10G-capable port, never through a hub (the hub is the
ceiling), and prefer a chipset the kernel already knows.

## Next year (the compute plane, for the record)

Two more twin nodes land next year (four total). The direct dual-cable trick expires past
two nodes: four-way NCCL wants its own QSFP fabric switch (InfiniBand or RoCE), a
separate line item to budget alongside the nodes. That is the compute plane, and it does
not touch this switch.

Prices in this runbook are a dated snapshot from the capture named above; verify before
ordering.

Floor: no em dashes, no ellipses.
