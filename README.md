# Global X Camera

An STM32N6-based, credit-card-size monochrome global-shutter camera project. This repository is the durable project record; chat and Page copies are working views. Latest hardware wiring update: November 10, 2026. Installed firmware and control smoke test: November 9, 2026.

**Public repository:** [bigjosh/global-x-camera](https://github.com/bigjosh/global-x-camera), created at the user's explicit request on October 13, 2026. The default branch is `main`.

## Start here

**November 10 USB HOLD correction — not yet installed:** USB mode now
requires A3 HOLD LOW after VBUS detection, before loading the USB app, and
through service/error/shutdown paths. Early pre-selection boot/UART recovery
still uses provisional HIGH; battery capture is unchanged. The installed
November9 image still holds through USB. [Policy and implementation status](firmware/usb-ptp/README.md).

**Latest installed firmware (November 9):** the combined capture/USB package now
uses A3/CN4.4/PA2 HOLD before the original UART guard and through operation.
Both programmed NOR regions matched full readback. UART recovery passed after
installation, the ADC diagnostic and an actual JS power cycle. The knob
sweep read A1 from0 to3840 with A0 LOW/A2 HIGH; stopping the diagnostic
drove A2 LOW while retaining A3 HIGH. Normal capture exposure remains fixed.
[Installation and smoke evidence](firmware/control-smoke/evidence/2026-11-09-a3-live/README.md).

**USB baseline (November 8):** native PTP photo access remains in the package. CN8 VBUS present at
boot selects **Global X RAW Camera** in Windows; the native camera driver can
browse thumbnails, download lossless 16-bit gray PNGs, and explicitly delete
individual photos. No driver replacement or FAT filesystem is needed. Two
new captures, deletion/slot reuse, preserved-neighbor hashes, reboot persistence
and real transfer cancellation passed. UART recovery remains available.
[Usage and limits](firmware/usb-ptp/README.md) and
[qualification record](firmware/usb-ptp/evidence/2026-11-08-native-ptp/README.md).
The November9 tests used direct5V through JS with CN8/MCU USB and the sensor
disconnected. The no-sensor error path reached about3.21mA with retained SBF=1;
physical A3 release and real-latch takeover/cutoff were not measured. JS was
left OFF, measured current zero, and COM8 closed. USB service and image capture
were not repeated in this sensor-absent test. See AGENTS.md before bench work.

**Capture baseline retained from October 28:** automatic single-frame capture is
installed, retaining Ethernet power-down and four-bit 25 MHz SD saving. The
cold awake proof showed one frame/exposure, zero explicit STOP writes and
stable autonomous standby. Three normal cold cycles each passed all eleven
phase markers, one observed exposure and UART recovery, with guarded Standby
flags observed afterward. Awake slot 142 matched the original camera RAM;
cold slots 143 and 144 passed complete SD readback and visual inspection.
Slot 145 passed 2,560 of 3,730 sectors before the user stopped testing, so it
is not fully verified. The installed firmware
is ready for the next power cycle; AGENTS.md records the final live state.
See the [single-frame promotion report](firmware/capture-raw/evidence/2026-10-28-sensor-single-frame/README.md)
for firmware identities and qualification limits.

The preceding Ethernet power-down campaign reduced median measured energy from
**224.82 to 173.65 mJ (22.8%)**; median cycle time increased from **396.12 to
413.88 ms**, with variable card latency. Energy excludes the unqualified first
5 ms. The [integration report](firmware/capture-raw/evidence/2026-10-28-ethernet-powerdown/README.md)
records image verification, firmware identity and measurement limits.
The preceding [isolated Nucleo study](docs/power/evidence/2026-10-28-isolated-nucleo/README.md)
contains CPU/cache/sleep controls and hardware-modification estimates.
See AGENTS.md before bench work.

**Canonical prototype power connection (October 27):** regulated source -> JS110 IN+ -> JS110 OUT+ -> **Arduino CN5.5/5V**; common return -> **CN5.6/GND**, with all CN9 shunts absent. [Source options, wiring and measurement limits](docs/power/nucleo-debug-isolation.md#canonical-target-power-connection--october-27).

**November 10 canonical hardware:** a manual SPDT power selector replaces
the USB-controlled cutoff MOSFET Q3. It selects USB power or the output of
battery-path R0=2.2 ohm into CN5.5/5V, with common ground at CN5.6. Q1/Q2,
the separate momentary SPDT trigger, C3=2.2uF and R5=1kohm remain. The PCB
will use **automatic MOSFET source control** rather than the manual selector.
HOLD remains **A3/CN4.4/PA2**; exposure is **A0 LOW / A1 wiper / A2 HIGH**.
The new ASA pot is **A4 high end / GND low end / A5 wiper** and will set
**analog gain**. ASA sampling and both knobs' camera integration are pending;
the installed firmware is unchanged. The user confirmed trigger/HOLD/error
cutoff with zero indicated current before this hardware update.
[Canonical wiring and diagram](docs/power/2026-10-14-power-tree-review.md#november-7-lipo-button-and-pd7-hold-wiring),
[control pin table](docs/hardware-firmware-interface.md).
Do not run old A3–A5 diagnostics against the new latch.

Read [NOTES.md](NOTES.md) for the reasons behind decisions, rejected approaches and hard-won constraints. Its map leads to the owning folder; the [bootstrap coverage record](docs/notes-bootstrap-2026-10-24.md) explains which sources were reviewed.

1. [Decision register](docs/decisions/2026-10-13-project-baseline.md) — accepted requirements, discoveries, future directions and remaining decisions, with local evidence.
2. [Design specification](spec.md) — current prototype requirements alongside explicitly identified recovered hardware.
3. [Power implementation study](power.md) — button/RUN/HOLD, OFF-current budget, shutdown and USB integration.
4. [Consolidated project review](reports/Global%20X%20Camera%20decision%20review.md) — project-wide synthesis and engineering backlog.
5. [Prototype parts and camera research](docs/prototype/prototype-parts-and-camera-research.md) — procurement status, sensor/optics comparisons and qualification limits.
6. [Hardware and firmware interface](docs/hardware-firmware-interface.md) — current behavior requirements and inherited pin-map obligations.
7. [Prototype power-cost comparison](docs/power/power-cost-comparison.md) — estimated battery energy for 5 V Nucleo, modified 3.3 V and custom hardware, with assumptions and a reproducible calculation.

8. [50 ms cold-start risk review](docs/decisions/50ms-cold-start-review.md) — sensor revision, MCU boot load, power startup and storage recovery risks; no measured timing compliance yet.
9. [First camera capture](firmware/bringup/README.md) — working RAM-only Nucleo/VD56G3 test, reproduction scripts, sensor identity and measured results.
10. [Automated power cycling and first GPIO](firmware/boot-timing/bench-results-2026-10-17.md) — three recorded CN8-powered autonomous starts, 15.20–15.43 ms from NRST rising to the first GPIO; includes the earlier source/reset problem and measurement limits.
11. [PCB readiness punch list](docs/review/2026-11-10-pcb-readiness-punch-list.md) — November 10 hardware review before custom-PCB design: open clarifications, problems and improvements in severity order. Review findings for discussion; nothing in it is a decision.

## Current position

**Storage format selected October 24:** the normal firmware captures packed RAW10 directly
into fixed SD slots, with all reserved photo metadata in the first sector.
Each 3730-sector slot contains `GXR2`, 152 metadata bytes, 1,909,600 image bytes
and trailing `GXRE`. The metadata bytes are zero for now; date/time and other
field schemas remain deferred. One sector read obtains occupancy and metadata;
checking completion requires the last sector too. The host also recognizes the
previous `GXRS` layout, so old and new photos may coexist without erasing the
card. This simple layout is preferred for its future NAND mapping even without
a current SD speed gain. See the [RAW implementation](firmware/capture-raw/README.md),
[format and host utility](firmware/raw-slots/README.md), and
[decision record](docs/decisions/raw-sd-slots-2026-10-24.md).

Normal and 230.597 ms long-exposure RAM tests each matched every SD image byte
to original camera RAM. The long test began writing 9.447 ms before FRAME and
checked twenty immediate LINE snapshots. Full readback of original GXRS slot 0
remained byte-identical after the new captures. A normal installed cold boot
saved slot 9, passed first-attempt warm UART recovery and an independent
Standby check, and passed complete image readback and visual inspection.
Its original RAM was lost in Standby; the two RAM tests supply that comparison.
A directory test retrieved each slot's occupancy and metadata with one sector
read, leaving completion unchecked. The layout change performed no erase.

**Historical October 24 transfer profile:** native one-bit SDMMC2 at 25 MHz
sent CMD55/ACMD23 and one CMD25 per image;
complete objects use IDMA and arriving objects use progressive PIO with hardware
flow control. The final sector remains withheld until capture validation and
sensor STOP. First safe publication remains 89,600 bytes. There is no on-camera
PNG conversion, compression, allocation table or separate header rewrite;
host extraction reconstructs PNG. CPU sleep during active DMA stays disabled.

The [current selected profile](firmware/capture-raw/README.md#current-selected-profile--october-28-single-frame-at-25-mhz-with-ethernet-power-down)
uses four-bit 25 MHz SDMMC2 and confirms autonomous sensor standby before
completion; it does not issue the historical successful-path sensor STOP.

The historical v17d comparison measured medians of **998.118 ms / 536.883 mJ**,
versus **997.516 ms / 549.897 mJ** for header-format v16. These are not v18
measurements. No speed gain was established; the observed 2.37% energy reduction
was confounded by card state, an intervening erase and three samples per build.
The [front-metadata qualification](firmware/capture-raw/evidence/2026-10-24-front-metadata/README.md)
is separate from that [earlier comparison](firmware/capture-raw/evidence/2026-10-24-magic-slots/README.md).
Markers are not payload checksums; arbitrary power loss and isolated
DUT/battery energy remain unqualified. Consult the latest `AGENTS.md` checkpoint
before operating the shared bench. Older checkpoints below describe their dated
experiments, not the current programmed image or wiring.

**Startup optimization follow-up, October 17:** CH5 now measures main MCU VDDIO. The first marker remains about 23 ms from the measured 5 V rise; fixed JS110 range provided no useful improvement. The tiny original payload already contains no HAL or camera application. Experimental post-marker diagnostics are being tested; exact NOR-sector restoration is preserved. See the [measurements, hypotheses and current firmware state](firmware/boot-timing/optimization-results-2026-10-17.md).

The prototype uses STM32N6, CAM-6G3-073CLR / VD56G3 at 73° diagonal field of view, and four series CR2032 cells through LTC3621. Exposure must start within 50 ms of a button press from fully off. Store at least 200 full-resolution uncompressed RAW10 photos; preserve photos when full. Ignore presses while capturing or saving, with no queued exposure. USB powers a PTP camera interface with explicit per-photo deletion and disables shutter operation; connection or download alone never deletes photos. Full-image readback is configurable; mandatory save/commit checks remain.

The main-path OFF-current target is 0.1 µA at room temperature, with RTC backup separately budgeted. The finished-product thickness target is ≤5 mm; a thicker functional prototype is allowed. These are requirements, not measured results.

**Hardware bring-up, October 15:** the delivered Nucleo and mounted CAM-6G3-073CLR produced recognizable 640 × 480 monochrome snapshots at 10 ms exposure and unity gain. The sensor reports model `0x5603`, revision `0x3110`, ROM `0x0420`; this revision selects the inspected driver's fast-boot path. The [RAM-only test](firmware/bringup/README.md) retrieves pixels through ST-Link and preserves the code and diagnostics. An earlier startup CSI error remains to investigate; final snapshots reported no new errors. Full-resolution RAW10, cold-start timing, battery operation, NAND and PTP remain unverified. No OTP or external flash was programmed, and no power/debug isolation rework was performed.

The recovered KiCad design still contains the older camera, memories and power circuit. A reviewed reconstruction and clean ERC are not a fabrication release. The [47-item engineering review](docs/DESIGN-REVIEW.md) remains the implementation backlog until findings are closed with evidence. That original review predates the working capture/save/Standby prototype linked above.

**Autonomous boot, October 17:** the separate [first-GPIO image](firmware/boot-timing/README.md) remains programmed in NOR after a complete backup. CN8 USB → CN9.3 → JS110 → CN9.2 now supports API-controlled power cycling: three recorded repeats reached PD0 **15.20–15.43 ms after NRST rose**, or **22.67–22.90 ms after target 5 V crossed 0.5 V**. Both measured rails had stayed below 0.1 V for about 13 seconds. A one-time hardware-reset pulse released an initially stuck NRST; no debugger command occurred during the repeat cycles. The earlier approximately 50 ms reset hold did not recur, although its cause remains unresolved. No sensor capture occurs in this image, so the 50 ms exposure requirement remains unqualified. The board remains in normal flash boot (JP1/JP2 pins 1–2); the original [October 16 results](firmware/boot-timing/bench-results-2026-10-16.md) describe the earlier ST-LINK-powered setup.

## Record structure and precedence

| Location | Purpose |
|---|---|
| `NOTES.md` at root and owning folders | Append-only rationale, rejected alternatives, constraints and deferrals, with evidence. See the root map; later entries supersede earlier choices. |
| `docs/decisions/`, `spec.md`, `power.md` | Current accepted decisions and implementation obligations. Later dated user decisions take precedence over older proposals. |
| `reports/` | Current consolidated synthesis; linked from the decision register. |
| `docs/prototype/` | Dated shopping and camera/optics research. An order being placed does not confirm every suggested part was bought. |
| `docs/review/`, `docs/DESIGN-REVIEW.md` | Findings about the recovered circuit; retain until fixed or explicitly superseded. |
| `docs/power/`, `docs/manufacturing/` | Dated models and candidate studies. Their assumptions and stock snapshots remain historical. |
| `hardware/` | Recovered editable KiCad projects, provenance and validation; see [hardware README](hardware/README.md). |
| `firmware/bringup/` | Reproducible RAM-only camera capture test; local scene images stay in ignored temporary storage. |
| `imports/flux/` | Original Flux exports and recovery evidence. |
| `datasheets/` | Local primary-source archive with source manifests. |
| `research_notes/Global X Camera decision review/` | Initial audit, coverage inventories, historical chat evidence and current-review evidence export. |
| `tools/` | Reproduction, analysis and validation utilities. Schematic generators can overwrite generated design files; read their documentation first. |

Future work explicitly retained: higher-resolution VD5943 with compact/custom optics; mechanical frame advance winding a spring; and a series-capacitor start pulse to reduce held-button drain. None is a prototype requirement.

## Documentation maintenance

Read root and relevant folder `NOTES.md` before making changes. Append a dated note when rejecting an alternative, learning a non-obvious constraint, removing something or consciously deferring a choice; keep each reason in one owning folder and link from elsewhere. Update current behavior in the affected README, specification and decision register, while preserving superseded studies and immutable measurement evidence. Notes record why; they do not duplicate the implementation or every checkpoint. Record a measured result only with its setup and evidence. Keep the repository sufficient to resume work without access to a chat account. The [current-review evidence export](research_notes/Global%20X%20Camera%20decision%20review/chat_sources/2026-10-12-13-current-review.md) preserves the user approvals and assistant findings that led to this baseline.

Imported Claude conversations could not be located; the user authorized proceeding without them. The coverage record identifies what was reviewed rather than claiming unavailable history was recovered.

Local scratch renders/extractions, KiCad UI state and the live nested save-history directory are excluded from version control. Durable reports, source evidence, design files and a portable backup of the existing KiCad save history are retained.
