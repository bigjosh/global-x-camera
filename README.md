# Global X Camera

An STM32N6-based, credit-card-size monochrome global-shutter camera project. This repository is the durable project record; chat and Page copies are working views. Updated through October 15, 2026.

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

## Current position

The prototype uses STM32N6, CAM-6G3-073CLR / VD56G3 at 73° diagonal field of view, and four series CR2032 cells through LTC3621. Exposure must start within 50 ms of a button press from fully off. Store at least 200 full-resolution uncompressed RAW10 photos; preserve photos when full. Ignore presses while capturing or saving, with no queued exposure. USB powers a PTP camera interface with explicit per-photo deletion and disables shutter operation; connection or download alone never deletes photos. Full-image readback is configurable; mandatory save/commit checks remain.

The main-path OFF-current target is 0.1 µA at room temperature, with RTC backup separately budgeted. The finished-product thickness target is ≤5 mm; a thicker functional prototype is allowed. These are requirements, not measured results.

The recovered KiCad design still contains the older camera, memories and power circuit. A reviewed reconstruction and clean ERC are not a fabrication release. The [47-item engineering review](docs/DESIGN-REVIEW.md) remains the implementation backlog until findings are closed with evidence. No integrated firmware or measured full capture/save/shutdown cycle is recorded.

## Record structure and precedence

| Location | Purpose |
|---|---|
| `docs/decisions/`, `spec.md`, `power.md` | Current accepted decisions and implementation obligations. Later dated user decisions take precedence over older proposals. |
| `reports/` | Current consolidated synthesis; linked from the decision register. |
| `docs/prototype/` | Dated shopping and camera/optics research. An order being placed does not confirm every suggested part was bought. |
| `docs/review/`, `docs/DESIGN-REVIEW.md` | Findings about the recovered circuit; retain until fixed or explicitly superseded. |
| `docs/power/`, `docs/manufacturing/` | Dated models and candidate studies. Their assumptions and stock snapshots remain historical. |
| `hardware/` | Recovered editable KiCad projects, provenance and validation; see [hardware README](hardware/README.md). |
| `imports/flux/` | Original Flux exports and recovery evidence. |
| `datasheets/` | Local primary-source archive with source manifests. |
| `research_notes/Global X Camera decision review/` | Initial audit, coverage inventories, historical chat evidence and current-review evidence export. |
| `tools/` | Reproduction, analysis and validation utilities. Schematic generators can overwrite generated design files; read their documentation first. |

Future work explicitly retained: higher-resolution VD5943 with compact/custom optics; mechanical frame advance winding a spring; and a series-capacitor start pulse to reduce held-button drain. None is a prototype requirement.

## Documentation maintenance

Record new decisions in the decision register, update affected requirements and the consolidated report, and preserve superseded studies with their dates and assumptions. Record a measured result only with its setup and evidence. Keep the repository sufficient to resume work without access to a chat account. The [current-review evidence export](research_notes/Global%20X%20Camera%20decision%20review/chat_sources/2026-10-12-13-current-review.md) preserves the user approvals and assistant findings that led to this baseline.

Imported Claude conversations could not be located; the user authorized proceeding without them. The coverage record identifies what was reviewed rather than claiming unavailable history was recovered.

Local scratch renders/extractions, KiCad UI state and the live nested save-history directory are excluded from version control. Durable reports, source evidence, design files and a portable backup of the existing KiCad save history are retained.
