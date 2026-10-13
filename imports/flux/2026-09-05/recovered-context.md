# Recovered Flux project context

Source: `bigjosh-global-x-camera.flx`, downloaded 2026-09-05, 11,610,536 bytes. SHA-256: `6da7be0451f25cee64d67e8072e4fb0b201687bf9c56cfb6292dd439a3d16aac`. This review inspected only the saved project JSON; it did not retrieve referenced assets or modify the source.

The native export preserves substantial design context beyond EDIF, including component rationale, schematic positions, PCB placement, mechanical keepouts, and provisional routing rules. It does **not** contain the project's chat history or a firmware-document archive.

## What is present

| Area | Evidence in the export |
| --- | --- |
| Project overview | Name and a short description identifying the STM32N6, CAM-5G0-079CLR, raw NAND, four series CR2032 cells, and USB-C download architecture. |
| Component intent | All **148** top-level elements have nonempty `Role`, `Role Details`, and `Functional Group` properties. There are **12** distinct group names, with some parts assigned to multiple groups. |
| Schematic arrangement | All **148** elements have `symbol_placements.MAIN`; **1,131** `routeVertices` preserve positions and horizontal/vertical connection relationships. These are schematic-style wire records, not evidence of routed PCB copper. |
| PCB placement | **1,889** PCB nodes include **147** element nodes with positions, **147** footprint nodes, **699** pad nodes, **133** model nodes, **15** text nodes, and **2** camera keepout zones. Another recovery report covers detailed pin/footprint inventory. |
| Board rules | **10** top-level rule sets, of which **9** carry `ruleSetOrigin: agent`; embedded custom stackup data is available by decoding the layout node's `stackup.payloadAsBase64`. |
| Pair annotations | **22** raw net records carry impedance/pair annotations, including repeated schematic segments. They refer to **3** pair groups: CSI2_CLK, CSI2_D0, and USB2_HS; this is not 22 separate differential pairs. |
| Asset metadata | **310** unique storage-name records across project assets and repeated part-library caches: 133 KiCad footprints, 127 STEP files, 6 STP files, 24 SVGs, and 20 PNGs. These are mostly ECAD/model/symbol/thumbnail metadata, not attachments containing design reports. **26** distinct named `.kicad_mod` payloads are embedded as base64; many other referenced files are not embedded. |

Examples of recoverable rationale in `elements/<id>/properties` include U12's load-switch choice to meet LIS2DW12 supply limits, C8's startup/inrush tradeoff, and the external camera's deliberate separation from the host J3 footprint. Limited firmware-interface assumptions also survive there: U8's intended RTC BSM setting, R16's NAND write-protect sequencing, and U5's primary/redundant FSBL addresses. These are useful hardware-review inputs, not firmware implementation evidence.

## Physical and routing context to preserve

- The layout stores an **85.6 x 53.98 mm** rectangular board, **3.18 mm** corner radius, and **0.25 mm** board inset/keepout.
- Its explicitly provisional stack label says four layers / 1.6 mm. Stored layers are L1 signal/components, L2 ground reference, L3 power/slow signals, and L4 ground; each copper layer is 35 micrometers. Stored dielectric thicknesses are 0.18 / 1.17 / 0.18 mm with dielectric constant 4.2. The numeric copper-plus-dielectric sum is 1.67 mm, so the label is not a fabricator-confirmed thickness.
- Rule descriptions set nominal **100-ohm CSI-2** and **90-ohm USB** differential targets on L1 over L2, while explicitly requiring width/gap recalculation for the eventual fabricator. Stored width choices include 0.10 mm neckdown and 0.15 mm main geometry; they do not establish achieved impedance or length matching.
- Provisional minimum copper/clearance is 0.10 mm. One enabled through-via definition uses a 0.20 mm drill and 0.50 mm pad. A separate generic laser-hole minimum is present; it does not demonstrate a selected HDI process.
- Two 10 x 15 mm top-side camera component keepouts remain at (-16, +6.5) and (-16, -6.5) mm, with matching visible outlines/labels. Preserve both as stored; their presence does not settle final camera orientation.
- Three rules preserve prior footprint corrections: U7's nine duplicate pads disabled, and U10's two mirrored custom copper shapes restored. The overrides are saved design state; their explanatory claims still need checking against manufacturer drawings.

## What is absent or only referenced

`comment_count` is zero and `comment_threads` is empty. There are no chat/message/conversation collections, standalone project-knowledge documents, firmware source files, or PDF/text-document asset records in this export. Root `properties` is empty. Root `behaviour` contains only Flux's introductory automation template; it is not project firmware. `routes` is empty, and the PCB node inventory has no route-segment or via nodes, so no completed copper routing was recovered here.

The single project-level asset is metadata for `cam-6g3-073clr-reference.stp`, explicitly labeled a supplied reference model. The selected camera element says **CAM-5G0-079CLR**. Do not treat the different module's reference model as validated production geometry. No associated STP file bytes are embedded in that root asset record.

## Source hierarchy

Treat stored nets, placements, and enabled rule values as evidence of the exported state. Treat `Role Details`, cached part descriptions, and rule descriptions as rationale or assertions to verify. For example, C41's note still names an MT29F2G NAND family, illustrating that prose can lag part selection. Cached library assets may include unused package alternatives. No chat assertions were recovered, and no missing firmware documents should block reconstruction or hardware review using the saved hardware state.
