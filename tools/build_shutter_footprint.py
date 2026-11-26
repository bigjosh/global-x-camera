"""KiCad footprint for the Omron D2MQ-4L-105-1 shutter switch, lying flat.

On the beta board the switch (hinge lever, straight terminals, gold contacts)
lies on the parts side with a large face on the board, its lever toward the
top board edge and its three terminals pointing away from the edge. Nothing
passes through the board: the terminals are trimmed, joggled down by hand and
soldered to rectangular pads, and the case's two mounting holes are not used.

Part geometry is Omron's own (datasheets/controls/Omron_D2MQ_datasheet.pdf:
"PCB terminals (Straight)" on page 2, "Hinge lever Models" on page 3, "Contact
Form" on page 1). Omron draws the switch with the lever pivot on the left and
the terminals down, and measures lever positions from the mounting-hole centre
line. That is also how the switch appears in the board's back (user-side)
view, seen through the board, so the geometry below is given in that view:
origin on the board edge at the centre of the body's width, +x to the right,
+y beyond the edge. The footprint is drawn as KiCad wants it, looking at the
parts side: x is mirrored and y points down.

Contact order. Omron's contact-form figure shows the case in the same view as
its dimension drawings, plunger left of centre, with the terminals reading
COM, NO, NC from the plunger end. On the hinge-lever model the pivot is at the
plunger end, so COM is the terminal nearest the lever pivot, NO the centre one
and NC the one under the lever's free end: pads 1, 2, 3. This is read from the
drawings only and is to be confirmed with a meter before the board is ordered.

Run:  python tools/build_shutter_footprint.py
"""
import math
from pathlib import Path

LIBRARY = Path(__file__).resolve().parents[1] / 'hardware/beta/GXB.pretty'
NAME = 'OMRON_D2MQ-4L-105-1_Flat'

# Omron geometry, millimetres. Widths are measured from the case's pivot-end side, heights from the hole line.
BODY_W, BODY_THICKNESS = 8.2, 2.7             # the base of the case; above the base it is 8.1 wide and 2.6 thick
HOLE_LINE = 1.6                               # mounting-hole centre line above the case bottom
HOLE_D, HOLE_FIRST, HOLE_PITCH = 1.6, 2.1, 4.0
CASE_TOP = 4.45                               # top face under the lever
SHOULDER_TOP, SHOULDER_W = 6.5 - HOLE_LINE, 3.1   # raised pivot end: 6.5 above the bottom; width scaled from the drawing
PIVOT, PIVOT_R = 5.9, 0.7                     # lever pivot; the lever's hub tops out at 6.6
PIVOT_FROM_SIDE = 0.75                        # scaled from the drawing: the R0.7 hub is flush with the 8.1 mm upper case
LEVER_SWING_R, LEVER_TIP_R = 6.3, 0.5         # centre of the lever's rounded plastic end; its radius
FREE, OPERATE, OPERATE_TOL = 8.7, 7.1, 0.5    # free position (maximum) and operating position, top of the lever end
TERMINAL_FIRST, TERMINAL_PITCH = 1.6, 2.5
TERMINAL_W, TERMINAL_BARB_W, TERMINAL_T, TERMINAL_L = 0.8, 1.3, 0.6, 3.4   # two 1.3 mm barbs along each terminal
CONTACTS = ('COM', 'NO', 'NC')                # from the pivot end; to be confirmed with a meter

# Placement and land pattern, chosen here (the same figures as tools/build_shutter_fit_preview.py).
LEVER_PROUD = 2.5                             # the lever at its free position stands at most this far beyond the board edge;
                                              # 2.0 until November 26, when the user moved the switch 0.5 mm toward the edge
                                              # so that a worst-case part still snaps, with its overtravel, above the edge
