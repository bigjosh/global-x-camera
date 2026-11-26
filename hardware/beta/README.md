# Beta board hardware

KiCad files for the first custom board, the beta. The recovered September design is in [../kicad](../kicad) and is not the starting point.

So far this holds one footprint library, `GXB.pretty`.

## ALPS_RK10J11E0034_FaceDown

The exposure and ASA dials. Written by `tools/build_dial_footprint.py`; change the script, not the file.

The Alps RK10J11E0034 is a through-hole thumbwheel potentiometer. Here it is mounted on the parts side with its knob face against the board, so the label on the knob face shows through a hole from the user side. Its legs are re-formed by hand:

- The five terminals are folded back toward the board and soldered to pads `1`, `D1`, `2`, `D2`, `3`. The schematic uses the two outside pads, `1` and `3`, as the top and bottom of the track and the middle pad, `2`, as the wiper; `D1` and `D2` are soldered to their own pads and connected to nothing (user's decision, November 26). The wiring is symmetric, so it does not matter which way round the part's terminal numbering runs in the mirrored footprint; a reversed part only reverses the direction of rotation, which firmware sets. This follows Alps's terminal figure for the part, which reads 1, dummy, 2, dummy, 3. The leaders on Alps's hole drawing and the reflow twin's land drawing point instead to 1, 2, dummy, dummy, 3, so meter a part before the board is ordered: if the wiper is on a dummy position, that pad is beside the middle pad and a solder bridge joins them.
- The two mounting tabs are folded outward until they lie flat with the back of the pot. A folded tab ends about 6.97 mm from the knob centre, over the knob's rim, with its underside 1.5 mm above the board. It cannot touch the board. Its `MP` pad sits just outside the rim, 7.4 to 8.6 mm from the centre, and a formed wire or strip joins the pad to the back of the tab.
- A 2.8 mm unplated hole, 5.2 mm from the knob centre on the terminal side, shows the selected label.

The footprint is drawn looking at the parts side, where the back of the pot faces the viewer. The board's top edge passes 5.0 mm from the knob centre, so the knob stands 2 mm above it; a line on `Dwgs.User` marks the edge.

**Status: draft, checked once on paper.** Positions come from Alps's catalog drawing and 3D model in [datasheets/controls](../../datasheets/controls); a second reader re-measured the model and confirmed the pad positions, the mirroring and the clearances. Pad sizes are the reviewer's choice for hand soldering. Nothing has been checked against a part.

Before boards are ordered, re-form one sacrificial part and check:

- which terminal is the wiper, with a meter;
- that the terminals survive the fold. It reverses the factory bend 1 mm from the eyelet, and Alps allows one 3 s solder joint, so a poor joint cannot be reworked. Measure end-to-end and wiper resistance before and after;
- that the folded terminals reach their pads. About 2.2 to 2.3 mm of metal has about 2.15 mm to travel, and a label under the knob lifts the part by its own thickness, so use a thin label and tin the pads first.

Layout rules that the footprint does not enforce: no vias, pads or silk within 7.3 mm of the knob centre, where the knob or its label slides on the board; no panel tabs on the top edge within 5 mm of a dial centre. Take the wiper straight to the ADC with only a capacitor to ground: Alps asks for a load above 1 megohm. Alps rates the part for -10 to +60 C.
