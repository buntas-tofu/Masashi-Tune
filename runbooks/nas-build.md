# NAS build: the mirror deck

The rig's storage node: a box whose whole job is holding declared copies. A working
fabric accumulates mass with no replication target anywhere, and this is that target. It
inherits the case and PSU freed by a dissolved install plan.

The tiering model: each concern has a HEAD (the working copy), a MIRROR (a copy on this
node), and a COLD declaration. This box is MIRROR or COLD, never sole HEAD. A head handoff
is a one-line edit in the ledger.

## Why build it now

The heavy single-copy mass lives on working nodes, with no replication target anywhere:

- a personal records archive (finance, tax, business history) that had been a live
  archive of record on one node, single copy;
- a large processed document estate, single copy since a relocation;
- a vault estate, single copy;
- a model zoo and model mass on a node's data disk, re-fetchable in principle but
  expensive in practice.

The finding that shaped the build (see the landed-purchase section below) is that the
genuinely irreplaceable slice is **small**. Everything with no second copy anywhere fit in
a few gigabytes, and it had been sitting exposed while the conversation was about hundreds
of gigabytes of models that any model host would hand back for the cost of a download.
The risk was never the mass.

## Owned, rides in at zero dollars

| Part | Status | Notes |
|---|---|---|
| Lian Li LANCOOL 217 | owned | Four 3.5in bays require ROTATED PSU mode (two cages of two); standard mode holds one cage. Rotated-mode PSU clearance 180mm. Five 2.5in mounts besides. Ships with five fans. |
| Corsair RM1000x (2024, ATX 3.1) | owned | 160mm deep, fits rotated mode with room, fully modular helps in the rotated bay. 1000W is comic headroom for spinning disks; it is also free, so it wins. |

**Verify at the carton:** whether the second 3.5in cage ships in the accessory box or is a
separate part. The vendor page lists two-cage support in rotated mode but is ambiguous on
inclusion. If absent, it is a small accessory order; make it before the drives arrive.

## The buy list (prices a dated snapshot, verify at order)

### Path A, primary: used server platform (ECC plus IPMI)

| Part | Pick | Est | Why |
|---|---|---|---|
| Board | Supermicro X11SSM-F (mATX, C236) | $100-150 used | 8x SATA3 onboard, IPMI (BIOS and console over the LAN, no monitor hauled downstairs), PCIe x8 for the NIC |
| CPU | Xeon E3-1230 v5 or v6 | $40-60 used | 4c8t, more than a replication target will ever need |
| RAM | 2x 16GB DDR4 ECC UDIMM 2133/2400 | $60-90 used | UDIMM, NOT RDIMM; this board takes unbuffered only |
| Cooler | Thermalright Peerless Assassin or Phantom Spirit | $35 | 180mm clearance in the case fits anything; used combos sometimes include one |

Path A subtotal roughly $235-335. ECC on the archive of record is the belt and suspenders
the role deserves, and IPMI is worth real money on a headless basement box.

### Path B, retail alternative (shelf stock, warranty, no IPMI)

ASRock B550M Pro4 (~$90) plus Ryzen 5 5600 (~$85) plus 32GB DDR4 (ECC UDIMM ~$120, plain
~$55). Roughly $230-300 new. ASRock B550 accepts ECC UDIMM with ordinary Ryzen; the
validation is community-grade rather than vendor-sworn.

Rejected for the record: low-power N100/N305 NAS boards. The low idle power is real, but
the typical x1 slot chokes the 10G path, ECC is absent, and the archive role outranks the
watts.

### Drives

| Part | Pick | Est | Why |
|---|---|---|---|
| Data, 4x | 12TB recertified data-center drives (Seagate Exos or WD Ultrastar class) | $90-115 each, $360-460 total | Two sources held this band at capture. Buy from TWO sources or two batches to decorrelate failure. |
| Shelf spare, optional 5th | same class | $90-115 | the spare on the shelf is the resilver you do not wait a shipping cycle for |
| Boot | 500GB-class 2.5in SATA SSD | $35-45 | one 2.5in mount, one SATA port. Boot mirror deliberately skipped: onboarding makes reinstall cheap and the config lives in git. |

12TB is the value band at capture (roughly $8.3/TB against $10.5/TB at 20TB), and four in
two mirrors is roughly 21.8 TiB usable against an estate then measured in single-digit TB.

### Network

| Route | Parts | Est | Read |
|---|---|---|---|
| Primary: SFP+ DAC | used Mellanox ConnectX-3 CX311A (or ConnectX-4 Lx CX4121A) plus a 10G SFP+ DAC, 2-3m | $30-50 plus $15-20 | Lands on one of the switch's two free SFP+ ports, which saves an RJ45 and runs cooler than 10GBASE-T. mlx4/mlx5 drivers in-tree. DAC coding on an unmanaged switch is generally permissive; if the link sulks, swap coding, keep the receipt. |
| Alternative: RJ45 | AQC107 card (ASUS XG-C100C v2 / TP-Link TX401) plus Cat6a | $75-85 | Retail-simple, atlantic driver in-tree, spends a copper port |

Sizing: two mirror vdevs sustain roughly 400-500 MB/s sequential, call it 4 Gbit/s. A 2.5G
link would cap the pool; 10G does not.

### Misc and optional

