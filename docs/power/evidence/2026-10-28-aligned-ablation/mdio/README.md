# Offline LAN8742 power-ablation helper

Prepared October 28, 2026. No hardware operation was performed by this helper's
author. The bench owner owns deployment and measurements.

Implementation: [power_phy.inc](../../../../firmware/capture-raw/power_phy.inc).
It is included only in RAM diagnostic modes 3 (unchanged Ethernet control) and
4 (Ethernet general power-down). It does not access camera, SD, NOR, NRST, the
Ethernet MAC, or a global regulator. Call `power_phy_begin(mode)` at the selected
post-FRAME/post-STOP point, and `power_phy_restore()` after SD cleanup on **all**
terminal paths. Both return explicit nonzero errors; neither supplies an idle
proof. No-op restore before begin is allowed; failed restoration retains the
active flag and error.

## Electrical mapping and sources

The [ST MB1940 C02 schematic](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf),
sheet 7, maps MDC to PG11 and MDIO to PF4. R56 is the 1.5 kΩ MDIO pull-up.
R68 straps PHYAD0 low. SB14 joins PHY nRST to target NRST. REFCLKO reaches PF7
through R51. Local reviewed schematic render:
`tmp/hardware-review/nucleo-modifications/ethernet-sheet7.png`.

The [Microchip LAN8742 data sheet](https://www.microchip.com/content/dam/mchp/documents/OTH/ProductDocuments/DataSheets/DS_LAN8742_00001989A.pdf)
defines Clause-22 framing in §3.5, power-down behavior in §3.8.3.1, BMCR in
§4.2.1, identity in §§4.2.3–4 and timing in §5.6.5. Expected IDs are `0007` and
`C13x`; the revision nibble varies. BMCR bit 11 selects general power-down;
management remains accessible. Clearing it automatically resets the PHY and
restarts REFCLKO. Exact restored BMCR is therefore checked twice; preservation
of other PHY registers or negotiated link state is **not** claimed.

## Preconditions and bounds

- Run privileged thread code with GPIO F/G under exclusive caller ownership,
  no Ethernet MAC use, target/PHY supply present and stable, and qualified
  400 MHz CPU/DWT. The helper checks DWT enabled/progress, not actual CPU rate.
- The helper proves GPIO clocks enabled and resets clear before GPIO access.
  It never resets a GPIO bank. Per-pin mode/type/speed/pull/AF/ODR are preserved;
  only newly enabled F/G clock bits are removed afterward. No GPIO reads follow
  clock removal. The rest of each GPIO port is left untouched.
- MDIO is open drain throughout, with no internal pull; released level must
  read high before clocking. This is a digital-level check, not an electrical
  pull-up resistance measurement. MDC is push-pull low-speed GPIO.
- Each half-cycle waits at least 2,000 DWT cycles: nominal 100 kHz at 400 MHz,
  slightly slower with instruction overhead. Interrupts may extend it. DWT
  delays have finite iteration caps; restoration polls at most 100 times.
- Read identities, then two equal BMCR values before any PHY write. Only
  `1000`, `1100`, `3000`, or `3100` is admitted: auto-negotiation enabled and
  normal speed/duplex strap choices, with no reset/restart, power-down,
  isolation, loopback or reserved bits. Both modes perform matched reads and
  one begin write: mode 3 unchanged; mode 4 adds only `0800`.
- Restore identifies the PHY again before writing original BMCR, then requires
  two exact original readbacks and exact pin/clock restoration. There is no
  hidden retry reset or broad register reconfiguration. Unexpected original
  configuration, identity mismatch, turn-around failure or cleanup failure
  remains visible.

## Proof schema

`raw_power_phy_proof` is 64 little-endian words (256 bytes), at a linker symbol
recorded by the parent build. `E_*` in the include is authoritative.

| Words | Meaning |
|---|---|
| 0–5 | `31594850` PH Y1 magic, version 1, mode, stage, begin error, restore error |
| 6–9 | DWT begin, ready, restore start, restore complete |
| 10–16 | Initial IDs, original BMCR twice, requested BMCR, verified BMCR twice |
| 17–20 | Pre-restore BMCR, exact restored BMCR twice, restore poll count |
| 21–23 | Begin GPIO cleanup error, restore GPIO cleanup error, write attempts |
| 24–29 | Begin RCC enable before/after and reset snapshot; restore equivalents |
| 30–31 | Released MDIO observed high at begin/restore |
| 32–37 / 38–43 | Initial PF4 / PG11 per-pin mode, type, speed, pull, AF, ODR |
| 44–49 / 50–55 | Same fields after begin operation and GPIO restoration |
| 56–58 | Restore per-pin equality, pre-wake identity recheck |
| 59–63 | Flags, declared DWT Hz, half-cycle cycles, two reserved words |

Stage 4 means begin succeeded; stage 6 means final restore succeeded. `E1/E2`
identify begin/restore errors. Flags bit 0 records original state captured and
potential mutation; bit 1 records verified restoration. A successful complete
pair has flags 3 and two writes. Hardware operations may have failed even when
cleanup subsequently succeeded; retain both errors.

## Offline verification and interpretation

`compile_check.c` compiled for Cortex-M55 with GCC 12.3, `-O2 -Wall -Wextra
-Werror`. `test_offline.py` runs the production framing, state and cleanup code
against a native register/PHY model with only three hardware leaf functions
replaced. Ten cases cover both matched modes, invalid identity, unstable or
already powered-down BMCR, absent released MDIO high, turn-around failure,
restore mismatch/timeout, disabled DWT, and restore before begin. The generated
`offline-model-result.json` binds the source SHA. These checks establish no
physical waveform, live identity, actual power saving or hardware restoration.

Measure the settled interior of the 200 ms hold, excluding helper entry/exit.
The Ethernet delta includes PHY power, loss in its auxiliary buck, stopped
REFCLKO and any resulting MCU input switching. It is not a pure silicon-current
measurement and does not isolate inrush or establish power savings from removing
U24. Match scene, target rail, clocks, sensor state and instrument settings.
