# Startup inrush investigation — November 5

**Later follow-up:** the user removed C14 and reconnected ST-LINK. Three cold
captures and complete image verification are recorded in the
[C14-removed report](../2026-11-05-c14-removed/README.md). This page retains the
earlier preparation and C14-fitted state; it is not the latest bench checkpoint.

The first live checks independently confirm approximately **3.31 mA at 5.00 V**
on the user-modified board. The startup experiment matrix is prepared but has
**not run**: Windows detects JS110 and LP8, but no ST-LINK/VCP. The user has been
asked to reconnect CN10. No target reset, power toggle, firmware load, NOR/SD
transaction or physical modification occurred in this campaign.

## Fresh observations

The user confirms direct regulated5V through JS110 into the target and reconnects
the prior CN15 synchronization wires. U42, D2/R23 and the SD breakout power LED
are user-confirmed removed. The intended contacts remain CN5.5/5V and CN5.6/GND,
with JS IN0/IN1 on CN15.21/PD12 and CN15.33/PD0, GPIO ground CN15.20.

| Measurement | Current | JS input voltage | Input power |
|---|---:|---:|---:|
| Initial API statistics, 22:12:46 UTC | 3.30748 mA | 4.99548 V | 16.5225 mW |
| Last complete 1 s of native static recording | 3.30997 mA | 4.99513 V | 16.5337 mW |
| Final API statistics, 22:19:31 UTC | 3.30792 mA | 4.99545 V | 16.5245 mW |

All three scoped analog streams in that1s window are finite and contiguous.
Both GPIO streams and the current-range stream were recorded, but there was no
firmware event train during this passive recording. Reconnected wire identity
and phase synchronization are therefore not freshly qualified. The low current
is an observed plateau, not a newly read MCU Standby flag.

The initial restricted USB open returned access denied; the permitted direct
hardware session subsequently opened JS110 normally. No other bench process was
found. The UART helper found no matching ST-LINK port and exited **before**
opening a serial device or sending any stimulus. Final Windows enumeration
still contained JS110/LP8 but no ST-LINK. Other unrelated serial devices were not
used. Instrument range128, statistics and streaming/EXTIO settings were restored;
JS was closed and target power left on. No active helper remains.

## Input capacitance audit

This is schematic/BOM evidence, not a measured capacitance or causal isolation.
The principal fitted capacitors directly across target5V total about274uF nominal:

| Capacitors | Nominal total | Supply purpose |
|---|---:|---|
| **C14** | **220 uF** | Main target5V bulk reservoir |
| C19/C23 | 20 uF | Core buck U17 input |
| C76/C82 | 11 uF | Auxiliary buck U34 input |
| C12/C28 | 11 uF | Already-disabled U14 input |
| C74/C52 | 2 uF | Main/AON LDO inputs |
| **C17** | **10 uF** | Removed U42's input capacitor, still connected to5V |

C13/C81 are not fitted. C21/C26 lie across supply feed/sense links, rather than
being ordinary5V-to-ground bulk caps with those links shorted. Removing U42 does
not disconnect C17. Its output capacitor C155 is on the now-isolated output net
and is not a remaining5V input charging load.

C14 is Murata GRM31CR60J227ME11,220uF6.3V X5R1206. Its effective capacitance
under5V DC bias is not established here. Both locator images use ST's actual
assembly vectors with pick/place, ODB++ pad-net and fitted-BOM cross-checks:

- [C14, top side](cap-locations/c14-location.png)
- [C17, underside](cap-locations/c17-location.png)
- [Location sources and rail-sequence limits](cap-locations/README.md)

