# Open questions before the first camera PCB

**Compiled November 25, 2026**, in answer to "what open questions do we need to resolve before we can spin the first camera PCB?". It continues the [November 10 punch list](2026-11-10-pcb-readiness-punch-list.md); `PL-xx` refers to its items. The user and the reviewer are working through the items one at a time. Each resolution gets a status line here and a dated entry in the owning `NOTES.md`.

Four things gate schematic capture: the CAD-tool test (4), two owner decisions (5, 6), the power-and-latch proposal (11–19), and a pin table (21). The rest can close during capture or before layout. Nothing settled on November 11 is re-opened.

## How this list was made, and its limits

Six readers went through the repository by area (power; storage and boot; camera and latency; pins and controls; mechanical, fabrication and CAD; changes since November 11). A skeptic checked each reader's list against the repository, a completeness pass looked for gaps between areas, and three checkers compared the merged list with its sources, with the repository and pull request #1, and with the decisions already settled. Recommendations are the reviewer's unless marked otherwise.

Not checked: live stock, vendor documents that are not stored in the repository, DipTrace itself, and the owner's local working tree. Vendor and distributor sites cannot be reached from the review environment; web search can see distributor listings.

## Status

On November 25 the user redefined the first board as a beta: one small LiPo, an SD card, KiCad, ST-LINK only. That changes or closes many items below; the item text is kept as first written.

| Item | Status |
|---|---|
| 1 | **Resolved.** Pull request #1's firmware and installer are ignored for PCB planning. See [root notes](../../NOTES.md). |
| 2 | Open. The user asked what the local checkout and stash hold. The review environment cannot reach the user's PC; it needs `git status` and `git stash list` output, or the work pushed to a branch. |
| 3 | Open. The user has the RV-3032 documents in the PC's downloads folder, which the review environment cannot reach. They need uploading, or fetching from the maker's site. |
| 4 | **Resolved.** KiCad. |
| 5 | **Resolved.** The beta runs only from a small LiPo stuck to the parts side; no charger, two pads for an external one. The reviewer is picking the cell. See [power notes](../power/NOTES.md). |
| 6 | **Resolved.** Unordered power-down is accepted. |
| 7 | Delegated to the reviewer: pick an available NOR that will work. In progress. |
| 8 | **Resolved.** No FRAM in this version. |
| 9 | **Resolved.** An ST-LINK connector on the parts side is the only programming and debug path. |
| 10 | **Resolved.** Two potentiometers; the ASA steps are made in software. |
| 11–20 | Reframed. Storage is an SD card, so item 19 becomes the SD rail. The user proposes a 1.8 V buck plus an MCU-switched 3.3 V rail for the card; the reviewer's proposal for the whole tree is in progress. Item 14: the SPDT-and-capacitor start stays as built on the prototype. |
| 22 | Partly resolved. The control group's geometry is locked: [preview](../custom-pcb/control-cluster-preview.svg), [positions](../custom-pcb/control-cluster.json). Quantity, enclosure and the rest of the placement are open. |
| 24 | Partly resolved. One reverse-mount RGB LED, seen through a hole below the shutter button. Part and behaviour during exposure open. |
| 26, 28 | Not on this beta: no NAND and no cell holders. A card socket and a LiPo replace them. |
| 30 | **Resolved.** Alps RK10J11E0034 for both dials, mounted face-down; a small hole below each dial centre shows the selected label. See [prototype notes](../prototype/NOTES.md). The footprint waits on how the lugs are held. |
| 12, 13, 15–18, 21, 23, 25, 27, 29, 31–35 | Open, not yet discussed. Items 12 and 13 are much simpler on a LiPo. |

## 1. Housekeeping first (owner)

