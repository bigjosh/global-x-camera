"""Fit of the Omron D2MQ hinge-lever switch between the two dials, back view.

The switch (D2MQ-4L-105-1: hinge lever, straight terminals, gold contacts)
lies flat on the parts side, lever toward the top edge, its three terminals
joggled down and soldered to pads. Geometry is from Omron's datasheet, stored
in datasheets/controls. Omron measures lever positions from the mounting-hole
centre line, 1.6 mm above the case bottom.

To give the 8.2 mm body room between the dials' inner tab pads, the dials
are 26 mm apart: the ASA dial sits 2 mm and the switch and LED 1 mm left of
the first locked positions; the exposure dial did not move. The user confirmed
this on November 26, 2026, and the positions now come from the control
cluster script.

Run:  python tools/build_shutter_fit_preview.py
"""
import math
from pathlib import Path

import build_control_cluster_preview as cluster
import build_dial_footprint as dial
import build_shutter_footprint as switch          # the one definition of the switch and its lands

OUT = Path(__file__).resolve().parents[1] / 'docs/custom-pcb/shutter-switch-fit.svg'
W = cluster.BOARD_W
ASA_X, EXP_X = cluster.ASA_X, cluster.EXPOSURE_X
SW_X = cluster.BUTTON_X
DIAL_Y = cluster.DIAL_Y

# Omron D2MQ-4L, heights above the case bottom (the footprint script keeps Omron's own reference, the hole line).
BODY_W = switch.BODY_W
CASE_TOP = switch.CASE_TOP + switch.HOLE_LINE          # top face of the case, under the lever
SHOULDER_TOP = switch.SHOULDER_TOP + switch.HOLE_LINE  # raised pivot end
PIVOT = switch.PIVOT + switch.HOLE_LINE                # lever pivot
FREE = switch.FREE + switch.HOLE_LINE                  # top of the lever end at rest (maximum)
OPERATE = switch.OPERATE + switch.HOLE_LINE            # where it snaps (+/-0.5)
HOLE_LINE, HOLE_PITCH = switch.HOLE_LINE, switch.HOLE_PITCH
TERMINALS = tuple(x for _, _, x in switch.terminals())
TERMINAL_W = switch.TERMINAL_W

# Placement, from the footprint.
LEVER_PROUD = switch.LEVER_PROUD           # the lever at rest stands at most this far above the board's top edge
BOTTOM_Y = -switch.CASE_BOTTOM_Y           # case bottom, this far below the edge
TRIM = switch.TRIM                         # terminals trimmed to this length when they are re-formed
PAD_W, PAD_Y = switch.PAD_W, (-switch.PAD_Y[0], -switch.PAD_Y[1])
LED_Y = cluster.LED_BELOW_EDGE             # LED hole centre, clear of the terminal pads
assert abs(LED_Y - (PAD_Y[1] + 1.6)) < 1e-6, 'the locked LED hole no longer sits 1.6 mm below the terminal pads'
FET_W, FET_H, FET_GAP = 2.9, 1.6, 0.4      # four SOT-23, two each side of the LED
LED_BODY = (3.2, 2.8)

X0, X1, Y0, Y1 = 36.0, 88.0, -9.0, 20.0
S = 20


def edge_y(height):
    """Board y of a point this far above the case bottom."""
    return BOTTOM_Y - height


def fets():
    """(x, y, w, h) of the four FETs, a row centred on the LED."""
    half = LED_BODY[0] / 2 + FET_GAP
    xs = [SW_X - half - 2 * FET_W - FET_GAP, SW_X - half - FET_W, SW_X + half, SW_X + half + FET_W + FET_GAP]
    return [(x, LED_Y - FET_H / 2, FET_W, FET_H) for x in xs]


def n(v):
    return f'{v:.2f}'.rstrip('0').rstrip('.')


