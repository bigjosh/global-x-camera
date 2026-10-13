# Flux recovery snapshot — 2026-09-05

Recovered directly from the [live Flux project](https://www.flux.ai/bigjosh/global-x-camera~2a) using its Export menu. The original project and the repository's original `netlist.edif`, `bom.txt`, and `spec.md` were not edited. These files preserve an incomplete design; they are not fabrication outputs approved for manufacture.

## Saved exports

| File | Purpose |
| --- | --- |
| [Native project](bigjosh-global-x-camera.flx) | JSON containing component/terminal UUIDs, physical pin numbers, cached library data, schematic arrangement, placements, board rules, and per-instance properties. |
| [IPC-2581C](global-x-camera.ipc2581c) | XML containing board geometry, packages, placement, net-associated pads, and a proposed stackup. Useful as an independent physical reference; no direct KiCad import was attempted. |
| [Current EDIF](bigjosh-global-x-camera.edif) | Fresh connectivity export for comparison with the original repository netlist. |
| [BOM archive](bigjosh-global-x-camera-BOM-V2026-09-05T071229666Z.zip) | Eight vendor-format CSV files, including Flux's extended property export. Grouped values remain less precise than native per-instance properties. |

[manifest.json](manifest.json) records source, export action, file hashes, sizes, and timestamps. The four downloaded files are unchanged. Export times differ, and a common internal revision is not guaranteed. The source native revision marker is retained literally in the manifest.

## What this saves us

The native source recovers **148 components and all 729 terminal pin numbers**, including all **264 MCU BGA balls**. It also preserves embedded footprints, individual passive values/ratings/packages, explicit no-connect records, schematic positions, 147 PCB footprint instances, camera keepouts, and provisional constraints. CAM1 remains external to the host PCB.

This substantially reduces manual reconstruction. Manufacturer pin tables and package drawings still need to validate the imported library data. U7/U10 have saved board-level footprint correction rules: an importer must evaluate those overrides as well as the cached library footprints.

- [Native inventory and pin/footprint evidence](native-inventory.md), with [machine-readable inventory](native-inventory.json).
- [Recovered rationale, mechanical constraints, and missing context](recovered-context.md).
- [Cross-export audit](export-audit.json).

## Reconciliation findings

1. **Component inclusion differs.** Native data includes optional SW2/SW3 with `Exclude from BOM=true`; fresh EDIF still has 146 components, 81 nets, and 538 connected endpoints, omitting those switches. Their intended connections are documented in component rationale but are not yet validated as recovered electrical nets.
2. **J3 aliases differ between EDIF exports.** All non-J3 endpoint memberships match. Several J3 `&__N` / `~_N` aliases differ; native connector terminals all have the name `~`, while their UUIDs carry explicit physical numbers. These export suffixes are not established pin numbers. The difference alone proves neither rewiring nor equivalence. Resolve using native UUID-to-pin mapping and IPC pad geometry before creating the numbered schematic.
3. **Native net records are fragmented.** Its 544 single-pin records must not be treated as 544 independent electrical nets. Two also have no-connect markers. Preserve them and reconcile their grouping with the compiled exports.
4. **IPC is a useful cross-check, with limits.** It contains 145 real host component records plus two synthetic board-root records; CAM1 is correctly absent. Its 81 net names match EDIF. Connectivity appears in `Set/@net` and `Pad/PinRef`, not `LogicalNet` records. Repeated layer geometry and ambiguous `~` pin names on J3/LED1 prevent a simple unique endpoint comparison. This audit parsed XML; it did not validate the full IPC schema, copper rules, or electrical correctness.
5. **No completed PCB routing or firmware archive was recovered.** The native file has schematic wire records, placements, and constraints, but no route-segment/via nodes. Project chat, knowledge documents, and firmware source are absent. Component rationale remains useful but can be stale.

## Recommended next work

Use this snapshot to reconstruct and verify a readable schematic and PCB starting point in KiCad. A direct `.flx`-to-KiCad conversion has not been demonstrated; the plan is controlled extraction with explicit connectivity and footprint checks. Retain useful placement/mechanical constraints, then reassess placement around power loops, BGA escape, and the camera/USB routes.

Keep firmware integration parallel using the [hardware/firmware interface baseline](../../../docs/hardware-firmware-interface.md). Hardware source reconciliation, pin/footprint review, rail and boot review, and placement preparation can proceed immediately. Reconcile firmware-owned pins, clocks, power sequencing, camera lane mode, and boot assumptions before freezing their routing.

Four layers and conventional drilled vias remain the working target, not a validated manufacturing solution. The recovered stackup is explicitly provisional, and its numeric layer sum differs from its 1.6 mm label. Choose actual fabrication rules and dielectric dimensions before finalizing BGA escape and CSI/USB width/gap. Nominal impedance annotations alone do not establish achieved impedance.

Reproduce native extraction with [inventory_native.py](inventory_native.py) and the cross-export catalog with [catalog_flux_snapshot.py](../../../tools/catalog_flux_snapshot.py). Scripts only produce derived inventories/manifests; they do not rewrite source exports.
