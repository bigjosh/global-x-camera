# Beta board hardware

KiCad files for the first custom board, the beta. The recovered September design is in [../kicad](../kicad) and is not the starting point.

So far this holds one footprint library, `GXB.pretty`.

## ALPS_RK10J11E0034_FaceDown

The exposure and ASA dials. Written by `tools/build_dial_footprint.py`; change the script, not the file.

The Alps RK10J11E0034 is a through-hole thumbwheel potentiometer. Here it is mounted on the parts side with its knob face against the board, so the label on the knob face shows through a hole from the user side. Its legs are re-formed by hand:

- The five terminals are folded back toward the board and soldered to pads `1`, `D1`, `2`, `D2`, `3`. `1` and `3` are the track ends and `2` is the wiper. **Which terminal is the wiper is not certain.** Alps's terminal figure for this part reads 1, dummy, 2, dummy, 3, but the leaders on its hole drawing and the reflow twin's land drawing point to 1, 2, dummy, dummy, 3. Meter a part before the board is ordered; until then the schematic should tie `D1`, `2` and `D2` together as the wiper, which is right either way if the dummies are unconnected.
- The two mounting tabs are folded outward until they lie flat with the back of the pot. A folded tab ends about 6.97 mm from the knob centre, over the knob's rim, with its underside 1.5 mm above the board. It cannot touch the board. Its `MP` pad sits just outside the rim, 7.4 to 8.6 mm from the centre, and a formed wire or strip joins the pad to the back of the tab.
- A 2.8 mm unplated hole, 5.2 mm from the knob centre on the terminal side, shows the selected label.

The footprint is drawn looking at the parts side, where the back of the pot faces the viewer. The board's top edge passes 5.0 mm from the knob centre, so the knob stands 2 mm above it; a line on `Dwgs.User` marks the edge.

**Status: draft, checked once on paper.** Positions come from Alps's catalog drawing and 3D model in [datasheets/controls](../../datasheets/controls); a second reader re-measured the model and confirmed the pad positions, the mirroring and the clearances. Pad sizes are the reviewer's choice for hand soldering. Nothing has been checked against a part.

Before boards are ordered, re-form one sacrificial part and check:

- which terminal is the wiper, with a meter;
- that the terminals survive the fold. It reverses the factory bend 1 mm from the eyelet, and Alps allows one 3 s solder joint, so a poor joint cannot be reworked. Measure end-to-end and wiper resistance before and after;
- that the folded terminals reach their pads. About 2.2 to 2.3 mm of metal has about 2.15 mm to travel, and a label under the knob lifts the part by its own thickness, so use a thin label and tin the pads first.

Layout rules that the footprint does not enforce: no vias, pads or silk within 7.3 mm of the knob centre, where the knob or its label slides on the board; no panel tabs on the top edge within 5 mm of a dial centre. Take the wiper straight to the ADC with only a capacitor to ground: Alps asks for a load above 1 megohm. Alps rates the part for -10 to +60 C.
