# Beta board hardware

KiCad files for the first custom board, the beta. The recovered September design is in [../kicad](../kicad) and is not the starting point.

So far this holds one footprint library, `GXB.pretty`, with the dial and the shutter switch.

## ALPS_RK10J11E0034_FaceDown

The exposure and ASA dials. Written by `tools/build_dial_footprint.py`; change the script, not the file.

The Alps RK10J11E0034 is a through-hole thumbwheel potentiometer. Here it is mounted on the parts side with its knob face against the board, so the label on the knob face shows through a hole from the user side. Its legs are re-formed by hand:

- The five terminals are folded back toward the board and soldered to pads `1`, `D1`, `2`, `D2`, `3`. The schematic uses the two outside pads, `1` and `3`, as the top and bottom of the track and the middle pad, `2`, as the wiper; `D1` and `D2` are soldered to their own pads and connected to nothing (user's decision, November 26). The wiring is symmetric, so it does not matter which way round the part's terminal numbering runs in the mirrored footprint; a reversed part only reverses the direction of rotation, which firmware sets. This follows Alps's terminal figure for the part, which reads 1, dummy, 2, dummy, 3. The leaders on Alps's hole drawing and the reflow twin's land drawing point instead to 1, 2, dummy, dummy, 3, so meter a part before the board is ordered: if the wiper is on a dummy position, that pad is beside the middle pad and a solder bridge joins them.
  The second-terminal reading has real support. Alps's dual-unit RK10J12 parts share this outline and 3D model and read, from the same end: shared track end, first wiper, second wiper, second track's far end, first track's far end. Alps's reflow single-unit twin, RK10J11R0A0L, is labelled 1, 2, dummy, dummy, 3. If the RK10J11E0034 is built on the dual-unit element, its wiper is on the second terminal, the middle terminal is an unused collector and the fourth is the far end of an unused 10 kilohm track. In every Alps figure the two outside terminals are the track ends, so that part of the wiring is safe either way.
  Meter check, unpowered: the outside pair should read about 10 kilohm and stay constant; the wiper is whichever of the second or middle terminal sweeps against both ends as the wheel turns; then measure the remaining terminals against all others to see whether they are true dummies.
- The two mounting tabs are folded outward until they lie flat with the back of the pot. A folded tab ends about 6.97 mm from the knob centre, over the knob's rim, with its underside 1.5 mm above the board. It cannot touch the board. Its `MP` pad sits just outside the rim, 7.4 to 8.6 mm from the centre, and a formed wire or strip joins the pad to the back of the tab.
- A 2.8 mm unplated hole, 5.2 mm from the knob centre on the terminal side, shows the selected label.

The footprint is drawn looking at the parts side, where the back of the pot faces the viewer. The board's top edge passes 5.0 mm from the knob centre, so the knob stands 2 mm above it; a line on `Dwgs.User` marks the edge.

**Status: draft, checked once on paper.** Positions come from Alps's catalog drawing and 3D model in [datasheets/controls](../../datasheets/controls); a second reader re-measured the model and confirmed the pad positions, the mirroring and the clearances. Pad sizes are the reviewer's choice for hand soldering. Nothing has been checked against a part.

Before boards are ordered, re-form one sacrificial part and check:

- which terminal is the wiper, with a meter;
- that the terminals survive the fold. It reverses the factory bend 1 mm from the eyelet, and Alps allows one 3 s solder joint, so a poor joint cannot be reworked. Measure end-to-end and wiper resistance before and after;
- that the folded terminals reach their pads. About 2.2 to 2.3 mm of metal has about 2.15 mm to travel, and a label under the knob lifts the part by its own thickness, so use a thin label and tin the pads first.

Layout rules that the footprint does not enforce: no vias, pads or silk within 7.3 mm of the knob centre, where the knob or its label slides on the board; no panel tabs on the top edge within 5 mm of a dial centre. Take the wiper straight to the ADC with only a capacitor to ground: Alps asks for a load above 1 megohm. Alps rates the part for -10 to +60 C.

## OMRON_D2MQ-4L-105-1_Flat

The shutter switch. Written by `tools/build_shutter_footprint.py`; change the script, not the file.

The Omron D2MQ-4L-105-1 is a subminiature snap-action switch with a hinge lever, straight terminals and gold contacts. Here it lies flat on the parts side, lever toward the top board edge, between the two dials. Nothing passes through the board:

- The footprint's origin goes on the board edge. The case bottom is 8.3 mm below the edge, so the lever at rest stands at most 2.0 mm beyond it, level with the dial rims.
- The three terminals are trimmed from 3.4 to 2.2 mm, joggled down and soldered to pads `1`, `2`, `3`, each 1.6 x 2.6 mm at 2.5 mm pitch, 8.4 to 11.0 mm below the edge. A terminal leaves the case on the centre plane of its thickness: centre 1.35 mm and underside 1.05 mm above the board, so the joggle is about 1 mm.
- Pad `1` is at the lever-pivot end. From Omron's contact-form figure the order is `1` COM, `2` NO, `3` NC. **This is read from drawings only; confirm it with a meter before the board is ordered.**
- The case's two 1.6 mm mounting holes are not used and the board has no holes for them. The three joints alone hold the switch against finger force unless adhesive or a housing rib is added.

**Status: draft, checked once on paper.** A second reader re-measured Omron's drawings, re-derived the contact order and checked the mirroring; all agreed with the footprint. The file has been parsed but not loaded in KiCad, and nothing has been checked against a part.

Points the check raised, none of them errors in the footprint:

- Omron gives the free position as a maximum, so a lever may rest lower than 2.0 mm above the edge.
- With the case 8.3 mm below the edge the switch snaps 0.4 ±0.5 mm above the edge, and Omron asks for at least 0.3 mm of travel past that. A worst-case part must be pressed 0.4 mm below the board edge. Placing the switch 0.5 mm nearer the edge would keep the whole stroke above it; that changes the confirmed position, so it is the user's decision.
- Whether a 1 mm joggle can be formed in a 2.2 mm stub that carries a 1.3 mm barb has to be tried on a part.
- Omron cautions against solder and flux reaching the case; the pads start 0.1 mm from it.