No removal is selected. C17 is a clean unused-branch candidate but only about4%
of this nominal total. Replacing C14 with47uF would lower the listed nominal
total to101uF, or91uF if C17 were also removed. Those are arithmetic alternatives,
not validated component changes. Keep converter-required local input capacitors.
Input bulk changes also require startup, load-step and shutdown rail checks:
main supplies must remain valid until AUX supplies discharge below0.6V.
[ST AN5967 section3.5](https://www.st.com/resource/en/application_note/an5967-getting-started-with-hardware-development-for-stm32n6-mcus-stmicroelectronics.pdf).

## Reanalysis of historical startup recordings

These are **October28 data with U42 still fitted**, not new measurements on the
current board. The new analyzer exactly reproduced their prior onset, peak,
charge and energy results, and independently reproduced all11 marker timestamps
and energy from the old single-frame candidate02 recording.

| Historical startup | Fixed10A | Automatic range |
|---|---:|---:|
| Native sampled peak | 7.87262 A | 7.90202 A |
| Peak time after current onset | 35.0 us | 35.5 us |
| Net charge, first5ms | 0.934422 mC | 0.945246 mC |
| Raw input energy, first5ms | 3.67579 mJ | 3.73083 mJ |

The fixed10A trace spends127.5us above1A,108.5us above3A,69.5us above5A and
32us above7A. It is not a flat7A load lasting200us. The peak precedes the auto
range transition, so autoranging is not its sole explanation. Physical peak
accuracy, switch response, negative transients and target-side rail voltage
remain unqualified. Input voltage is measured upstream of the JS shunt/switch.
[Original evidence](../2026-10-28-aligned-ablation/README.md#initial-transient-fixed-range-versus-automatic-range).

## Prepared experiments and interpretation

1. Re-establish exact current-firmware UART park and measure its awake current.
2. Record three fixed10A cold normal starts with15s off dwell.
3. Compare cold recovery (no capture application), then reset held across power-on.
4. Compare powered warm reset and a recovery-only off-dwell sweep.
5. Restore exact recovery and leave a measured normal boot or clearly recorded park.

Raw current/voltage/power, both GPI and range codes are retained at2MS/s with
native sample IDs. Analyze0.25/1/5ms windows, signed charge, energy, threshold
durations, data validity, phase overlap and post-startup operation. A reset-held
comparison does not automatically isolate C14: hardware-controlled rail startup
can still occur independently of application code. Short off dwell does not
prove a fully discharged cold boot. No new whole-image verification is claimed.

The new recorder has passive, cold-normal, cold-recovery, cold-reset-held,
warm-normal and warm-recovery modes. Mutations require the exact fresh reviewed
park proof and measured current bounds. Cleanup never re-enables an output left
OFF after an aborted test. **21 offline tests passed** across recorder guards
and analysis invariants; mutating modes still require hardware qualification.

Working campaign: `tmp/bringup/inrush-20261105/`. Archived copies in `support/`
preserve the prepared source; run from the working campaign because path guards
are deliberately tied to that location. `ANALYSIS.md` documents commands and
historical self-checks. The expected installed normal build remains October28
`sensor-autostop-promote-20261028/flash-standby-v1`; its current physical contents
were not reread. The separate SD-DMA-sleep candidate remains offline only.

## Likely hardware direction, pending tests

Input capacitors charge before firmware can schedule their load. A controlled
input rise is the direct way to spread that charge; removing capacitance mostly
reduces charge/duration and does not guarantee a proportional lower peak.
For illustration,274uF charged0–5V over5ms draws274mA of capacitive current,
plus the starting electronics. This is a nominal linear-ramp calculation.

JS110 has no documented programmable supply ramp/current limiter. Its small
current ranges are measurement shunts and must not be used as precharge resistors.
[Driver](https://github.com/jetperch/joulescope_driver/blob/main/src/devices/js110/js110_usb.c),
[JS110 ratings](https://docs.joulescope.com/en/products/js110/guide/specifications.html).
A CT-controlled load switch such as TPS22918 is a candidate for a subsequent
physical experiment, not a selected or installed solution. Its turn-on ordering,
output discharge, load and main/AUX shutdown sequence need circuit qualification.
[TPS22918 datasheet](https://www.ti.com/lit/ds/symlink/tps22918.pdf).
