"""Preview of the control cluster on the custom board, seen from the user side.

The user side is the bare face of the board; every part is on the far side.
The two Alps RK10J11E0034 dials are mounted face-down against the board, their
rims standing above the top edge. Each dial carries a ring of labels near its
outer edge; a small hole in the board below the dial centre shows the one
label that is selected. The shutter switch, an Omron D2MQ hinge-lever
microswitch lying flat, sits between the dials and a reverse-mount RGB LED
shows through a hole below its terminal pads.

The user confirmed the arrangement on November 25, 2026 ("lock it in") and,
on November 26, the wider dial spacing the switch needs ("26mm spacing and
gold contacts. lock it in."). The constants below are the baseline for
placement. The script also writes them as control-cluster.json. Run:  python tools/build_control_cluster_preview.py
"""
import json
import math
from pathlib import Path

import build_dial_footprint as dial_footprint       # the one definition of the dial's lands and label hole

OUT = Path(__file__).resolve().parents[1] / 'docs/custom-pcb/control-cluster-preview.svg'

# Board: ISO ID-1 card outline (spec.md), millimetres. Origin top-left, y down.
BOARD_W, BOARD_H, CORNER_R = 85.60, 53.98, 3.18

# From the user's description, November 25.
CLUSTER_CENTRE_X = BOARD_W * 0.75 - 1.0   # 1 mm left of the centre of the right half: the ASA dial moved 2 mm left for the switch, the exposure dial stayed
PROTRUSION = 2.0            # how far each dial rim and the button stand above the top edge

# Alps RK10J11E0034, from datasheets/controls (knob centre is the part origin).
KNOB_R = 7.0
BODY_HALF_W, BODY_TOP, BODY_BOTTOM = 5.15, 5.0, -7.6      # metal frame; terminals leave at y = -7.5
SUBSTRATE_LEFT, SUBSTRATE_TOP = -6.0, -1.1                # substrate runs wider on one side
TAB_RIGHT, TAB_TOP, TAB_BOTTOM = 7.0, -1.9, -4.0          # flat frame tab on the other side

# Drawn by the reviewer and confirmed with the rest of the drawing.
DIAL_PITCH = 26.0           # centre to centre; 24 until the 8.2 mm switch body had to fit between the inner tab pads
WINDOW_D = dial_footprint.LABEL_HOLE_D      # hole that shows one label
WINDOW_R = dial_footprint.LABEL_HOLE_R      # its centre, measured from the knob centre
LABEL_SWEEP = 260           # degrees of the 270 degree travel used by the labels
LED_BELOW_EDGE = 12.6       # hole centre; 1.6 mm below the end of the switch's terminal pads
LED_HOLE_D = 2.0            # follows the reverse-mount RGB LED still to be confirmed

