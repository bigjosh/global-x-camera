# Global X Camera hardware

**Implementation status, October 13, 2026:** these KiCad files are the recovered September VD55G0/TPS62132/AO3401A circuit. The [current specification](../spec.md) selects CAM-6G3-073CLR/VD56G3 and LTC3621 for the prototype; those selections and the known review fixes have not yet been applied. For the agreed behavior and remaining decisions, start with the [consolidated review](../reports/Global%20X%20Camera%20decision%20review.md) and [power implementation study](../power.md). Do not infer readiness from a successful reconstruction check or a newer document date.

Open [kicad/global-x-camera.kicad_pro](kicad/global-x-camera.kicad_pro) in KiCad, then open its schematic. The project uses local symbol and footprint libraries, so no Flux connection is required. KiCad 10.0.6 is installed for the current Windows user.

- [Editable root schematic](kicad/global-x-camera.kicad_sch): 16 functional sheets, 148 components, all MCU units and explicit unused pins.
- [Schematic PDF](kicad/global-x-camera.pdf): complete review copy with clickable hierarchy links.
- [Reconstruction record](reconstruction/README.md): source reconciliation, documented changes, validation and remaining design work.
- [Full design review](../docs/DESIGN-REVIEW.md): confirmed wiring/footprint faults, architecture risks, component coverage and recommended corrections. Review dated 2026-09-05; corrections have not yet been applied to the schematic.

KiCad netlist comparison passes for 737 physical terminals: 550 connected endpoints and 187 explicit no-connects on 81 named nets. All recovered source connections are preserved. ERC reports zero violations with documented supply-source declarations and pin-type modeling. The 147 host footprints load and cover all 703 host physical pins; CAM1 is external.

This is an editable reconstruction for electrical review. PCB placement/routing and manufacturing geometry have not been completed or approved. Keep the project directory together with `GX.kicad_sym`, `GX.pretty`, and both library tables.

The generation scripts under `tools/` reproduce this initial reconstruction. They overwrite generated schematic/library files. After manual editing, use the KiCad files as the working design and preserve those edits before deliberately regenerating.