CASE_BOTTOM_Y = LEVER_PROUD - FREE - HOLE_LINE    # so the case bottom is 7.8 mm below the edge
HOLE_Y = CASE_BOTTOM_Y + HOLE_LINE
TRIM = 2.2                                    # terminals are cut to this length when they are re-formed
PAD_W = 1.6                                   # 0.15 mm a side over the 1.3 mm barbs, Omron's general tolerance; leaves 0.9 mm between pads
PAD_Y = (-7.9, -10.5)                         # starts 0.1 mm outside the case; ends 0.5 mm past a trimmed terminal

# Where the terminals leave the case, for the note and the README. They are on the centre plane of the thickness.
TERMINAL_CENTRE_ABOVE_BOARD = BODY_THICKNESS / 2                             # 1.35 mm
TERMINAL_UNDERSIDE_ABOVE_BOARD = TERMINAL_CENTRE_ABOVE_BOARD - TERMINAL_T / 2     # 1.05 mm: the joggle


def from_side(d):
    """Back-view x of a point this far from the case's pivot-end side."""
    return round(d - BODY_W / 2, 4)


def above_holes(h):
    """Back-view y of a point this far above the mounting-hole line."""
    return round(HOLE_Y + h, 4)


def terminals():
    """(pad name, contact, x) in the back view, from the pivot end."""
    return [(str(i + 1), CONTACTS[i], from_side(TERMINAL_FIRST + i * TERMINAL_PITCH)) for i in range(3)]


def pads():
    """(name, x, y, width, height) in the back view."""
    y0, y1 = PAD_Y
    return [(name, x, (y0 + y1) / 2, PAD_W, y0 - y1) for name, _, x in terminals()]


def lever():
    """Pivot and the centre of the lever's rounded end at the free position, back view."""
    px, py = from_side(PIVOT_FROM_SIDE), above_holes(PIVOT)
    rise = FREE - LEVER_TIP_R - PIVOT
    return (px, py), (round(px + math.sqrt(LEVER_SWING_R ** 2 - rise ** 2), 4), round(py + rise, 4))


def kx(x): return round(-x + 0.0, 4)          # mirror: the back view looks through the board
def ky(y): return round(-y + 0.0, 4)          # KiCad y points down


