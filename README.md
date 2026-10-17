# Global X Camera

An STM32N6-based, credit-card-size monochrome global-shutter camera project. This repository is the durable project record; chat and Page copies are working views. Updated through October 16, 2026.

**Public repository:** [bigjosh/global-x-camera](https://github.com/bigjosh/global-x-camera), created at the user's explicit request on October 13, 2026. The default branch is `main`.

## Start here

1. [Decision register](docs/decisions/2026-10-13-project-baseline.md) — accepted requirements, discoveries, future directions and remaining decisions, with local evidence.
2. [Design specification](spec.md) — current prototype requirements alongside explicitly identified recovered hardware.
3. [Power implementation study](power.md) — button/RUN/HOLD, OFF-current budget, shutdown and USB integration.
4. [Consolidated project review](reports/Global%20X%20Camera%20decision%20review.md) — project-wide synthesis and engineering backlog.
5. [Prototype parts and camera research](docs/prototype/prototype-parts-and-camera-research.md) — procurement status, sensor/optics comparisons and qualification limits.
6. [Hardware and firmware interface](docs/hardware-firmware-interface.md) — current behavior requirements and inherited pin-map obligations.
7. [Prototype power-cost comparison](docs/power/power-cost-comparison.md) — estimated battery energy for 5 V Nucleo, modified 3.3 V and custom hardware, with assumptions and a reproducible calculation.

8. [50 ms cold-start risk review](docs/decisions/50ms-cold-start-review.md) — sensor revision, MCU boot load, power startup and storage recovery risks; no measured timing compliance yet.
9. [First camera capture](firmware/bringup/README.md) — working RAM-only Nucleo/VD56G3 test, reproduction scripts, sensor identity and measured results.
10. [First GPIO boot timing](firmware/boot-timing/bench-results-2026-10-16.md) — two autonomous starts, roughly 63 ms from the 5 V rise, including a roughly 50 ms reset hold whose source remains unresolved.

## Current position

The prototype uses STM32N6, CAM-6G3-073CLR / VD56G3 at 73° diagonal field of view, and four series CR2032 cells through LTC3621. Exposure must start within 50 ms of a button press from fully off. Store at least 200 full-resolution uncompressed RAW10 photos; preserve photos when full. Ignore presses while capturing or saving, with no queued exposure. USB powers a PTP camera interface with explicit per-photo deletion and disables shutter operation; connection or download alone never deletes photos. Full-image readback is configurable; mandatory save/commit checks remain.

The main-path OFF-current target is 0.1 µA at room temperature, with RTC backup separately budgeted. The finished-product thickness target is ≤5 mm; a thicker functional prototype is allowed. These are requirements, not measured results.

**Hardware bring-up, October 15:** the delivered Nucleo and mounted CAM-6G3-073CLR produced recognizable 640 × 480 monochrome snapshots at 10 ms exposure and unity gain. The sensor reports model `0x5603`, revision `0x3110`, ROM `0x0420`; this revision selects the inspected driver's fast-boot path. The [RAM-only test](firmware/bringup/README.md) retrieves pixels through ST-Link and preserves the code and diagnostics. An earlier startup CSI error remains to investigate; final snapshots reported no new errors. Full-resolution RAW10, cold-start timing, battery operation, NAND and PTP remain unverified. No OTP or external flash was programmed, and no power/debug isolation rework was performed.

The recovered KiCad design still contains the older camera, memories and power circuit. A reviewed reconstruction and clean ERC are not a fabrication release. The [47-item engineering review](docs/DESIGN-REVIEW.md) remains the implementation backlog until findings are closed with evidence. No integrated product firmware or measured full capture/save/shutdown cycle is recorded.

**Autonomous boot, October 16:** the separate [first-GPIO image](firmware/boot-timing/README.md) is now programmed in NOR after a complete backup. Two USB power-ups reached PD0 62.75–62.91 ms after the target 5 V rail first crossed 4.50 V. Approximately 50 ms was spent with NRST held low, whose source remains unresolved; the observed NRST edge to PD0 took 12.92–13.43 ms. No sensor capture occurs in this image, so the 50 ms exposure requirement remains unqualified. The board is currently in normal flash boot (JP1/JP2 pins 1–2).

## Record structure and precedence

| Location | Purpose |
|---|---|
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

Record new decisions in the decision register, update affected requirements and the consolidated report, and preserve superseded studies with their dates and assumptions. Record a measured result only with its setup and evidence. Keep the repository sufficient to resume work without access to a chat account. The [current-review evidence export](research_notes/Global%20X%20Camera%20decision%20review/chat_sources/2026-10-12-13-current-review.md) preserves the user approvals and assistant findings that led to this baseline.

Imported Claude conversations could not be located; the user authorized proceeding without them. The coverage record identifies what was reviewed rather than claiming unavailable history was recovered.

Local scratch renders/extractions, KiCad UI state and the live nested save-history directory are excluded from version control. Durable reports, source evidence, design files and a portable backup of the existing KiCad save history are retained.
