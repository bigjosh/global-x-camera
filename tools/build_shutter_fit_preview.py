"""Proposed fit of the Omron D2MQ shutter switch between the two dials, back view.

The switch (D2MQ-4L-105-1, lever type) lies flat on the parts side with its
lever toward the top edge and its three terminals folded flat onto pads. To
give its 8.2 mm body room between the dials' inner tab pads, this proposal
moves the ASA dial 2 mm left and the switch and LED 1 mm left of the locked
positions; the exposure dial does not move.

Switch figures are from distributor listings of Omron's datasheet, which is
not stored: body 8.2 x 6.5 x 2.7 mm, lever 6.3 mm, operating position 7.1 mm
and free position 8.7 mm above the base, terminal spacings 2.5 and 4 mm.
The terminal positions drawn are therefore provisional.

Run:  python tools/build_shutter_fit_preview.py
"""
import math
from pathlib import Path

import build_control_cluster_preview as cluster
import build_dial_footprint as dial

OUT = Path(__file__).resolve().parents[1] / 'docs/custom-pcb/shutter-switch-fit.svg'
W = cluster.BOARD_W
ASA_SHIFT, SWITCH_SHIFT = -2.0, -1.0
ASA_X, EXP_X = cluster.ASA_X + ASA_SHIFT, cluster.EXPOSURE_X
SW_X = cluster.BUTTON_X + SWITCH_SHIFT
DIAL_Y = cluster.DIAL_Y

BODY_W, BODY_H = 8.2, 6.5                 # along the edge, into the board (the switch is 2.7 thick)
FREE, OPERATE = 8.7 - BODY_H, 7.1 - BODY_H   # lever tip above the body's top face: free, and where it snaps
LEVER = 6.3
TERMINALS = (-3.25, -0.75, 3.25)          # provisional: spacings 2.5 and 4 mm
PAD_W, PAD_L = 1.4, 2.6
LED_Y = 12.2                              # LED hole moves down to clear the terminal pads

X0, X1, Y0, Y1 = 38.0, 88.0, -8.0, 19.0
S = 20


def n(v):
    return f'{v:.2f}'.rstrip('0').rstrip('.')