def switch_svg(add, front=False, X=lambda x: x, oy=0.0, ghost=False):
    """Draw the switch; used here and by the whole-board drawing."""
    bx = SW_X - BODY_W / 2
    def rx(x, w):                      # left edge after optional mirroring
        return X(x + w) if front else X(x)
    dash = 'fill="none" stroke="#bfe3d0" stroke-width="0.12" stroke-dasharray="0.6 0.4"'
    sw = switch.SHOULDER_W                                   # the pivot end of the case is a raised shoulder
    outline = [(bx, BOTTOM_Y), (bx, edge_y(SHOULDER_TOP)), (bx + sw, edge_y(SHOULDER_TOP)), (bx + sw, edge_y(CASE_TOP)),
               (bx + BODY_W, edge_y(CASE_TOP)), (bx + BODY_W, BOTTOM_Y)]
    add('<path d="M' + ' L'.join(f'{n(X(x))} {n(oy + y)}' for x, y in outline) + ' Z" '
        + (dash if ghost else 'fill="#22262b" stroke="#0d0f11" stroke-width="0.1"') + '/>')
    for hx in (-HOLE_PITCH / 2, HOLE_PITCH / 2):
        add(f'<circle cx="{n(X(SW_X + hx))}" cy="{n(oy + edge_y(HOLE_LINE))}" r="0.8" fill="#2f6b4f" stroke="#555" stroke-width="0.06"/>')
    (px, py), (tx, ty) = switch.lever()                      # back view about the switch centre, +y beyond the edge
    px, py, tx, ty = SW_X + px, -py, SW_X + tx, -ty
    add(f'<path d="M{n(X(px))} {n(oy + py)} L{n(X(tx))} {n(oy + ty)}" stroke="#d7dbe0" stroke-width="0.35" stroke-linecap="round"/>')
    add(f'<circle cx="{n(X(tx))}" cy="{n(oy + ty)}" r="{switch.LEVER_TIP_R}" fill="#d7dbe0"/>')
    add(f'<circle cx="{n(X(px))}" cy="{n(oy + py)}" r="{switch.PIVOT_R}" fill="#3a3f46" stroke="#0d0f11" stroke-width="0.06"/>')
    for t in TERMINALS:
        add(f'<rect x="{n(rx(SW_X + t - PAD_W / 2, PAD_W))}" y="{n(oy + PAD_Y[0])}" width="{n(PAD_W)}" height="{n(PAD_Y[1] - PAD_Y[0])}" '
            + (dash if ghost else 'fill="#d9a441" fill-opacity="0.8" stroke="#7a5a14" stroke-width="0.05"') + '/>')
        if not ghost:
            add(f'<rect x="{n(rx(SW_X + t - TERMINAL_W / 2, TERMINAL_W))}" y="{n(oy + BOTTOM_Y)}" width="{n(TERMINAL_W)}" height="{n(TRIM)}" fill="#8c8f94"/>')
    return px, tx


