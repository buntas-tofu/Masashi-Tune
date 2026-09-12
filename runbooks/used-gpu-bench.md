# Used GPU bench: the function-and-power check

How a used card earns its place in the rig: install it, run it, record what it actually
does, and only then discuss what it costs. This documents the bench of a used
liquid-cooled RTX 4090 into a dual-GPU workstation that already held an RTX 5090.

## Standing rulings

- **Bench before price.** The bench is free. No price conversation exists until the card
  has receipts.
- **If it sings, it lands in the workstation's second slot:** 56GB of CUDA in one box.
- The alternative install into the small CUDA node was stood down and stays down. This
  bench is in the workstation, which is also the placement target, so the bench tests the
  real configuration.

## The hardware

- **Card:** MSI RTX 4090 SUPRIM LIQUID X 24G. 280 x 140 x 43mm, two slots. 240mm AIO, rad
  plus fans 274 x 121 x 55mm, tubes 470mm. Gaming-mode power 480W. Rad fans and pump are
  powered and controlled by the card, no motherboard headers needed. Acquired used from a
  private seller, in hand, untested. The AIO pump is the real unknown; the silicon is not.
- **Host:** the dual-GPU workstation, Ryzen 9, RTX 5090 in slot 1 (Gen5 x16), 1700W PSU,
  modular with a full bag of native cables.
- **Board:** ASUS ProArt X870E-Creator WiFi. The two main x16 slots run x8/x8 from the CPU
  when both are populated, so the 4090 gets Gen4 x8, not chipset x4 as first inferred.
  Verify live after boot.
- **Power:** the dual-GPU build was staged at the factory, with a second native 12V-2x6
  flat-ribbon cable pre-routed through the grommet and coiled at the second slot, plus an
  adjustable anti-sag bracket. Trace the staged cable to the PSU's GPU bank before
  trusting it (verify by hand at install).
- **Case:** Fractal North XL Charcoal Black, mesh, **FD-C-NOR1X-07**.

## Pre-install state (receipts, taken over the overlay before shutdown)

- 5090 idle 48C, 37.28W, 483MiB used (compositor), driver 595.84, CUDA 13.2
- No containers running, load average 0.17, clean shutdown
- Top: 360mm AIO on the CPU. Front: 3x 140mm intake. Rear: 140mm exhaust. Bottom: intake
  mesh.
- Second full-length x16 slot empty below the 5090, electrical width unverified
  (inference: expect x4 chipset lanes on AM5; read the real link after boot)

## Case-specific install sequence (North XL manual v1.0, pages cited)

1. **Front panel: no screws.** Clipped, pull tab at the bottom edge, pull straight off
   (p.21). All front fan work happens from the OUTSIDE face of the chassis.
2. **Displace two intake fans.** Standard long fan screws through the slotted front rails
   (p.31). Unclip their PWM leads at the case fan hub, not mid-run.
3. **Mount the 240 rad** through the same rails into the rad-and-fan sandwich, fans as
   front intake. Height: as high as tube slack allows after a dry fit with the card
   seated; a high mount clears the GPU lane entirely. Tubes toward the bottom of the rad
   if the slack reaches cleanly; either way the rad top must sit above the card pump,
   because air in a used loop collects at the highest point and must be kept off the pump.
   Front limits for reference: 40mm rad thickness, 465mm length (p.36); the Liquid X rad
   is about 30mm bare. If the front panel will not reseat flush, the rad screw heads are
   proud of the rail: swap screws, never force the panel.
4. **Seat the card.** I/O cover plate off if the slot screws are buried (overview part 8,
   p.5). Slot covers out, two screws (p.15). Case flat, lower the card vertically by the
   bracket end and far top corner, no pressure on the pump housing, PEG latch click, then
   bracket screws. Magnetic driver, start screws by hand.
5. **Power.** Native 12V-2x6 cable from THIS PSU's own bag only (modular pinouts are not
   cross-brand safe), PSU socket labeled 12V-2x6 or PCIe 5.1, click both ends, straight
   run, no bend within 35mm of the card connector.

Clearance math: 413mm GPU limit bare, minus rad thickness where they overlap, about 383mm
effective. Cards present are 280mm and about 300mm. No interference anywhere.

## Bench protocol (after boot)

1. `nvidia-smi`: both cards present. Record the new card's VBIOS, link gen and width
   (`nvidia-smi --query-gpu=name,vbios_version,pcie.link.gen.current,pcie.link.width.current --format=csv`).
2. Idle receipts: temp, power, fan and pump behavior at desktop.
3. Sustained load, 15 minutes minimum, watching `nvidia-smi dmon`: core temp (plateau
   expected; a steady climb is the pump failing to move heat), power draw, throttle flags,
   and an ear on the pump. This is the whole verdict on a used liquid card.
4. Receipts land in the bench report: idle temp, load plateau temp, max power observed,
   throttle state, pump verdict.

## Results (bench complete: THE CARD SINGS)

**Verdict: PASS on every gate.** Function, power, and the pump all proven. The bench was
free, as ruled. The card is a working RTX 4090 SUPRIM LIQUID X with a healthy loop.

Install notes as-built:

- Rad thread confirmed 6-32 by the card's previous owner; MSI rad screws were absent from
  the box, so Fractal's 6-32 accessory screws were used instead. Short screws only, never
  long: the coolant channels run millimeters behind the rad face.
- Seated in the second CPU x16 slot. Board bifurcated to x8/x8 clean; the M.2 lane-share
  did not bite.
- First boot: card enumerated nowhere on the bus and its LED lit anyway. Cause: the
  factory-staged 12V-2x6 was routed but NOT connected at the PSU end, and slot power lit
  the LED. Staged is not connected; trace to the click. Second boot clean.
- Container gotcha for the record: in-container CUDA device order does not match
  `nvidia-smi` bus order. `CUDA_VISIBLE_DEVICES` inside the container picked the WRONG
  card (burned the 5090 for 4 minutes at 575W / 81C, itself a free PSU-headroom receipt).
  Pin GPUs at the docker layer with `--gpus device=N` (`nvidia-smi` index), which maps
  only that card into the container.

Bench receipts (900s sustained FP16 8192x8192 matmul, `vllm/vllm-openai` container,
driver 595.84):

| receipt | value |
|---|---|
| enumeration | AD102, VBIOS 95.02.18.80.74, driver 595.84 |
| link | Gen4 x8 (x8/x8 bifurcation with the 5090) |
| idle | 24-28C, about 30W |
| sustained load | 479-480W, 100% SM, 2505-2535 MHz, no throttle flags |
| thermal trajectory | 49C at 1 min, 61C at 3 min, plateau 62C minutes 3-15, zero creep |
| peak temp | 62C |
| cooldown | 62C to 35C in 60s idle |
| sustained compute | 133,000 iterations, about 162 TFLOPS FP16 held for 15 min |
| pump verdict | ALIVE AND HEALTHY. Flat plateau plus fast recovery is a working loop |
| comparison | the air-cooled 5090 in the same box ran 81C at 575W; the liquid 4090 runs 19C cooler at full tilt |

State after bench: both cards idle and healthy. 56GB CUDA total on the node. Placement is
done; this WAS the placement, the card is in its slot. Price conversation is now unlocked
per the ruling, and the report back to the seller can be receipts, not a shrug.

## Provenance

Case manual: North XL User Guide V1.0 2023-07-07, fractal-design.com. Radiator limits:
Fractal support article 4000203863. Card specs: msi.com. Pre-install receipts taken over
SSH before shutdown. Bench numbers are a single run on one card and one driver line,
reproducible by re-running the protocol above.

Floor: no em dashes, no ellipses.