1. **Pull request #1.** A collaborator's open pull request against this branch (November 16–21) holds the only hardware results for the knob firmware. For the board, four of its bench findings matter, none with an established cause: the ASA knob only reads its end values on that unit; exposures above about 220 ms fail with two red flashes after the settings verify as applied; once the MCU appeared to stay powered on battery with the ST-LINK attached; daylight clipped at 1/1000 s. Question: which line is the PCB baseline, and do its firmware changes bear on the board?
2. **Uncommitted work on the owner's Windows checkout.** `AGENTS.md` and the [November 14 reconciliation](2026-11-14-knob-firmware-reconciliation.md) say power-design and PCB-readiness edits stayed in the working tree (stash `d0609865`). They are on no branch. If they hold a draft power proposal, it should be committed.
3. **Vendor access.** Either allow vendor and distributor hosts for the review environment or upload documents on request. Needed before the RTC sheet is drawn: the RV-3032 datasheet and application manual. Needed before layout: a STEP or drawing of the camera module, and the Micron and Kioxia NAND datasheets.
4. **CAD tool (PL-05).** Still untested. Needed: the DipTrace version and edition, the XML format specification, and an XML and ASCII export of a small project. If import fails: capture by hand in DipTrace from a generated netlist and pin table, or move to KiCad?

## 2. Owner decisions before the schematic

5. **LiPo fallback.** Must one fitted circuit run from both a LiPo (3.0–4.2 V) and the coin pack (up to 16.5 V with five cells), or is the LiPo a build variant? Options: one 3.0–16.5 V input stage; a coin-cell stage plus LiPo pads selected by links; no LiPo support. Recommended: the link-selected variant. It keeps the coin-cell converter optimal, and a 3.0 V input leaves only 0.2 V above the sensor's 2.8 V rail. The power reader preferred one input stage.
6. **Power-off order (PL-06).** Does the November 8 prototype waiver carry over, or does the board enforce ST's order (auxiliary rails down before the main rail)? Must that also hold on unplug or a collapsing pack? Options: accept unordered collapse, as the Nucleo does; an RC off-delay for controlled shutdown only; an input-fail detector that drops the auxiliary rails first. Recommended: the detector, which also gives the brown-out signal.
7. **Boot flash part (PL-13).** The ROM cannot boot from parallel NAND, so a serial NOR stays. PL-13 says a small low-current NOR; PL-22 says keep the Nucleo's part. Recommended: the small NOR, noting that ST's stock loader, the proven way onto a blank board, only works with the Nucleo's part.
8. **FRAM for the slot table: yes or no.** Kept open in October. Recommended: no.
9. **Programming and recovery (PL-13).** The board has no ST-LINK. Which probe will be used, and does it work at 1.8 V? Should BOOT0 be reachable on the closed camera so the ROM's USB loader works with only a cable? Recommended: both that and a debug footprint carrying SWD, reset, the UART recovery pins and both boot straps at 1.8 V.
10. **Controls.** Confirm two knobs and USB-C. The sweep suggested a four-position switch for ASA. Recommended: two potentiometers of one documented part, matching D-50 and the printed labels.

## 3. The power-and-latch proposal (PL-06, 07, 08, 15, 16)

The punch list's stated next step. The reviewer writes it; the owner approves. It must answer:

11. **Tree and partition.** Which converters, which loads sit in ST's main and auxiliary groups, and how the sensor's 2.8 V and 1.15 V are made. The agreed 1.8 V NAND already forces the main I/O bank to 1.8 V. The boot flash and its I/O bank belong in the main group so the ROM can read it. No pin may ever exceed 1.98 V.
12. **Core supply.** Internal SMPS or external buck; fixed in copper. The November 11 recommendation was an external buck, under the lowest-power rule. The model's difference is under 0.01 W on an assumed efficiency. Recommended now: the internal SMPS, for one converter fewer. That trades against the owner's rule, so it is the owner's call.
13. **Main 1.8 V buck.** Needs live stock. Rated 20 V or more; output inside 1.746–1.89 V if it feeds the internal SMPS and the USB analog supply; about 85% at 30–120 mA; able to carry the USB-mode load. The cell-count conclusion rests on that assumed 85%.
14. **Latch (PL-08).** Held by `PWR_ON` or a GPIO? `PWR_ON` alone conflicts with the rule that USB never leaves the camera on the battery: read from the documents, not measured, the board would stay on at unplug and on a blank flash. Recommended: `PWR_ON` gated by a hardware VBUS lockout and an on-time limit. The shutter switch form comes first: the prototype trigger needs SPDT, and the only stored switch is SPST rated 12 V. The hold transistor must turn on fully from 1.8 V. Every MCU pin touching pack voltage needs a series resistor and clamp, since PA2 failed on the prototype for a reason never found.
15. **Source selection and USB detect (PL-15).** The coin pack sits above VBUS and neither source may be charged, so a diode-OR fails. One hardware VBUS-present signal forces the battery path off and replaces the ADC sample.
16. **Off-current budget.** The 100 nA target, counted over every part left on the pack at 16.5 V.
17. **The 50 ms budget (PL-11).** The only measurement is about 25 ms on a stiff bench supply, never from the button. Converters and the reservoir are chosen against this table. At 50 °F, must it hold on half-used cells or only fresh ones? Recommended: half-used. The reviewer estimates the rail ramp alone can reach the four-cell burst ceiling, so cold start needs simulating.
18. **Sensor start-up (PL-09).** What replaces the adapter board: the clock source, the hardware reset release, and rails that rise without firmware. The adapter's oscillator may take 5 ms to start, so ST's bare pull-up breaks the datasheet's clock-first rule on paper; a release delay is needed.
19. **NAND supply.** The specification checks for a free slot before exposure, and the NAND needs up to 5 ms after power. Recommended: NAND on the main rail from power-up. May a "full" or "low battery" verdict arrive just after exposure begins?
20. **Before layout, from the same proposal:** the battery divider and undervoltage detector (PL-16); the reservoir capacitor; USB PHY supplies; RV-3032 supply and backup; an LED supply, since no LED lights from 1.8 V.