def build():
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{n((X1 - X0) * S)}" height="{n((Y1 - Y0 + 6) * S)}" '
         f'viewBox="{n(X0)} {n(Y0)} {n(X1 - X0)} {n(Y1 - Y0 + 6)}" font-family="Helvetica, Arial, sans-serif">',
         f'<rect x="{n(X0)}" y="{n(Y0)}" width="{n(X1 - X0)}" height="{n(Y1 - Y0 + 6)}" fill="#f6f5f1"/>']
    add = o.append

    def text(x, y, s, size=0.9, fill='#222', anchor='middle', weight='normal'):
        add(f'<text x="{n(x)}" y="{n(y)}" font-size="{size}" text-anchor="{anchor}" fill="{fill}" font-weight="{weight}">{s}</text>')

    def dim(x1, x2, y, label, up=True):
        add(f'<path d="M{n(x1)} {n(y)} H{n(x2)} M{n(x1)} {n(y - 0.5)} V{n(y + 0.5)} M{n(x2)} {n(y - 0.5)} V{n(y + 0.5)}" stroke="#b3261e" stroke-width="0.08" fill="none"/>')
        text((x1 + x2) / 2, y - 0.4 if up else y + 1.1, label, 0.8, '#b3261e')

    for cx in (ASA_X, EXP_X):
        add(f'<circle cx="{n(cx)}" cy="{n(DIAL_Y)}" r="{dial.KNOB_R}" fill="#1c1c1c"/>')
    r = cluster.CORNER_R
    add(f'<path d="M{n(X0)} 0 H{n(W - r)} A{r} {r} 0 0 1 {n(W)} {n(r)} V{n(Y1)} H{n(X0)} Z" fill="#2f6b4f" stroke="#17382a" stroke-width="0.15"/>')
    ghost = 'fill="none" stroke="#bfe3d0" stroke-width="0.09" stroke-dasharray="0.5 0.35"'
    pad = 'fill="#d9a441" fill-opacity="0.75" stroke="#7a5a14" stroke-width="0.05"'
    for cx, name in ((ASA_X, 'ASA dial'), (EXP_X, 'Exposure dial')):
        add(f'<circle cx="{n(cx)}" cy="{n(DIAL_Y)}" r="{dial.KNOB_R}" {ghost}/>')
        add(f'<rect x="{n(cx - dial.BODY_HALF_W)}" y="{n(DIAL_Y - dial.BODY_TOP)}" width="{n(2 * dial.BODY_HALF_W)}" height="{n(dial.BODY_TOP - dial.BODY_BOTTOM)}" {ghost}/>')
        for _, px, py, pw, ph in dial.pads():
            add(f'<rect x="{n(cx + px - pw / 2)}" y="{n(DIAL_Y - py - ph / 2)}" width="{n(pw)}" height="{n(ph)}" {pad}/>')
        add(f'<circle cx="{n(cx)}" cy="{n(DIAL_Y + dial.LABEL_HOLE_R)}" r="{n(dial.LABEL_HOLE_D / 2)}" fill="#e3cb9b" stroke="#0f2a1e" stroke-width="0.12"/>')
        text(cx, DIAL_Y + 0.3, name, 1.0, '#ffffff', weight='bold')

    px, _ = switch_svg(add)
    rise = OPERATE - switch.LEVER_TIP_R - PIVOT                # the lever end at the nominal operating position
    tx = px + math.sqrt(switch.LEVER_SWING_R ** 2 - rise ** 2)
    add(f'<path d="M{n(px)} {n(edge_y(PIVOT))} L{n(tx)} {n(edge_y(OPERATE - switch.LEVER_TIP_R))}" stroke="#d7dbe0" stroke-width="0.2" stroke-dasharray="0.4 0.3" stroke-linecap="round"/>')
    text(SW_X, edge_y(CASE_TOP) + 2.4, 'D2MQ', 0.95, '#e6e6e6', weight='bold')
    add(f'<circle cx="{n(SW_X)}" cy="{n(LED_Y)}" r="{n(cluster.LED_HOLE_D / 2)}" fill="#fff6c9" stroke="#0f2a1e" stroke-width="0.12"/>')
    add(f'<rect x="{n(SW_X - LED_BODY[0] / 2)}" y="{n(LED_Y - LED_BODY[1] / 2)}" width="{LED_BODY[0]}" height="{LED_BODY[1]}" {ghost}/>')
    for x, y, w, h in fets():
        add(f'<rect x="{n(x)}" y="{n(y)}" width="{w}" height="{h}" {ghost}/>')
    text(SW_X, LED_Y + 3.0, 'FET  FET  LED  FET  FET', 0.75, '#ffffff')

    bx = SW_X - BODY_W / 2
    asa_pad, exp_pad = ASA_X + dial.TAB_PAD_X[1], EXP_X - dial.TAB_PAD_X[1]
    dim(asa_pad, bx, 5.4, '', up=False)
    dim(bx + BODY_W, exp_pad, 5.4, '', up=False)
    dim(ASA_X, EXP_X, -6.6, f'{n(EXP_X - ASA_X)} mm between dial centres')
    dim(EXP_X + dial.KNOB_R, W, -3.6, n(W - EXP_X - dial.KNOB_R))
    x = ASA_X - dial.KNOB_R - 1.0
    add(f'<path d="M{n(x)} {n(DIAL_Y - dial.KNOB_R)} V0 M{n(x - 0.4)} {n(DIAL_Y - dial.KNOB_R)} H{n(x + 0.4)} M{n(x - 0.4)} 0 H{n(x + 0.4)}" stroke="#b3261e" stroke-width="0.08" fill="none"/>')
    text(x - 0.5, -0.7, '2', 0.8, '#b3261e', 'end')
    text(SW_X, -4.4, f'lever: up to {n(LEVER_PROUD)} mm proud at rest,', 0.8, '#b3261e')
    text(SW_X, -3.3, f'snaps {n(OPERATE - BOTTOM_Y)} ±{switch.OPERATE_TOL} mm above the edge', 0.8, '#b3261e')
    x = bx - 1.0
    add(f'<path d="M{n(x)} 0 V{n(BOTTOM_Y)} M{n(x - 0.4)} {n(BOTTOM_Y)} H{n(x + 0.4)}" stroke="#b3261e" stroke-width="0.08" fill="none"/>')
    text(x - 0.3, BOTTOM_Y + 1.0, n(BOTTOM_Y), 0.8, '#b3261e', 'end')
    text(X0 + 1, 18.8, 'BACK VIEW (user side); parts shown through the board', 0.85, '#9fd0b6', 'start')
    y = Y1 + 1.6
    text((X0 + X1) / 2, y, 'Confirmed November 26: dials 26 mm apart, the switch midway between them; exposure dial where it was first locked.', 0.9)
    text((X0 + X1) / 2, y + 1.4, f'Switch case bottom {n(BOTTOM_Y)} mm below the edge; {n(bx - asa_pad)} mm between the case and each dial\'s inner tab pad; terminals trimmed to {n(TRIM)} mm.', 0.85, '#444')
    text((X0 + X1) / 2, y + 2.8, 'The LED hole sits below the switch pads, with two FETs each side of it. Switch geometry from Omron\'s datasheet.', 0.85, '#444')
    o.append('</svg>')
    return '\n'.join(o) + '\n'


def main():
    OUT.write_text(build())
    bx = SW_X - BODY_W / 2
    print(f'ASA {ASA_X:.1f}, switch {SW_X:.1f}, exposure {EXP_X:.1f}; case bottom {BOTTOM_Y:.2f} below edge, case top {edge_y(CASE_TOP):.2f}, '
          f'snap {OPERATE - BOTTOM_Y:.2f} above edge; pads to {PAD_Y[1]:.2f}; LED hole at {LED_Y:.2f}; side clearance {bx - (ASA_X + dial.TAB_PAD_X[1]):.2f}')


if __name__ == '__main__':
    main()
