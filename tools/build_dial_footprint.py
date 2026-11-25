"""KiCad footprint for the Alps RK10J11E0034 dial, mounted face-down.

On the beta board each dial sits on the parts side with its knob face against
the board, so the label on the knob face shows through a hole from the user
side. The part is a through-hole potentiometer, so its legs are re-formed by
hand: the five terminals are folded back toward the board, and the two
mounting tabs are folded outward until they lie flat with the back of the pot.

Part geometry is Alps's own (datasheets/controls: Drawing No. 1 of the RK10J
catalog and the RK10J1_E.STEP model), given below in Alps's knob-side view:
origin at the knob centre, +y away from the terminals. The footprint is drawn
as KiCad wants it, looking at the parts side of the board, where the back of
the pot faces the viewer: x is mirrored and y points down.

Run:  python tools/build_dial_footprint.py
"""
import math
from pathlib import Path

LIBRARY = Path(__file__).resolve().parents[1] / 'hardware/beta/GXB.pretty'
NAME = 'ALPS_RK10J11E0034_FaceDown'

# Alps geometry, knob-side view, millimetres.
KNOB_R, KNOB_R_MAX = 7.0, 7.1                 # diameter 14 +/-0.2
KNOB_THICKNESS, PART_HEIGHT = 0.9, 1.8        # knob face to back of pot is 1.8
BODY_HALF_W, BODY_TOP, BODY_BOTTOM = 5.15, 5.0, -7.6
TERMINALS = (('1', -4.0), ('D1', -2.0), ('2', 0.0), ('D2', 2.0), ('3', 4.0))   # D = dummy, no connection
TERMINAL_Y, TERMINAL_OUTER_FACE_Y, TERMINAL_FREE = -7.5, -7.65, 1.9
TAB_FACE_X, TAB_Y, TAB_W, TAB_FREE = 5.15, 2.5, 1.0, 1.8

# Land pattern, chosen here.
RIM_CLEARANCE = 0.3                           # copper stays this far outside the turning knob
PIN_PAD_W = 1.2
PIN_PAD_Y = (-(KNOB_R_MAX + RIM_CLEARANCE), -9.6)        # inner edge clears the rim at the centre terminal
TAB_PAD_H = 1.6
TAB_PAD_X = (7.4, 8.9)                        # just outside the rim at the tab; ends short of the board edge
LABEL_HOLE_D, LABEL_HOLE_R = 2.8, 5.2         # shows the selected label; confirmed with the control layout
BOARD_EDGE_Y = 5.0                            # the top board edge; the knob stands 2 mm beyond it

# Where the re-formed legs end up, for drawing and for the README.
BEND_ALLOWANCE = 0.25
TAB_TIP_X = TAB_FACE_X + TAB_FREE - BEND_ALLOWANCE       # folded outward, lying on the back of the pot
TAB_HEIGHT_ABOVE_BOARD = PART_HEIGHT                     # so the tab is this far above its pad
PIN_FOLD_Y = TERMINAL_OUTER_FACE_Y - 0.45                # centre of a terminal folded back over the strip edge


def pads():
    """(name, x, y, width, height) in the knob-side view."""
    out = []
    y0, y1 = PIN_PAD_Y
    for name, x in TERMINALS:
        out.append((name, x, (y0 + y1) / 2, PIN_PAD_W, y0 - y1))
    x0, x1 = TAB_PAD_X
    for sign in (-1, 1):
        out.append(('MP', sign * (x0 + x1) / 2, TAB_Y, x1 - x0, TAB_PAD_H))
    return out


def kx(x): return round(-x + 0.0, 4)          # mirror: the viewer is behind the pot
def ky(y): return round(-y + 0.0, 4)          # KiCad y points down


