"""Preview of the control cluster on the custom board, seen from the user side.

The user side is the bare face of the board; every part is on the far side.
The two Alps RK10J11E0034 dials are mounted face-down against the board, their
faces seen through window holes, their rims standing above the top edge. The
shutter button sits between them and a reverse-mount RGB LED shows through a
hole below it.

This is a drawing to confirm the arrangement, not a placement. Edit the
constants and run again:  python tools/build_control_cluster_preview.py
"""
import math
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'docs/custom-pcb/control-cluster-preview.svg'

# Board: ISO ID-1 card outline (spec.md), millimetres. Origin top-left, y down.
BOARD_W, BOARD_H, CORNER_R = 85.60, 53.98, 3.18

# From the user's description, November 25.
SHUTTER_FROM_RIGHT = 25.4   # right board edge to the middle of the cluster ("about 1 inch")
PROTRUSION = 2.0            # how far each dial rim and the button stand above the top edge

# Alps RK10J11E0034, from datasheets/controls (knob centre is the part origin).
KNOB_R = 7.0
BODY_HALF_W, BODY_TOP, BODY_BOTTOM = 5.15, 5.0, -7.6      # metal frame; terminals leave at y = -7.5
SUBSTRATE_LEFT, SUBSTRATE_TOP = -6.0, -1.1                # substrate runs wider on one side
TAB_RIGHT, TAB_TOP, TAB_BOTTOM = 7.0, -1.9, -4.0          # flat frame tab on the other side
TERMINAL_X = (-4.0, -2.0, 0.0, 2.0, 4.0)
PAD_W, PAD_TOP, PAD_BOTTOM = 1.2, -7.0, -9.8              # lands for the folded-back terminals

# Assumptions made for the drawing; not yet decided.
DIAL_PITCH = 24.0           # centre to centre
EDGE_WEB = 1.0              # board left between a window and the top edge
BUTTON_W, BUTTON_BODY_W, BUTTON_BODY_H = 4.0, 6.5, 3.6
LED_HOLE_D, LED_BELOW_EDGE = 2.0, 7.5

DIAL_Y = KNOB_R - PROTRUSION                     # centre depth below the top edge
WINDOW_D = 2 * (DIAL_Y - EDGE_WEB)               # largest closed round window
BUTTON_X = BOARD_W - SHUTTER_FROM_RIGHT
ASA_X = BUTTON_X - DIAL_PITCH / 2
EXPOSURE_X = BUTTON_X + DIAL_PITCH / 2

MARGIN_L, MARGIN_T, MARGIN_R, MARGIN_B = 6.0, 15.0, 6.0, 15.0
SCALE = 11                                       # pixels per millimetre on screen


def n(v):
    return f'{v:.2f}'.rstrip('0').rstrip('.')