def build():
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{n((X1 - X0) * S)}" height="{n((Y1 - Y0 + 5) * S)}" '
         f'viewBox="{n(X0)} {n(Y0)} {n(X1 - X0)} {n(Y1 - Y0 + 5)}" font-family="Helvetica, Arial, sans-serif">',
         f'<rect x="{n(X0)}" y="{n(Y0)}" width="{n(X1 - X0)}" height="{n(Y1 - Y0 + 5)}" fill="#f6f5f1"/>']
    add = o.append

    def text(x, y, s, size=0.9, fill='#222', anchor='middle', weight='normal'):
        add(f'<text x="{n(x)}" y="{n(y)}" font-size="{size}" text-anchor="{anchor}" fill="{fill}" font-weight="{weight}">{s}</text>')

    def dim(x1, x2, y, label, up=True):
        add(f'<path d="M{n(x1)} {n(y)} H{n(x2)} M{n(x1)} {n(y - 0.5)} V{n(y + 0.5)} M{n(x2)} {n(y - 0.5)} V{n(y + 0.5)}" stroke="#b3261e" stroke-width="0.08" fill="none"/>')
        text((x1 + x2) / 2, y - 0.4 if up else y + 1.1, label, 0.8, '#b3261e')

    # Wheels above the edge, then the board.
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

    # The switch: body, lever at rest and at the snap point, folded terminals on pads.
    bx = SW_X - BODY_W / 2
    add(f'<rect x="{n(bx)}" y="0" width="{n(BODY_W)}" height="{n(BODY_H)}" fill="#22262b" stroke="#0d0f11" stroke-width="0.1"/>')
    text(SW_X, BODY_H / 2 - 0.2, 'D2MQ', 0.95, '#e6e6e6', weight='bold')
    text(SW_X, BODY_H / 2 + 1.0, f'{n(BODY_W)} x {n(BODY_H)}', 0.75, '#c9cdd3')
    hinge_x = bx + 0.6
    tip_x = hinge_x + LEVER
    add(f'<path d="M{n(hinge_x)} -0.15 L{n(tip_x)} {n(-FREE)}" stroke="#c9cdd3" stroke-width="0.3" stroke-linecap="round"/>')
    add(f'<path d="M{n(hinge_x)} -0.15 L{n(tip_x)} {n(-OPERATE)}" stroke="#c9cdd3" stroke-width="0.2" stroke-dasharray="0.4 0.3" stroke-linecap="round"/>')
    for tx in TERMINALS:
        add(f'<rect x="{n(SW_X + tx - PAD_W / 2)}" y="{n(BODY_H + 0.2)}" width="{n(PAD_W)}" height="{n(PAD_L)}" {pad}/>')
        add(f'<rect x="{n(SW_X + tx - 0.3)}" y="{n(BODY_H)}" width="0.6" height="2.0" fill="#8c8f94"/>')
    add(f'<circle cx="{n(SW_X)}" cy="{n(LED_Y)}" r="{n(cluster.LED_HOLE_D / 2)}" fill="#fff6c9" stroke="#0f2a1e" stroke-width="0.12"/>')
    text(SW_X, LED_Y + 2.3, 'LED hole', 0.8, '#ffffff')

    # Dimensions.
    asa_pad = ASA_X + dial.TAB_PAD_X[1]
    exp_pad = EXP_X - dial.TAB_PAD_X[1]
    dim(asa_pad, bx, 4.6, n(bx - asa_pad), up=False)
    dim(bx + BODY_W, exp_pad, 4.6, n(exp_pad - bx - BODY_W), up=False)
    dim(ASA_X, EXP_X, -5.6, f'{n(EXP_X - ASA_X)} mm between dial centres (was 24)')
    dim(EXP_X + dial.KNOB_R, W, -3.6, n(W - EXP_X - dial.KNOB_R))
    add(f'<path d="M{n(tip_x + 1.2)} {n(-FREE)} V0 M{n(tip_x + 0.8)} {n(-FREE)} H{n(tip_x + 1.6)} M{n(tip_x + 0.8)} 0 H{n(tip_x + 1.6)}" stroke="#b3261e" stroke-width="0.08" fill="none"/>')
    x = ASA_X - dial.KNOB_R - 1.0
    add(f'<path d="M{n(x)} {n(DIAL_Y - dial.KNOB_R)} V0 M{n(x - 0.4)} {n(DIAL_Y - dial.KNOB_R)} H{n(x + 0.4)} M{n(x - 0.4)} 0 H{n(x + 0.4)}" stroke="#b3261e" stroke-width="0.08" fill="none"/>')
    text(x - 0.5, -0.7, '2', 0.8, '#b3261e', 'end')
    text(SW_X, -3.4, f'lever: {n(FREE)} mm proud at rest, snaps at {n(OPERATE)} mm', 0.8, '#b3261e')
    text(X0 + 1, 17.6, 'BACK VIEW (user side); parts shown through the board', 0.85, '#9fd0b6', 'start')
    y = Y1 + 1.4
    text((X0 + X1) / 2, y, 'Proposed: ASA dial 2 mm left and the switch and LED 1 mm left of the locked positions; exposure dial unchanged.', 0.9)
    text((X0 + X1) / 2, y + 1.4, 'The switch body sits with its top face at the board edge. Lever tip stands 2.2 mm proud at rest and snaps 0.6 mm above the edge.', 0.85, '#444')
    text((X0 + X1) / 2, y + 2.8, 'Terminal positions are provisional until Omron\'s drawing is in hand. Gold pads are solder lands.', 0.85, '#444')
    o.append('</svg>')
    return '\n'.join(o) + '\n'


def main():
    OUT.write_text(build())
    bx = SW_X - BODY_W / 2
    print(f'ASA {ASA_X}, switch {SW_X}, exposure {EXP_X}; clearances {bx - (ASA_X + dial.TAB_PAD_X[1]):.2f} and {(EXP_X - dial.TAB_PAD_X[1]) - (bx + BODY_W):.2f} mm; '
          f'wheel rim to body {bx - (ASA_X + math.sqrt(dial.KNOB_R ** 2 - DIAL_Y ** 2)):.2f} mm at the edge')


if __name__ == '__main__':
    main()
