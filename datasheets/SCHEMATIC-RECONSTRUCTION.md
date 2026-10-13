# Schematic reconstruction inputs

The initial source package was `netlist.edif`, `bom.txt`, and `spec.md`. On 2026-09-05, a [richer Flux snapshot](../imports/flux/2026-09-05/README.md) was recovered: native `.flx`, IPC-2581C, fresh EDIF, and an extended BOM archive. A [16-sheet KiCad reconstruction](../hardware/README.md) is now built and checked against the reconciled physical connectivity. The notes below preserve the source issues and workflow; see the [completed reconstruction record](../hardware/reconstruction/README.md) for resolved issues, explicit additions, and validation. Circuit and manufacturing signoff remain separate.

## Original EDIF/BOM baseline

- The EDIF contains 146 instances and 81 nets, with 538 connected instance/port endpoints. Every endpoint resolves to a defined instance and library port, and no endpoint is assigned to conflicting nets by this export.
- All 146 instance references appear in the BOM, and all BOM references appear in the EDIF. This includes CAM1, which is electrically modeled but excluded from the host PCB.
- The MCU library cell includes 264 logical ports. Components generally have functional port names, which provide a basis for reconstructing symbols against manufacturer pin tables.
- The parsed inventory preserves both EDIF identifiers and display names. For example, a displayed `SS/TR` may use the identifier `SS_TR` in net references.

These are structural consistency checks, not proof of correct circuit connections.

## Current reconstruction and reconciliation work

1. **Physical pin/ball mapping.** The EDIF lacks package-number properties, but native terminal UUIDs recover all 729 physical pin numbers, including U1's 264 balls. Validate that map against archived manufacturer tables, including exposed pads, duplicated supplies, connector orientation, and BGA coordinates. Logical suffixes are not ball coordinates. See [native inventory](../imports/flux/2026-09-05/native-inventory.md).
2. **Values and footprints.** Native per-instance properties resolve the grouped BOM's value/package/rating ambiguity. Embedded footprints and board-level U7/U10 correction rules must be evaluated together. Inductor current/saturation/DCR and MLCC effective-capacitance specifications still need actual MPN selections and verification.
3. **Schematic presentation.** Native symbol positions, wire vertices, rationale, and 187 no-connect records are now available. Recover useful arrangement, then organize readable functional sheets. Native wire/net fragments need semantic reconciliation before they can establish a complete connected schematic.
4. **Terminal semantics and export aliases.** D3's recovered role and footprint identify pad 1 as cathode on SHUTTER_SENSE and pad 2 as anode on LATCH_PULLDOWN. J3 has explicit numbered native terminals despite repeated `~` names. Original and fresh EDIF exports use differing J3 aliases; all non-J3 endpoint memberships match. Resolve connector numbering with native UUID mapping and IPC geometry. Review the custom Tag-Connect mapping against its numbered contact pattern.
5. **Optional circuitry.** SW2/SW3 exist in native source with footprints, placements, intended boot/reset roles, and `Exclude from BOM=true`. They remain absent from the fresh EDIF as well as the original EDIF/BOM. Preserve them as recovered source state, but verify their actual connectivity before incorporating them into a reconstructed netlist.

## Reconstruction workflow

Build an explicit logical-port/UUID-to-physical-pin table from the native inventory, with a manufacturer document/page reference for verification of each device family. Reconcile native fragments and optional circuitry with EDIF and IPC geometry, then create a schematic organized by power/latch, processor/clock/debug, camera, storage, USB, and RTC/accelerometer. Preserve reference designators and verified net membership. Compare the generated schematic's exported connectivity against the reconciled source baseline, run electrical rules checks, and review intentional unconnected pins. Record inference and intentional corrections separately from exact transcription.

The [generated KiCad schematic](../hardware/kicad/global-x-camera.kicad_sch) now passes physical-connectivity comparison and ERC. The [hardware/firmware interface baseline](../docs/hardware-firmware-interface.md) permits electrical review and placement preparation to proceed while existing firmware work is integrated.

## PCB assumptions recorded from the owner

The fabricator is not selected. Use a conventional four-layer, mechanically drilled process as the working target, with the BGA fanout and impedance-controlled MIPI CSI pairs as the main routing constraints. The existing specification also targets USB High-Speed geometry.

The specification's provisional 0.10/0.10 mm trace/space, 0.50/0.20 mm via pad/finished drill, and dielectric dimensions are planning inputs. Confirm the chosen vendor's annular-ring/drill capability and actual copper/dielectric stackup before freezing BGA escape and differential width/gap. A four-layer count alone does not determine impedance geometry. No fabricator, HDI process, or final trace widths have been selected by this documentation task.