DIAL_Y = KNOB_R - PROTRUSION                     # centre depth below the top edge
BUTTON_X = CLUSTER_CENTRE_X
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
        for sign in (-1, 1):                                       # tabs folded outward, flat with the back of the pot
            x1, x2 = sorted((sign * dial_footprint.TAB_FACE_X, sign * dial_footprint.TAB_TIP_X))
            add(f'<rect x="{n(cx + x1)}" y="{n(DIAL_Y - dial_footprint.TAB_Y - dial_footprint.TAB_W / 2)}" width="{n(x2 - x1)}" '
                f'height="{n(dial_footprint.TAB_W)}" {hidden}/>')
        for _, px, py, pw, ph in dial_footprint.pads():
            add(f'<rect x="{n(cx + px - pw / 2)}" y="{n(DIAL_Y - py - ph / 2)}" width="{n(pw)}" height="{n(ph)}" '
                f'fill="#d9a441" fill-opacity="0.55" stroke="#bfe3d0" stroke-width="0.08" stroke-dasharray="0.4 0.3"/>')
    add(f'<rect x="{n(BUTTON_X - 1.6)}" y="{n(LED_BELOW_EDGE - 1.4)}" width="3.2" height="2.8" {hidden}/>')
    add('</g>')
    import build_shutter_fit_preview as shutter              # imported here: that module imports this one
    shutter.switch_svg(add, ghost=True)                      # outside the clip: the lever stands above the edge

    # Label rings on the dial faces (behind the board) and the window that shows one label.
    for cx, marks, shown in ((ASA_X, ('100', '200', '400', '800'), 2),
                             (EXPOSURE_X, ('1000', '500', '250', '125', '60', '30', '15', '8', '4', '2'), 3)):
        step = LABEL_SWEEP / (len(marks) - 1)
        wy = DIAL_Y + WINDOW_R
        add(f'<circle cx="{n(cx)}" cy="{n(wy)}" r="{n(WINDOW_D / 2)}" fill="#e3cb9b" stroke="#0f2a1e" stroke-width="0.2"/>')
        for i, m in enumerate(marks):
            turn = (i - shown) * step                       # the shown label sits at six o'clock
            size = 1.0 if len(marks) > 4 else 1.25
            if i == shown:
                add(f'<text x="{n(cx)}" y="{n(wy + size * 0.36)}" font-size="{size}" text-anchor="middle" fill="#2b1f08" font-weight="bold">{m}</text>')
            else:
                add(f'<text x="{n(cx)}" y="{n(wy + size * 0.36)}" font-size="{size}" text-anchor="middle" fill="#bfe3d0" fill-opacity="0.75" '
                    f'transform="rotate({n(turn)} {n(cx)} {n(DIAL_Y)})">{m}</text>')

    # LED window.
    add(f'<circle cx="{n(BUTTON_X)}" cy="{n(LED_BELOW_EDGE)}" r="{n(LED_HOLE_D / 2)}" fill="#fff6c9" stroke="#0f2a1e" stroke-width="0.2"/>')

    # Names.
    text(ASA_X, DIAL_Y + 12.6 + 5.2, 'ASA dial', 1.7, fill='#ffffff', weight='bold')
    text(EXPOSURE_X, DIAL_Y + 12.6 + 5.2, 'Exposure dial', 1.7, fill='#ffffff', weight='bold')
    text(BUTTON_X, LED_BELOW_EDGE + 3.4, 'RGB LED', 1.25, fill='#ffffff')
    text(BUTTON_X, -PROTRUSION - 1.6, 'Shutter', 1.5, fill='#222222', weight='bold')
    text(BOARD_W / 2, BOARD_H - 16, 'USER SIDE (bare board)', 2.6, fill='#9fd0b6', weight='bold')
    text(BOARD_W / 2, BOARD_H - 12.4, 'all parts are on the far side; dashed lines show them through the board', 1.4, fill='#9fd0b6')
    text(2.2, BOARD_H - 2.2, f'{BOARD_W:.2f} x {BOARD_H:.2f} mm card outline', 1.3, 'start', '#9fd0b6')

    # Dimensions.
    dim_h(BOARD_W / 2, BOARD_W, -6.4, 'right half of the top edge; the cluster sits 1 mm left of its centre')
    dim_h(ASA_X, EXPOSURE_X, -10.4, f'{n(DIAL_PITCH)} mm between dial centres')
    add(f'<path d="M{n(ASA_X)} -10.4 V-8.8 M{n(EXPOSURE_X)} -10.4 V-8.8 M{n(BUTTON_X)} -6.4 V{n(-PROTRUSION - 2.6)} M{n(BOARD_W / 2)} -6.4 V0" stroke="#b3261e" stroke-width="0.06" stroke-dasharray="0.3 0.3"/>')
    x = ASA_X - KNOB_R - 2.2
    add(f'<path d="M{n(x)} {n(-PROTRUSION)} V0 M{n(x - 0.7)} {n(-PROTRUSION)} H{n(x + 4.2)} M{n(x - 0.7)} 0 H{n(x + 0.7)}" stroke="#b3261e" stroke-width="0.12" fill="none"/>')
    text(x - 1.0, -0.5, f'{n(PROTRUSION)} mm', 1.35, 'end', '#b3261e')
    text(BUTTON_X, DIAL_Y + 12.6 + 8.2, f'a {n(WINDOW_D)} mm hole below each dial centre shows the selected label', 1.2, fill='#ffffff')
    text(BOARD_W / 2, BOARD_H + 4.2, 'Control cluster preview, seen from the user side. Dials are 14 mm Alps RK10J11E0034 wheels, mounted face-down.', 1.45)
    text(BOARD_W / 2, BOARD_H + 6.8, 'Faint numbers are the label ring on each dial face, hidden by the board.', 1.3, fill='#555555')
    text(BOARD_W / 2, BOARD_H + 9.0, 'The shutter switch is an Omron D2MQ hinge-lever microswitch lying flat; its lever rests 2 mm above the edge.', 1.3, fill='#555555')
    add('</svg>')
    return '\n'.join(o) + '\n'


def record():
    """The confirmed positions, user-side view: origin at the board's top-left corner, x right, y down."""
    import build_shutter_fit_preview as shutter
    def dial(x):
        return dict(knob_centre=[round(x, 2), DIAL_Y], label_hole_centre=[round(x, 2), round(DIAL_Y + WINDOW_R, 2)])
    return dict(
        schema=1,
        confirmed='2026-11-25, by the user, from control-cluster-preview.svg; dial spacing widened from 24 to 26 mm for the shutter switch and confirmed 2026-11-26',
        units='mm',
        view='user side (bare face); on the parts side x is mirrored: x_parts = board_width - x',
        board=dict(width=BOARD_W, height=BOARD_H, corner_radius=CORNER_R),
        order_left_to_right=['ASA dial', 'shutter switch', 'exposure dial'],
        cluster_centre_x=round(BUTTON_X, 2),
        dial_pitch=DIAL_PITCH,
        knob_protrusion_above_top_edge=PROTRUSION,
        asa_dial=dial(ASA_X),
        exposure_dial=dial(EXPOSURE_X),
        label_hole=dict(diameter=WINDOW_D, radius_from_knob_centre=WINDOW_R, shows='the one selected label'),
        shutter_switch=dict(part='Omron D2MQ-4L-105-1, lying flat on the parts side, lever toward the top edge, terminals re-formed onto pads',
                            centre_x=round(BUTTON_X, 2), lever_rest_above_top_edge=PROTRUSION,
                            case_bottom_below_top_edge=round(shutter.BOTTOM_Y, 2),
                            terminal_pads_end_below_top_edge=round(shutter.PAD_Y[1], 2)),
        led_hole=dict(centre=[round(BUTTON_X, 2), LED_BELOW_EDGE], diameter=LED_HOLE_D,
                      provisional='diameter follows the reverse-mount RGB LED chosen'),
        dial_part='Alps RK10J11E0034, mounted face-down, terminals pointing away from the top edge',
        dial_footprint='hardware/beta/GXB.pretty/' + dial_footprint.NAME + '.kicad_mod')


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build())
    OUT.with_name('control-cluster.json').write_text(json.dumps(record(), indent=2) + '\n')
    print(f'dial centres {DIAL_Y:.1f} mm below the top edge; label hole {WINDOW_D:.1f} mm at {DIAL_Y + WINDOW_R:.1f} mm below the edge; '
          f'ASA x={ASA_X:.1f}, switch x={BUTTON_X:.1f}, exposure x={EXPOSURE_X:.1f}')


if __name__ == '__main__':
    main()