def footprint():
    stroke = '(stroke (width {w}) (type solid))'
    font = '(effects (font (size {s} {s}) (thickness {t})))'
    order = ', '.join(f'{name} {contact}' for name, contact, _ in terminals())
    o = [f'(footprint "{NAME}"',
         '\t(version 20260206)',
         '\t(generator "global-x-camera-tools")',
         '\t(layer "F.Cu")',
         '\t(descr "Omron D2MQ-4L-105-1 subminiature basic switch (hinge lever, straight terminals, gold contacts), lying flat '
         'on the parts side with the lever toward the board edge; the origin goes on the board edge. '
         f'Terminals trimmed to {TRIM} mm, joggled down {TERMINAL_UNDERSIDE_ABOVE_BOARD:.2f} mm and soldered to the pads; no holes in the board. '
         f'Pads {order}, with pad 1 at the lever pivot end: read from the datasheet drawings, to be confirmed with a meter. '
         'Draft: not yet checked against a part.")',
         '\t(tags "switch microswitch snap-action lever Omron D2MQ")',
         f'\t(property "Reference" "REF**" (at 0 {ky(PAD_Y[1]) + 1.4} 0) (layer "F.SilkS") {font.format(s=1, t=0.15)})',
         f'\t(property "Value" "{NAME}" (at 0 {ky(PAD_Y[1]) + 2.9} 0) (layer "F.Fab") {font.format(s=1, t=0.15)})',
         '\t(attr smd)']
    # Fabrication layer: the case, its unused mounting holes, the lever at its free position, the trimmed terminals.
    half = BODY_W / 2
    outline = [(-half, CASE_BOTTOM_Y), (-half, above_holes(SHOULDER_TOP)), (from_side(SHOULDER_W), above_holes(SHOULDER_TOP)),
               (from_side(SHOULDER_W), above_holes(CASE_TOP)), (half, above_holes(CASE_TOP)), (half, CASE_BOTTOM_Y)]
    pts = ' '.join(f'(xy {kx(x)} {ky(y)})' for x, y in outline)
    o.append(f'\t(fp_poly (pts {pts}) {stroke.format(w=0.1)} (fill no) (layer "F.Fab"))')
    for i in range(2):
        x = kx(from_side(HOLE_FIRST + i * HOLE_PITCH))
        o.append(f'\t(fp_circle (center {x} {ky(HOLE_Y)}) (end {round(x + HOLE_D / 2, 4)} {ky(HOLE_Y)}) {stroke.format(w=0.1)} (fill no) (layer "F.Fab"))')
    (px, py), (tx, ty) = lever()
    o.append(f'\t(fp_circle (center {kx(px)} {ky(py)}) (end {round(kx(px) + PIVOT_R, 4)} {ky(py)}) {stroke.format(w=0.1)} (fill no) (layer "F.Fab"))')
    o.append(f'\t(fp_line (start {kx(px)} {ky(py)}) (end {kx(tx)} {ky(ty)}) {stroke.format(w=0.1)} (layer "F.Fab"))')
    o.append(f'\t(fp_circle (center {kx(tx)} {ky(ty)}) (end {round(kx(tx) + LEVER_TIP_R, 4)} {ky(ty)}) {stroke.format(w=0.1)} (fill no) (layer "F.Fab"))')
    for _, _, x in terminals():
        o.append(f'\t(fp_rect (start {kx(x + TERMINAL_W / 2)} {ky(CASE_BOTTOM_Y)}) (end {kx(x - TERMINAL_W / 2)} {ky(CASE_BOTTOM_Y - TRIM)}) '
                 f'{stroke.format(w=0.1)} (fill no) (layer "F.Fab"))')
    o.append(f'\t(fp_text user "${{REFERENCE}}" (at 0 {ky(above_holes(1.9))} 0) (layer "F.Fab") {font.format(s=1, t=0.15)})')
    # Board edge and notes.
    o.append(f'\t(fp_line (start -6.5 0) (end 6.5 0) {stroke.format(w=0.1)} (layer "Dwgs.User"))')
    o.append(f'\t(fp_text user "board edge; lever stands up to {LEVER_PROUD:g} mm beyond" (at 0 {round(-LEVER_PROUD - 1.1, 3)} 0) (layer "Dwgs.User") {font.format(s=0.6, t=0.09)})')
    note_y = ky(PAD_Y[1]) + 4.3
    o.append(f'\t(fp_text user "terminals leave the case {TERMINAL_CENTRE_ABOVE_BOARD:.2f} mm above the board (centre; underside {TERMINAL_UNDERSIDE_ABOVE_BOARD:.2f} mm):" '
             f'(at 0 {round(note_y, 3)} 0) (layer "Cmts.User") {font.format(s=0.6, t=0.09)})')
    o.append(f'\t(fp_text user "trim to {TRIM} mm and joggle down to the pads" (at 0 {round(note_y + 1.0, 3)} 0) (layer "Cmts.User") {font.format(s=0.6, t=0.09)})')
    o.append(f'\t(fp_text user "{order}; 1 is at the lever pivot. To be confirmed with a meter" (at 0 {round(note_y + 2.0, 3)} 0) (layer "Cmts.User") {font.format(s=0.6, t=0.09)})')
    # Silk: terminal 1 marker, beside its pad and clear of the case.
    one = kx(terminals()[0][2])
    o.append(f'\t(fp_text user "1" (at {round(one + math.copysign(PAD_W / 2 + 0.55, one), 3)} {ky(PAD_Y[1]) - 0.7} 0) (layer "F.SilkS") {font.format(s=0.8, t=0.12)})')
    # Courtyard: the case width, from the lever's free position to the end of the pads.
    cx = half + 0.25
    o.append(f'\t(fp_rect (start {-cx} {round(-LEVER_PROUD - 0.25, 3)}) (end {cx} {ky(PAD_Y[1]) + 0.25}) {stroke.format(w=0.05)} (fill no) (layer "F.CrtYd"))')
    # Pads.
    for name, x, y, w, h in pads():
        o.append(f'\t(pad "{name}" smd rect (at {kx(x)} {ky(y)}) (size {round(w, 3)} {round(h, 3)}) (layers "F.Cu" "F.Mask"))')
    o.append('\t(embedded_fonts no)')
    o.append(')')
    return '\n'.join(o) + '\n'