def build():
    width, height = BOARD_W + MARGIN_L + MARGIN_R, BOARD_H + MARGIN_T + MARGIN_B
    o = []
    add = o.append
    add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{n(width * SCALE)}" height="{n(height * SCALE)}" '
        f'viewBox="{n(-MARGIN_L)} {n(-MARGIN_T)} {n(width)} {n(height)}" font-family="Helvetica, Arial, sans-serif">')
    add(f'<rect x="{n(-MARGIN_L)}" y="{n(-MARGIN_T)}" width="{n(width)}" height="{n(height)}" fill="#f6f5f1"/>')
    add('<defs><clipPath id="above"><rect x="-10" y="-20" width="120" height="20"/></clipPath>'
        '<clipPath id="board"><rect x="0" y="0" width="%s" height="%s" rx="%s"/></clipPath></defs>' % (n(BOARD_W), n(BOARD_H), n(CORNER_R)))

    def text(x, y, s, size=1.5, anchor='middle', fill='#222222', weight='normal'):
        add(f'<text x="{n(x)}" y="{n(y)}" font-size="{size}" text-anchor="{anchor}" fill="{fill}" font-weight="{weight}">{s}</text>')

    def dim_h(x1, x2, y, label, above=True):
        add(f'<path d="M{n(x1)} {n(y)} H{n(x2)} M{n(x1)} {n(y - 0.7)} V{n(y + 0.7)} M{n(x2)} {n(y - 0.7)} V{n(y + 0.7)}" '
            f'stroke="#b3261e" stroke-width="0.12" fill="none"/>')
        text((x1 + x2) / 2, y - 0.6 if above else y + 1.7, label, 1.35, fill='#b3261e')

    # Parts that stand above the top edge (drawn first, the board covers the rest).
    for cx in (ASA_X, EXPOSURE_X):
        add(f'<g clip-path="url(#above)"><circle cx="{n(cx)}" cy="{n(DIAL_Y)}" r="{n(KNOB_R)}" fill="#1c1c1c"/>')
        for k in range(-40, 41):                                  # knurl
            a = math.radians(-90 + k * 4.5)
            x1, y1 = cx + (KNOB_R - 0.45) * math.cos(a), DIAL_Y + (KNOB_R - 0.45) * math.sin(a)
            x2, y2 = cx + KNOB_R * math.cos(a), DIAL_Y + KNOB_R * math.sin(a)
            add(f'<path d="M{n(x1)} {n(y1)} L{n(x2)} {n(y2)}" stroke="#6b6b6b" stroke-width="0.12"/>')
        add('</g>')
    add(f'<rect x="{n(BUTTON_X - BUTTON_W / 2)}" y="{n(-PROTRUSION)}" width="{n(BUTTON_W)}" height="{n(PROTRUSION + 0.5)}" rx="0.6" fill="#8c8f94" stroke="#44474b" stroke-width="0.1"/>')

    # The board, bare side.
    add(f'<rect x="0" y="0" width="{n(BOARD_W)}" height="{n(BOARD_H)}" rx="{n(CORNER_R)}" fill="#2f6b4f" stroke="#17382a" stroke-width="0.2"/>')

    # Parts behind the board, dashed.
    hidden = 'fill="none" stroke="#bfe3d0" stroke-width="0.12" stroke-dasharray="0.6 0.4"'
    add('<g clip-path="url(#board)">')
    for cx in (ASA_X, EXPOSURE_X):
        add(f'<circle cx="{n(cx)}" cy="{n(DIAL_Y)}" r="{n(KNOB_R)}" {hidden}/>')
        add(f'<rect x="{n(cx - BODY_HALF_W)}" y="{n(DIAL_Y - BODY_TOP)}" width="{n(2 * BODY_HALF_W)}" height="{n(BODY_TOP - BODY_BOTTOM)}" {hidden}/>')
        add(f'<rect x="{n(cx + SUBSTRATE_LEFT)}" y="{n(DIAL_Y - SUBSTRATE_TOP)}" width="{n(-BODY_HALF_W - SUBSTRATE_LEFT)}" height="{n(SUBSTRATE_TOP - BODY_BOTTOM)}" {hidden}/>')
        add(f'<rect x="{n(cx + BODY_HALF_W)}" y="{n(DIAL_Y - TAB_TOP)}" width="{n(TAB_RIGHT - BODY_HALF_W)}" height="{n(TAB_TOP - TAB_BOTTOM)}" {hidden}/>')
        for tx in TERMINAL_X:
            add(f'<rect x="{n(cx + tx - PAD_W / 2)}" y="{n(DIAL_Y - PAD_TOP)}" width="{n(PAD_W)}" height="{n(PAD_TOP - PAD_BOTTOM)}" '
                f'fill="#d9a441" fill-opacity="0.55" stroke="#bfe3d0" stroke-width="0.08" stroke-dasharray="0.4 0.3"/>')
    add(f'<rect x="{n(BUTTON_X - BUTTON_BODY_W / 2)}" y="0.3" width="{n(BUTTON_BODY_W)}" height="{n(BUTTON_BODY_H)}" {hidden}/>')
    add(f'<rect x="{n(BUTTON_X - 1.6)}" y="{n(LED_BELOW_EDGE - 1.4)}" width="3.2" height="2.8" {hidden}/>')
    add('</g>')

    # Windows onto the dial faces, each with its label.
    for cx, name, marks in ((ASA_X, 'ASA', ('100', '200', '400', '800')),
                            (EXPOSURE_X, 'SEC', ('1000', '250', '60', '15', '4', '2'))):
        r = WINDOW_D / 2
        add(f'<circle cx="{n(cx)}" cy="{n(DIAL_Y)}" r="{n(r)}" fill="#d8bd8a" stroke="#0f2a1e" stroke-width="0.25"/>')
        text(cx, DIAL_Y + 0.35, name, 0.95, fill='#3a2c12', weight='bold')
        for i, m in enumerate(marks):
            a = math.radians(150 + i * 240 / (len(marks) - 1))
            text(cx + (r - 0.95) * math.cos(a), DIAL_Y + (r - 0.95) * math.sin(a) + 0.25, m, 0.62, fill='#3a2c12')
        add(f'<path d="M{n(cx)} {n(DIAL_Y + r + 0.3)} l-0.5 0.8 h1 z" fill="#f2f2f2"/>')    # index mark on the board

    # LED window.
    add(f'<circle cx="{n(BUTTON_X)}" cy="{n(LED_BELOW_EDGE)}" r="{n(LED_HOLE_D / 2)}" fill="#fff6c9" stroke="#0f2a1e" stroke-width="0.2"/>')

    # Names.
    text(ASA_X, DIAL_Y + 12.6 + 5.2, 'ASA dial', 1.7, fill='#ffffff', weight='bold')
    text(EXPOSURE_X, DIAL_Y + 12.6 + 5.2, 'Exposure dial', 1.7, fill='#ffffff', weight='bold')
    text(BUTTON_X, LED_BELOW_EDGE + 3.6, 'RGB LED', 1.35, fill='#ffffff')
    text(BUTTON_X, -PROTRUSION - 0.9, 'Shutter', 1.5, fill='#222222', weight='bold')
    text(BOARD_W / 2, BOARD_H - 16, 'USER SIDE (bare board)', 2.6, fill='#9fd0b6', weight='bold')
    text(BOARD_W / 2, BOARD_H - 12.4, 'all parts are on the far side; dashed lines show them through the board', 1.4, fill='#9fd0b6')
    text(2.2, BOARD_H - 2.2, f'{BOARD_W:.2f} x {BOARD_H:.2f} mm card outline', 1.3, 'start', '#9fd0b6')

    # Dimensions.
    dim_h(BUTTON_X, BOARD_W, -6.4, f'{n(SHUTTER_FROM_RIGHT)} mm (1 in) from the shutter to the right edge')
    dim_h(ASA_X, EXPOSURE_X, -10.4, f'{n(DIAL_PITCH)} mm between dial centres (assumed)')
    add(f'<path d="M{n(ASA_X)} -10.4 V-8.8 M{n(EXPOSURE_X)} -10.4 V-8.8 M{n(BUTTON_X)} -6.4 V{n(-PROTRUSION - 2.6)}" stroke="#b3261e" stroke-width="0.06" stroke-dasharray="0.3 0.3"/>')
    x = ASA_X - KNOB_R - 2.2
    add(f'<path d="M{n(x)} {n(-PROTRUSION)} V0 M{n(x - 0.7)} {n(-PROTRUSION)} H{n(x + 4.2)} M{n(x - 0.7)} 0 H{n(x + 0.7)}" stroke="#b3261e" stroke-width="0.12" fill="none"/>')
    text(x - 1.0, -0.5, f'{n(PROTRUSION)} mm', 1.35, 'end', '#b3261e')
    text(ASA_X, DIAL_Y + WINDOW_D / 2 + 2.55, f'{n(WINDOW_D)} mm window', 1.1, fill='#ffffff')
    text(EXPOSURE_X, DIAL_Y + WINDOW_D / 2 + 2.55, f'{n(WINDOW_D)} mm window', 1.1, fill='#ffffff')
    text(BOARD_W / 2, BOARD_H + 4.2, 'Control cluster preview, seen from the user side. Dials are 14 mm Alps RK10J11E0034 wheels, face-down behind the windows.', 1.45)
    text(BOARD_W / 2, BOARD_H + 6.8, f'Each window is the largest closed round hole that leaves {n(EDGE_WEB)} mm of board at the top edge. '
         f'Dial spacing, button and LED sizes are placeholders.', 1.3, fill='#555555')
    add('</svg>')
    return '\n'.join(o) + '\n'


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build())
    print(f'dial centres {DIAL_Y:.1f} mm below the top edge; window {WINDOW_D:.1f} mm; '
          f'ASA x={ASA_X:.1f}, button x={BUTTON_X:.1f}, exposure x={EXPOSURE_X:.1f}')


if __name__ == '__main__':
    main()
