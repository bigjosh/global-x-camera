# Beta board hardware

KiCad files for the first custom board, the beta. The recovered September design is in [../kicad](../kicad) and is not the starting point.

So far this holds one footprint library, `GXB.pretty`.

## ALPS_RK10J11E0034_FaceDown

The exposure and ASA dials. Written by `tools/build_dial_footprint.py`; change the script, not the file.

The Alps RK10J11E0034 is a through-hole thumbwheel potentiometer. Here it is mounted on the parts side with its knob face against the board, so the label on the knob face shows through a hole from the user side. Its legs are re-formed by hand:

- The five terminals are folded back toward the board and soldered to pads `1`, `D1`, `2`, `D2`, `3`. `1` and `3` are the track ends, `2` is the wiper, and the two `D` terminals are Alps's dummies with no connection.
- The two mounting tabs are folded outward until they lie flat with the back of the pot. That leaves each tab 1.8 mm above the board and ending at the rim of the knob, so its `MP` pad sits just outside the rim and the tab needs a short wire or riser down to it.
- A 2.8 mm unplated hole, 5.2 mm from the knob centre on the terminal side, shows the selected label.

The footprint is drawn looking at the parts side, where the back of the pot faces the viewer. The board's top edge passes 5.0 mm from the knob centre, so the knob stands 2 mm above it; a line on `Dwgs.User` marks the edge.

**Status: draft.** Positions come from Alps's catalog drawing and 3D model in [datasheets/controls](../../datasheets/controls). Pad sizes are the reviewer's choice for hand soldering. Nothing has been checked against a part with re-formed legs. To check on the first part: whether the folded-back terminals reach the board (1.9 mm of free length against 1.9 mm to travel), and that no pad or solder touches the turning knob. Keep vias out from under the knob.