def checks():
    """What the land pattern has to keep; raises if a constant is changed carelessly."""
    xs = [x for _, x, _, _, _ in pads()]
    assert [name for name, _, _ in terminals()] == ['1', '2', '3'] and xs == [-2.5, 0.0, 2.5], xs
    gap = min(b - a for a, b in zip(xs, xs[1:])) - PAD_W
    assert gap >= 0.9 - 1e-6, f'pad-to-pad gap {gap:.2f} mm'
    assert max(abs(x) for x in xs) + PAD_W / 2 <= BODY_W / 2 + 1e-6, 'pads run outside the case width'
    assert PAD_W >= TERMINAL_BARB_W, 'pad narrower than the terminal barbs'
    assert abs(CASE_BOTTOM_Y + 7.8) < 1e-6, CASE_BOTTOM_Y
    assert above_holes(OPERATE - OPERATE_TOL) - 0.3 >= 0.1 - 1e-6, 'a worst-case part no longer finishes its stroke above the board edge'
    assert PAD_Y[0] <= CASE_BOTTOM_Y and PAD_Y[1] <= CASE_BOTTOM_Y - TRIM - 0.3, 'pad does not cover the trimmed terminal'
    assert TRIM <= TERMINAL_L
    assert abs(from_side(HOLE_FIRST) + from_side(HOLE_FIRST + HOLE_PITCH)) < 1e-6, 'mounting holes not centred'
    (px, py), (tx, ty) = lever()
    assert abs(ty + LEVER_TIP_R - LEVER_PROUD) < 1e-3, 'lever does not rest at the stated height'
    assert tx + LEVER_TIP_R <= BODY_W / 2 and px + LEVER_SWING_R + LEVER_TIP_R <= BODY_W / 2, 'lever swings outside the case width'
    assert py + PIVOT_R <= 0.4 + 1e-6, 'the fixed lever hub stands more than 0.4 mm beyond the board edge'
    text = footprint()
    assert 'thru_hole' not in text and 'drill' not in text, 'this footprint puts no holes in the board'
    assert text.count('(') == text.count(')')


def main():
    checks()
    LIBRARY.mkdir(parents=True, exist_ok=True)
    (LIBRARY / f'{NAME}.kicad_mod').write_text(footprint())
    contact = {name: c for name, c, _ in terminals()}
    for name, x, y, w, h in pads():
        print(f'{name:2} {contact[name]:3}  back view ({x:5.2f}, {y:6.2f})  KiCad ({kx(x):5.2f}, {ky(y):5.2f})  {w:.1f} x {h:.1f}')
    snap = above_holes(OPERATE)
    print('contact order from the datasheet drawings, pad 1 at the lever pivot: to be confirmed with a meter')
    print(f'case bottom {-CASE_BOTTOM_Y:.1f} mm below the edge; lever rests {LEVER_PROUD:.1f} mm beyond it (maximum) and snaps '
          f'{snap - OPERATE_TOL:+.1f} to {snap + OPERATE_TOL:+.1f} mm from it')
    print(f'terminal centre {TERMINAL_CENTRE_ABOVE_BOARD:.2f} mm above the board, underside {TERMINAL_UNDERSIDE_ABOVE_BOARD:.2f} mm; '
          f'trimmed to {TRIM} mm they end {-PAD_Y[1] + CASE_BOTTOM_Y - TRIM:.1f} mm inside the pads')


if __name__ == '__main__':
    main()