## 4. Pin table (PL-10)

21. None exists for the new board. It needs each signal's ball, function, voltage bank and state during reset and ROM boot. Keeping clear of the ROM's UART pins and boot straps in effect selects the PB/PD pin set for the NAND.

## 5. From the owner before layout

22. **Build inputs and enclosure (PL-02, PL-12).** How many boards? Does the October rule (a prototype may exceed 5 mm) apply to this spin? Is the board still the case's rear face, or may parts sit on both faces? Mounting holes, cell access, and a placement sketch.
23. **Fabricator, assembler and stackup (PL-20).** Deferred since October. Recommended: six layers on a standard impedance stackup. A DipTrace edition may cap signal layers.
24. **Indicators (PL-18).** How many, which colours, and is one lit during exposure?
25. **Camera module.** Photos of a module mated to the adapter, both faces with a scale, plus head height, flex length and pin 1 relative to the lens. Which way round does the frame sit on the card? The sensor can flip but not rotate 90°.

## 6. Sourcing and design before layout

26. **NAND part (PL-03).** A live stock check, then one part and one alternate. Page size comes ahead of capacity: 2 KiB-page parts, including the only 8 Gbit candidate, take about 0.28 s per save against 0.15 s.
27. **Other critical parts.** MCU, RV-3032 and camera connector available in the build quantity, and whether the assembler takes them consigned.
28. **Cell holder.** A stocked holder that physically refuses a reversed cell, with a bypass link at the fifth position.
29. **Placement study.** Whether four or five cells fit beside the module, two BGAs, knobs and USB-C.
30. **Control parts (PL-17).** A documented thumbwheel potentiometer to replace the hobby wheels.
31. **Footprints.** The camera connector redrawn from the Hirose drawing (the recovered one is wrong). Each new footprint checked against its maker's drawing by a second person.
32. **Test access (PL-21).** Now a requirement, since this board is the only power experiment: a link in every rail, a pack-emulation input, a force-on link, and pads on the latch, NAND control lines and sensor start-up nodes.
33. **Old findings.** Each schematic-level finding of the 47 marked fixed, carried over or superseded.

## 7. Before the order

34. Layout-level findings closed, and netlist, PDF, ERC and DRC exports committed so a second reader can check them.
35. The stock check repeated.

## Set aside as not PCB blockers

- NAND slot layout: a 4 Gbit part guarantees about 250 photos if slots are built from good blocks.
- OTP fuses: program none on first boards.
- The 220 ms exposure failure: firmware fault-finding; the board is designed to 0.5 s either way.
- A torn erase at unplug: a storage-format matter.
- Daylight clipping: a filter, if needed, sits in the case.
- Defaults adopted unless the owner objects: the 48 MHz crystal, CSI routed without the Nucleo's filter parts, and LIS2DW12 for orientation.

## Corrections to the November 10 punch list

- PL-20: filled via-in-pad is not needed. ST's Nucleo routes the same BGA on four layers with through vias.
- PL-01 and PL-12: five cells take 52% of the card, not 59%.
- PL-13 and PL-22 item 4 contradict each other on the boot flash part (item 7).
