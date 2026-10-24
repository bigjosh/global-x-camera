# Global X Camera

An STM32N6-based, credit-card-size monochrome global-shutter camera project. This repository is the durable project record; chat and Page copies are working views. Latest checkpoint: October 24, 2026.

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
10. [Automated power cycling and first GPIO](firmware/boot-timing/bench-results-2026-10-17.md) — three recorded CN8-powered autonomous starts, 15.20–15.43 ms from NRST rising to the first GPIO; includes the earlier source/reset problem and measurement limits.

## Current position

**Latest, October 24:** the prototype captures packed RAW10 directly into fixed SD slots, using native one-bit SDMMC2 at 25 MHz. Each slot contains `GXRS`, 1,909,600 image bytes, `GXRE` and 152 padding bytes, occupying 3730 sectors. There is no on-camera PNG conversion, compression, allocation table or separate header rewrite. The [RAW implementation](firmware/capture-raw/README.md), [slot format and host extraction utility](firmware/raw-slots/README.md), and [decision record](docs/decisions/raw-sd-slots-2026-10-24.md) describe the current path and its qualification. The card was explicitly erased and reports an erased byte of `0x00`; it is no longer a FAT32 drive. PNG reconstruction happens on the host. The prior [PNG/FAT32 firmware](firmware/capture-sd/README.md) remains archived for comparison.

Full SD readback matched deterministic packed patterns and an awake cold-captured scene byte for byte. Installed v17d announces all 3730 sectors with CMD55/ACMD23 and uses one CMD25, followed by card-ready checks, controller deinitialization, peripheral teardown and MCU Standby. Complete frames use hardware IDMA; frames still arriving use progressive PIO with hardware flow control. A 230.597 ms exposure test began writing 9.451 ms before FRAME; first safe publication is presently 89,600 bytes, not 512 bytes. The trailing marker is withheld until capture validation and sensor STOP. Warm UART recovery and the boot-freshness guard remain intact. Fresh three-run medians were **998.118 ms / 536.883 mJ**, versus **997.516 ms / 549.897 mJ** for header-format v16 on the same measured Nucleo branch. No speed gain is established; the observed 2.37% energy reduction is confounded by card state, the intervening erase and the small sample. All six comparison cycles passed recovery, independent Standby checks and complete image readback. CPU sleep during active DMA remains disabled. Markers are not a payload checksum; power-loss protection and isolated DUT/battery energy remain unqualified. See the [latest comparison](firmware/capture-raw/evidence/2026-10-24-magic-slots/README.md), [earlier preerase comparison](firmware/capture-raw/evidence/2026-10-24-preerase/README.md), and latest `AGENTS.md` checkpoint before operating the shared bench. Older checkpoints below describe their dated experiments, not the current programmed image or wiring.

**Startup optimization follow-up, October 17:** CH5 now measures main MCU VDDIO. The first marker remains about 23 ms from the measured 5 V rise; fixed JS110 range provided no useful improvement. The tiny original payload already contains no HAL or camera application. Experimental post-marker diagnostics are being tested; exact NOR-sector restoration is preserved. See the [measurements, hypotheses and current firmware state](firmware/boot-timing/optimization-results-2026-10-17.md).

The prototype uses STM32N6, CAM-6G3-073CLR / VD56G3 at 73° diagonal field of view, and four series CR2032 cells through LTC3621. Exposure must start within 50 ms of a button press from fully off. Store at least 200 full-resolution uncompressed RAW10 photos; preserve photos when full. Ignore presses while capturing or saving, with no queued exposure. USB powers a PTP camera interface with explicit per-photo deletion and disables shutter operation; connection or download alone never deletes photos. Full-image readback is configurable; mandatory save/commit checks remain.

The main-path OFF-current target is 0.1 µA at room temperature, with RTC backup separately budgeted. The finished-product thickness target is ≤5 mm; a thicker functional prototype is allowed. These are requirements, not measured results.

**Hardware bring-up, October 15:** the delivered Nucleo and mounted CAM-6G3-073CLR produced recognizable 640 × 480 monochrome snapshots at 10 ms exposure and unity gain. The sensor reports model `0x5603`, revision `0x3110`, ROM `0x0420`; this revision selects the inspected driver's fast-boot path. The [RAM-only test](firmware/bringup/README.md) retrieves pixels through ST-Link and preserves the code and diagnostics. An earlier startup CSI error remains to investigate; final snapshots reported no new errors. Full-resolution RAW10, cold-start timing, battery operation, NAND and PTP remain unverified. No OTP or external flash was programmed, and no power/debug isolation rework was performed.

The recovered KiCad design still contains the older camera, memories and power circuit. A reviewed reconstruction and clean ERC are not a fabrication release. The [47-item engineering review](docs/DESIGN-REVIEW.md) remains the implementation backlog until findings are closed with evidence. That original review predates the working capture/save/Standby prototype linked above.

**Autonomous boot, October 17:** the separate [first-GPIO image](firmware/boot-timing/README.md) remains programmed in NOR after a complete backup. CN8 USB → CN9.3 → JS110 → CN9.2 now supports API-controlled power cycling: three recorded repeats reached PD0 **15.20–15.43 ms after NRST rose**, or **22.67–22.90 ms after target 5 V crossed 0.5 V**. Both measured rails had stayed below 0.1 V for about 13 seconds. A one-time hardware-reset pulse released an initially stuck NRST; no debugger command occurred during the repeat cycles. The earlier approximately 50 ms reset hold did not recur, although its cause remains unresolved. No sensor capture occurs in this image, so the 50 ms exposure requirement remains unqualified. The board remains in normal flash boot (JP1/JP2 pins 1–2); the original [October 16 results](firmware/boot-timing/bench-results-2026-10-16.md) describe the earlier ST-LINK-powered setup.

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
