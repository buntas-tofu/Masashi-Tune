# Sustained load: the GB10 does not throttle

**2026-08-02 into 08-03.** First fleet telemetry capture, taken while a real campaign ran
rather than against a synthetic loop. Floor: DMF. Dated observation, labeled inference.

**Status: testbed observation.** Instrument: `fleet_telemetry.py`, 30 second interval,
five nodes, 2,806 samples over 4.7 hours. Load: the stage 4 backlog, 133
registrants through the reasoner on the specialist node, 5.6 hours of continuous 120B inference.

## The result

the specialist node, under 96 percent utilisation the entire time, in half-hour windows:

| window | util med | clock med | clock min | temp med | temp max | W med |
|---|---|---|---|---|---|---|
| 0.0h | 96 | 2411 | 2405 | 68 | 69 | 36.8 |
| 1.0h | 96 | 2411 | 2392 | 68 | 73 | 36.6 |
| 2.0h | 96 | 2411 | 2398 | 68 | 72 | 36.9 |
| 3.0h | 96 | 2411 | 2398 | 68 | 71 | 37.1 |
| 4.0h | 96 | 2405 | 2398 | 68 | 75 | 37.0 |

**No droop.** The median clock at hour 4 is the median clock at hour 0. The lowest single
sample across the whole run is 2392 MHz, which is 0.8 percent off median. Temperature held
a 68 degree median and crept 6 degrees at the peak over four hours. Reported draw was flat
within 0.5W.

**What that licenses.** A long unattended campaign on a twin node runs at full speed from the
first record to the last. Throughput does not need a degradation term, and a schedule built
on the first hour's rate will hold. Combined with Grace-Blackwell having no PCIe hop
between host and device at all, the appliance designation the twin nodes already carry is now
measured rather than assumed.

## The comparison nobody has run yet

**The primary node has not been measured under sustained load, and it is the interesting case.** Idle
figures only, from the same capture:

| device | idle W | p95 W | max temp |
|---|---|---|---|
| primary node 5090 | 12.9 | 31.0 | 52 |
| primary node 4090 | 27.2 | 29.9 | 31 |
| hub node GB10 (idle) | 11.2 | 11.8 | 44 |
| 4060 Ti node | 2.9 | 4.2 | 37 |

The 5090 carries a 575W limit and the 4090 a 480W limit, against a GB10 reporting under
40W at full tilt. The primary node was 2.3x faster than the hub node on identical weights in the
extraction bench, and that measurement lasted seconds. **Whether the speed advantage
survives four hours, and at what thermal and power cost, is unmeasured and is exactly the
knee the efficiency work is looking for.** Running the same shaped campaign on the primary node with
this sampler active is the obvious next experiment.

## Two things the capture surfaced on its own

**Residency has a standing cost.** The 4090 idles at 27.2W against the 5090's 12.9W on the
same box. The difference is that the primary carrier and the embedding service are resident on the 4090 holding roughly
4.7 GB, which keeps the card out of its deepest idle state. Call it 14W continuous, about
123 kWh a year, to keep the chair's synaptic layer warm. Cheap, and worth knowing it is
not free.

**Reported draw on GB10 is partial and must not be compared across vendors.** 37W at 96
percent utilisation on a 120B model cannot be a whole DGX Spark module. nvidia-smi is
reporting a rail rather than board power. The number is internally consistent and useful
for tracking a single node against itself over time. It is useless for joules-per-token
against a discrete card, and any efficiency comparison that crosses that line is wrong.

**Strix Halo reports no power or utilisation at all.** amd-smi answers N/A to both
socket_power and usage on the AMD node, so that node contributes temperature and memory only.
If joules per token becomes a real metric, the bar needs a different sensor path before it
can participate.
