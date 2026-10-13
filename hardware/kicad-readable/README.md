# Readable schematic presentation revision

> **Recovered design only:** this is a presentation of the September circuit, not a second electrical baseline or an implementation of the selected CAM-6G3-073CLR/VD56G3 and LTC3621 prototype. See the [hardware index](../README.md) for implementation status and the [current specification](../../spec.md) for accepted requirements. A more readable drawing does not close the design-review findings.

Open `global-x-camera-readable.kicad_pro` in KiCad 10, or browse
`global-x-camera-readable.pdf`. Start at the functional index; the camera is on
page 7, the boot flash on page 9, and NAND on page 10.

This is a separate presentation of the recovered circuit in `../kicad`.
The original project is preserved for the ongoing electrical design review.
No design-review corrections are incorporated here.

The 14 pages place local support components beside their associated ICs, draw
decoupling banks and local bias networks with direct wires, and group interfaces
into named KiCad buses. `CAM_MIPI` and `CAM_I2C` are separate buses; the MCU,
host receptacle J3 and external camera module CAM1 appear together. Global net
labels preserve the original net names and carry connections between pages.

Values, reference designators, physical pin numbers, pin types, unit assignments,
footprints, component metadata, no-connects and DNP status are preserved.
SW2/SW3 remain optional DNP intent reconstructions, and CAM1 remains external to
the host PCB. Source-recovery assumptions are documented in `../reconstruction`.

Validation is recorded in `review/validation.json`. KiCad's exported netlist is
compared by named endpoint and by complete connectivity partition. The validator
also checks component properties, pin identities and types, no-connect counts,
footprint bytes and source schematic hashes. ERC results are in `review/erc.json`.
Passing these checks establishes presentation equivalence, not hardware signoff.

The independent generator is `../../tools/relayout_schematic.py`; it writes only
this directory and reads the recovered project. After regeneration, use KiCad
CLI to export an XML netlist to `review/netlist.xml`, run ERC to `review/erc.json`,
export the PDF, then run `../../tools/validate_readable_schematic.py`.
Visually inspect all exported pages after changing the layout.

If the recovered circuit changes during design review, regenerate and revalidate
this presentation before using it for board updates. This folder is not a second
electrical source of truth.