def footprint():
    stroke = '(stroke (width {w}) (type solid))'
    font = '(effects (font (size {s} {s}) (thickness {t})))'
    o = [f'(footprint "{NAME}"',
         '\t(version 20260206)',
         '\t(generator "global-x-camera-tools")',
         '\t(layer "F.Cu")',
         '\t(descr "Alps Alpine RK10J11E0034 thumbwheel potentiometer, mounted face-down with the knob face on the board. '
         'Terminals folded back to the board; mounting tabs folded outward flat with the back of the pot and linked down to the MP pads. '
         'Draft: not yet checked against a part with re-formed legs.")',
         '\t(tags "potentiometer thumbwheel Alps RK10J")',
         f'\t(property "Reference" "REF**" (at 0 {ky(BODY_BOTTOM) + 3.4} 0) (layer "F.SilkS") {font.format(s=1, t=0.15)})',
         f'\t(property "Value" "{NAME}" (at 0 {ky(BODY_BOTTOM) + 4.9} 0) (layer "F.Fab") {font.format(s=1, t=0.15)})',
         '\t(attr smd)']
    # Fabrication layer: the knob, the body, the folded legs.
    o.append(f'\t(fp_circle (center 0 0) (end {KNOB_R} 0) {stroke.format(w=0.1)} (fill no) (layer "F.Fab"))')
    o.append(f'\t(fp_rect (start {-BODY_HALF_W} {ky(BODY_TOP)}) (end {BODY_HALF_W} {ky(BODY_BOTTOM)}) {stroke.format(w=0.1)} (fill no) (layer "F.Fab"))')
    for sign in (-1, 1):
        o.append(f'\t(fp_rect (start {sign * TAB_FACE_X} {ky(TAB_Y + TAB_W / 2)}) (end {round(sign * TAB_TIP_X, 3)} {ky(TAB_Y - TAB_W / 2)}) '
                 f'{stroke.format(w=0.1)} (fill no) (layer "F.Fab"))')
    for _, x in TERMINALS:
        o.append(f'\t(fp_rect (start {kx(x) - 0.4} {ky(TERMINAL_OUTER_FACE_Y)}) (end {kx(x) + 0.4} {ky(PIN_FOLD_Y - 0.15)}) '
                 f'{stroke.format(w=0.1)} (fill no) (layer "F.Fab"))')
    o.append(f'\t(fp_text user "${{REFERENCE}}" (at 0 {ky(1.5)} 0) (layer "F.Fab") {font.format(s=1, t=0.15)})')
    # Board edge and notes.
    o.append(f'\t(fp_line (start -9.5 {ky(BOARD_EDGE_Y)}) (end 9.5 {ky(BOARD_EDGE_Y)}) {stroke.format(w=0.1)} (layer "Dwgs.User"))')
    o.append(f'\t(fp_text user "board edge; knob stands 2 mm beyond" (at 0 {ky(BOARD_EDGE_Y) - 2.9} 0) (layer "Dwgs.User") {font.format(s=0.6, t=0.09)})')
    o.append(f'\t(fp_text user "knob face on the board; tabs sit {TAB_HEIGHT_ABOVE_BOARD} mm above the MP pads" (at 0 {round(ky(BODY_BOTTOM) + 6.3, 3)} 0) '
             f'(layer "Cmts.User") {font.format(s=0.6, t=0.09)})')
    # Silk: terminal 1 marker, outside everything that moves or solders.
    one = kx(TERMINALS[0][1])
    o.append(f'\t(fp_text user "1" (at {one + 1.5} {ky(PIN_PAD_Y[1]) - 0.5} 0) (layer "F.SilkS") {font.format(s=0.8, t=0.12)})')
    # Courtyard.
    cx = TAB_PAD_X[1] + 0.25
    o.append(f'\t(fp_rect (start {-cx} {-(KNOB_R_MAX + 0.25)}) (end {cx} {ky(PIN_PAD_Y[1]) + 0.25}) {stroke.format(w=0.05)} (fill no) (layer "F.CrtYd"))')
    # Pads.
    for name, x, y, w, h in pads():
        o.append(f'\t(pad "{name}" smd rect (at {kx(x)} {ky(y)}) (size {round(w, 3)} {round(h, 3)}) (layers "F.Cu" "F.Mask"))')
    o.append(f'\t(pad "" np_thru_hole circle (at 0 {ky(-LABEL_HOLE_R)}) (size {LABEL_HOLE_D} {LABEL_HOLE_D}) (drill {LABEL_HOLE_D}) (layers "*.Cu" "*.Mask"))')
    o.append('\t(embedded_fonts no)')
    o.append(')')
    return '\n'.join(o) + '\n'


def checks():
    """Clearances the land pattern has to keep; raises if a constant is changed carelessly."""
    for name, x, y, w, h in pads():
        nearest = math.hypot(max(abs(x) - w / 2, 0), max(abs(y) - h / 2, 0))      # pad to knob centre
        assert nearest >= KNOB_R_MAX + RIM_CLEARANCE - 1e-6, (name, round(nearest, 3))
    hole_outer = LABEL_HOLE_R + LABEL_HOLE_D / 2
    assert hole_outer <= 6.7, 'label hole runs past the flat knob face'
    assert -PIN_PAD_Y[0] - hole_outer >= 0.5, 'label hole too close to the centre terminal pad'


def main():
    checks()
    LIBRARY.mkdir(parents=True, exist_ok=True)
    (LIBRARY / f'{NAME}.kicad_mod').write_text(footprint())
    for name, x, y, w, h in pads():
        print(f'{name:3} knob-side ({x:6.2f}, {y:6.2f})  KiCad ({kx(x):6.2f}, {ky(y):6.2f})  {w:.1f} x {h:.1f}')
    print(f'label hole {LABEL_HOLE_D} mm at KiCad (0, {ky(-LABEL_HOLE_R)}); folded tab tip at x = {TAB_TIP_X:.2f}, '
          f'{TAB_HEIGHT_ABOVE_BOARD} mm above the board')


if __name__ == '__main__':
    main()