| Part | Est | Note |
|---|---|---|
| SATA data cables, 4 to 6 | $10 | boards ship with two |
| Second 3.5in cage, if not in carton | $15-25 | verify first, see above |
| UPS, CyberPower CP1500PFCLCD class | $200-230 | PFC sine wave (the RM1000x is active-PFC), covers the NAS plus the switch, NUT for clean shutdown. The one NEW infrastructure piece the archive role justifies. |

### Totals

Core build beyond owned parts: **roughly $700-900** (path A, four drives, SFP+ route).
With the shelf spare and the UPS: roughly $1,000-1,250.

Power, for the basement ledger: 50-65W idle with spindles turning, 30-40W spun down
between replication windows.

## Burn-in (receipts before trust)

Recert drives earn the pool, they are not granted it:

1. `smartctl -t long` on arrival; read the baseline.
2. One full destructive `badblocks -wsv` pass per drive (20-24h at 12TB; run all four in
   parallel).
3. Re-read SMART: zero reallocated, zero pending, or the drive goes back on warranty.
4. Then, and only then, the pool.

## Pool shape

- **Two mirror vdevs** (2x2), not RAID-Z1: pair-wise growth, fast resilver, and a 4-wide
  Z1 resilver is a stress test scheduled for the worst possible day. Usable roughly
  21.8 TiB.
- `ashift=12`, `compression=zstd`, `atime=off`, monthly scrub on a timer, `smartd` wired
  into the keeper's vitals.
- Datasets follow the ledger concerns: `models`, `records`, `corpus`, `venvs`, plus the
  archives. Each dataset carries its declared role. Default posture: this box is MIRROR or
  COLD; HEAD stays on the working nodes.
- **Replication mechanics, stated honestly:** the working nodes are not ZFS, so
  node-to-NAS transport is rsync-class push on timers, and the NAS snapshots each dataset
  after sync, which is what gives retention rules teeth. `zfs send` enters the picture for
  NAS-to-offsite later, not node-to-NAS today.
- Encryption: default OFF (the threat model is basement physical custody); native
  per-dataset encryption available if a concern demands it.

## OS and onboarding

Ubuntu Server, current LTS, matching the rest of the rig; OpenZFS from the archive. Then
the universal node-onboarding sequence (`node-onboarding.md`, minus the GPU steps): the
shared runtime directory user-owned, clone, service venv on system python, a keeper unit
binding the node's overlay IP behind the wait-for-tailnet guard, ENABLE not just start,
board presence as a keeper (vitals and files; no serving service). If another node lands
the same week, this is the pattern's third exercise inside one week, which is exactly what
"repeatable" was supposed to mean.

## Open rulings

1. Board path: A (used, ECC, IPMI) or B (retail, warranty, no IPMI).
2. Drives day one: four (both cages, full frame, recommended) or two (one mirror, stage
   the rest; saves roughly $200 now, costs a second shipping and burn-in cycle later).
3. Network route: SFP+ DAC (recommended, saves copper) or RJ45 AQC107.
4. UPS: in or out.
5. Encryption: per-concern, default off.

## Purchase landed later: a two-bay appliance plus one drive, and what it changes

The operator bought a **two-bay diskless NAS on sale plus one large drive at retail**,
which is not either build path above. Open rulings 1, 2, and 3 are resolved or moot by
purchase; the name ruling is moot. The OS and onboarding section is CONDITIONAL until the
appliance is identified: a Synology or QNAP runs its own OS and cannot take the rig's
pattern (no shared runtime directory, no service venv, no keeper unit), so it lands as an
SMB or NFS plus SSH rsync target and gets no board presence; a UGREEN, Terramaster, or
Aoostar class box usually accepts Ubuntu and the onboarding pattern holds whole. Do not
assume; read the carton first.

**Two bays with one drive is capacity, not redundancy.** Until a second drive lands, this
box is a SECOND COPY and never a mirror, which is still the exact thing the estate needs
but must be written down: ledger posture MIRROR or COLD, never sole HEAD, and a drive
failure here loses the copy, not the data.

### The landing priority, measured rather than assumed

| concern | size | where | risk today |
|---|---|---|---|
| the personal records archive | 4.2G | one node only | IRREPLACEABLE, single copy |
| the processed document estate | 4.1G | one node only | IRREPLACEABLE, single copy |
| the vault estate | 3.4G | one node only | IRREPLACEABLE, single copy |
| sovereign bare repos (the canon origins) | 490M | one node only | working clones exist rig-wide, the BARE does not |
| fabric memory and sediment | 65M | head node, nightly replica elsewhere | has a second copy already |
| **subtotal, the true archive of record** | **roughly 12.3G** | | **lands in minutes** |
| cold model zoo | 475G | one USB-C external | expensive to re-fetch, not impossible |
| live model mass | roughly 730G | four nodes | re-fetchable by design |

**Day one is about 12 gigabytes.** Everything with no second copy anywhere fits in one
short transfer. Second wave is the cold model zoo, which turns a single USB-C drive into a
two-place concern. Third is anything from the live nodes worth a mirror; at the drive size
bought there is room for the entire rig several times over, so nothing needs to be argued
about.

### Burn-in, proportioned to a NEW drive

The burn-in section above was written for RECERTIFIED drives and should not be applied
mechanically here. A new retail drive under warranty earns a `smartctl -a` baseline plus
`smartctl -t long` (a few hours, non-destructive) before it takes data. A full destructive
`badblocks -wsv` pass at 16TB runs 40 hours or more; it is defensible for recert stock and
optional for new stock. The honest read is that the long self-test plus watching
reallocated and pending sectors catches the infant mortality that matters.

Floor: no em dashes, no ellipses.
