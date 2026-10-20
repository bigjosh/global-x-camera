# Peripheral-off and Stop qualification — October 20, 2026

This checkpoint covers v57/v58 only. Later Standby tests and the final installed
image belong to the final bench record. The root controller performed all
hardware operations; this note was assembled from its saved evidence.

| Variant | Exact 64 KiB NOR sector SHA-256 | Observation |
| --- | --- | --- |
| v57 peripherals-off, awake | `44ea4f525d965e5b01a5178e4bb12e332f88184be2896e8c412e6ae13fc6caeb` | Capture/save and peripheral teardown verified |
| v58 Stop, SVOS high | `758d5bd20b48282983f434a647aedf46d2561f4732d0ce8fb01dc4dfd883b4e3` | Lower stable current and loss of normal debug access; no direct pre-reset terminal-proof read |

Both use the byte-identical qualified v8b save module. Completion is a separate
CRC-checked blob loaded after saving; the early receiver remains 15,560 bytes.

## v57: verified peripheral teardown

`v57-save-proof/verified.json` records `IMG00037.PNG`, 1,764,993 bytes, result
zero, matching before/after/post-clean frame FNV, finished filesystem rename,
idle card and deinitialized SD controller. Its save-module COMPLETE interval
was 2.441587 s; this excludes cold boot/capture and is image-content dependent.
This was a firmware/frame-integrity proof, not a full file download and pixel
comparison for IMG37.

`v57-lowpower-proof/result.json` verified the live code and checksummed
completion proof: mode 0, ARMED, error zero, peripheral result zero. The
peripheral record reached stage 7 / PDON: CSI/PHY disabled, sensor reset LOW,
CSI/DCMIPP/I2C2/XSPI clocks removed with their required reset sequencing,
NOR nCS HIGH as GPIO, and SD already idle/deinitialized. BSEC and unrelated
clock bits remained enabled. LED outputs were off. This variant deliberately
remained awake.

The prior v54d AF-mode nCS observation was handled by the narrowly qualified
GPIO takeover described in [peripherals.md](peripherals.md). v57 recorded initial
`GPION_IDR=0x8` and final `0x2`, confirming nCS HIGH after takeover. No cause is
claimed for the original AF-mode readback.

A warm UART recovery request subsequently reached the exact early park on its
first attempt: nine good pulses, zero bad pulses, source bit 2, request 1,
CONTROL 0, and idle XSPI. See `v57-uart-recovery/` and
`v57-recovery-park/result.json`.

## v58: Stop behavior and evidence limits

After programming and exact verification, a normal cold boot settled at about
62 mA. HOTPLUG AP1 could not read the completion record; AP0 could not obtain
the core ID, and AP2 was reported invalid. These were bounded read-only
attempts without a target reset or power change.

This is consistent with the deliberately cleared `DBG_STOP` bit. RM0486 Rev4
§78.5.1 (p4377) and §78.12.20 (pp4648–4650) explain that unclocked low-power
domains cannot be debugged without clock/power emulation. §78.10
(pp4395–4396) routes AP0 to DBGMCU and AP2 to the AXI system interconnect;
AP0 is not a substitute path to retained SRAM or PWR. DBGMCU has no direct
live-Stop-status register.

The exact firmware can reach Stop only after successful SAVE, card-ready,
SD deinitialization and peripheral teardown. The stable current reduction
and debug-access loss corroborate that path, but do not replace a directly
read terminal record. No v58 filename or complete PNG verification is claimed
by this checkpoint.

A bounded warm UART reset then reached the exact early recovery park on its
first attempt, again with nine good pulses and zero bad pulses.
`v58-post-reset-flags/result.json` read `PWR_CPUCR=0x00010000`, SBF=0,
STOPF=0. **STOPF is cleared by any reset** (RM0486 p392); its zero value after
NRST is expected and cannot disprove or prove the preceding Stop entry.
SBF has different retention semantics: it clears only on POR or CSSF.
High-SRAM records were not read after recovery, because this early branch
precedes the expanded-memory setup.

## Current observations

The statistics log `v57-session.jsonl` contains both trials. Representative
quiet windows, selected after completion and away from recovery stimulus:

| Variant | Statistics receive timestamps, UTC | Samples | Mean current | Mean input power |
| --- | --- | ---: | ---: | ---: |
| v57 awake/peripherals-off | 18:53:10–18:53:18 | 16 | 77.053 mA | 376.223 mW |
| v58 Stop candidate | 18:55:10–18:55:20 | 20 | 62.124 mA | 303.483 mW |

These are averages of the JS110's approximately half-second statistics at
about 4.88 V input, not MCU-only current, integrated capture-cycle energy, or
a complete board leakage audit. The ranges of interval-average current were
77.017–77.075 mA and 62.098–62.136 mA respectively. Existing debugger/USB and
board supply-boundary limitations still apply.

All evidence paths above are relative to
`tmp/bringup/capture-sleep-20261020/`. The exact build/source/layout review is
`v57-v59-offline-review.json`; later archival should preserve these inputs
and the relevant statistics intervals.
