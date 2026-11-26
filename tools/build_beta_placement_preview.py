"""Draft placement of the beta board, drawn from both faces.

The back is the user's side (bare board); every part is on the front, which
may be seen through a clear case. Positions are kept in the back view, the
view the user describes the camera in: origin at the top-left corner, x to
the right, y down. The front view is the same data mirrored left to right.

The control group is locked (docs/custom-pcb/control-cluster.json). Everything
else here is a proposal to mark up, not a placement.

Run:  python tools/build_beta_placement_preview.py
"""
import math
from pathlib import Path

import build_control_cluster_preview as cluster
import build_dial_footprint as dial
import build_shutter_fit_preview as shutter

OUT = Path(__file__).resolve().parents[1] / 'docs/custom-pcb/beta-placement-draft.svg'
W, H, R = cluster.BOARD_W, cluster.BOARD_H, cluster.CORNER_R
MID_Y = H / 2

# From the user, November 26, all "as seen from the back".
LENS = (W / 3, MID_Y)                     # vertically centred, a third of the width from the left edge
SD_EDGE_Y = MID_Y                         # card slot centred on the left edge
RIGHT_KEEPOUT = W - (cluster.EXPOSURE_X + cluster.KNOB_R)   # for the housing's radiused front edge; shrunk on
                                          # November 26 to stop at the exposure dial's rim. The dial's flat
                                          # outer tab pad is the one thing allowed inside it.
# The tripod socket is part of the housing (user, November 26), so the board keeps nothing clear for it.

# Camera module (ST data brief): 6.5 mm square head, 7.45 mm from optical centre to connector centre.
HEAD, CONNECTOR_OFFSET = 6.5, 7.45
CUTOUT_CLEAR = 0.3

# Proposed blocks: name, x, y, w, h (back view), style, label.
CELL_W, CELL_H = 36.5, 24.1               # Grepow pack, landscape
CELL_X, CELL_Y = 44.6, MID_Y + 0.6 - CELL_H / 2
PARTS = [
    ('sd', 0.0, SD_EDGE_Y - 7.0, 15.0, 14.0, 'conn', 'microSD'),
    ('mcu', LENS[0] - 7.0, 2.6, 14.0, 14.0, 'ic', 'MCU'),
    ('nor', 37.0, 3.6, 5.0, 6.0, 'ic', 'NOR'),
    ('camconn', LENS[0] + CONNECTOR_OFFSET - 1.0, LENS[1] - 3.8, 2.0, 7.6, 'conn', ''),
    ('cell', CELL_X, CELL_Y, CELL_W, CELL_H, 'cell', 'LiPo 210 mAh'),
    ('pcm', CELL_X - 4.2, CELL_Y + 2.0, 3.6, CELL_H - 4.0, 'pcm', ''),
    ('buck', LENS[0] - 9.0, 36.2, 5.0, 4.0, 'pwr', ''),
    ('aux', LENS[0] - 2.5, 36.2, 5.0, 4.0, 'pwr', ''),
    ('ldo33', LENS[0] + 4.0, 36.2, 5.0, 4.0, 'pwr', ''),
    ('ldo28', LENS[0] - 5.75, 41.6, 5.0, 4.0, 'pwr', ''),
    ('ldo12', LENS[0] + 0.75, 41.6, 5.0, 4.0, 'pwr', ''),
    ('rtc', 5.0, 40.0, 4.0, 3.5, 'ic', 'RTC'),
    ('imu', 11.0, 40.0, 3.0, 3.5, 'ic', ''),
    ('stlink', CELL_X + CELL_W / 2 - 4.75, 44.6, 9.5, 4.6, 'pads', 'ST-LINK pads'),
    ('chg+', CELL_X + CELL_W / 2 - 15.5, 44.9, 3.0, 4.0, 'pad', '+'),
    ('chg-', CELL_X + CELL_W / 2 + 12.5, 44.9, 3.0, 4.0, 'pad', '−'),
]
ASA_X = cluster.ASA_X

STYLE = {
    'ic': ('#22262b', '#0d0f11', '#e6e6e6'), 'conn': ('#c9c2a8', '#6f6a55', '#2a2a2a'),
    'cell': ('#b9bec6', '#6d727a', '#22262b'), 'pcm': ('#3d7f4f', '#1f4a2b', '#ffffff'),
    'pwr': ('#33383f', '#0d0f11', '#e6e6e6'), 'pad': ('#d9a441', '#7a5a14', '#2a2a2a'),
    'pads': ('#2f6b4f', '#d9a441', '#f3deb0'),
}
SCALE = 9.0
PAD = 7.0


def n(v):
    return f'{v:.2f}'.rstrip('0').rstrip('.')


def view(front, ox, oy, title):
    """One face of the board at offset (ox, oy). front=True mirrors x."""
    def X(x, w=0.0):
        return ox + (W - x - w if front else x)
    o = []
    add = o.append

    def text(x, y, s, size=1.4, fill='#222', anchor='middle', weight='normal'):
        add(f'<text x="{n(ox + (W - x if front else x))}" y="{n(oy + y)}" font-size="{size}" text-anchor="{anchor}" fill="{fill}" font-weight="{weight}">{s}</text>')

    def rect(x, y, w, h, style, extra=''):
        add(f'<rect x="{n(X(x, w))}" y="{n(oy + y)}" width="{n(w)}" height="{n(h)}" {style} {extra}/>')

    add(f'<text x="{n(ox + W / 2)}" y="{n(oy - 3.4)}" font-size="2.2" text-anchor="middle" font-weight="bold" fill="#222">{title}</text>')
    # Dial rims and the button above the top edge.
    for cx in (ASA_X, cluster.EXPOSURE_X):
        add(f'<circle cx="{n(X(cx))}" cy="{n(oy + cluster.DIAL_Y)}" r="{cluster.KNOB_R}" fill="#1c1c1c"/>')
    add(f'<rect x="{n(ox)}" y="{n(oy)}" width="{n(W)}" height="{n(H)}" rx="{n(R)}" fill="#2f6b4f" stroke="#17382a" stroke-width="0.2"/>')

    # Keep-outs.
    hatch = 'fill="#f2c14e" fill-opacity="0.28" stroke="#f2c14e" stroke-width="0.12" stroke-dasharray="0.7 0.5"'
    rect(W - RIGHT_KEEPOUT, 0, RIGHT_KEEPOUT, H, hatch)
    add(f'<text x="{n(X(W - RIGHT_KEEPOUT / 2))}" y="{n(oy + H * 0.72)}" font-size="1.0" text-anchor="middle" fill="#fff3c4" '
        f'transform="rotate(-90 {n(X(W - RIGHT_KEEPOUT / 2))} {n(oy + H * 0.72)})">housing radius keep-out</text>')

    # Axes the layout is composed on.
    axis = 'stroke="#9fd0b6" stroke-width="0.08" stroke-dasharray="1.2 0.8" opacity="0.7"'
    add(f'<path d="M{n(ox + 1)} {n(oy + MID_Y)} H{n(ox + W - 1)} M{n(X(LENS[0]))} {n(oy + 1)} V{n(oy + H - 1)}" {axis}/>')

    ghost = 'fill="none" stroke="#bfe3d0" stroke-width="0.12" stroke-dasharray="0.6 0.4"'
    # Dials.
    for cx in (ASA_X, cluster.EXPOSURE_X):
        if front:
            add(f'<circle cx="{n(X(cx))}" cy="{n(oy + cluster.DIAL_Y)}" r="{cluster.KNOB_R}" fill="#1c1c1c" stroke="#555" stroke-width="0.1"/>')
            rect(cx - dial.BODY_HALF_W, cluster.DIAL_Y - dial.BODY_TOP, 2 * dial.BODY_HALF_W, dial.BODY_TOP - dial.BODY_BOTTOM,
                 'fill="#c9cdd3" stroke="#555" stroke-width="0.1"')
        else:
            add(f'<circle cx="{n(X(cx))}" cy="{n(oy + cluster.DIAL_Y)}" r="{cluster.KNOB_R}" {ghost}/>')
        for _, px, py, pw, ph in dial.pads():
            rect(cx + px - pw / 2, cluster.DIAL_Y - py - ph / 2, pw, ph, 'fill="#d9a441"' if front else ghost)
        add(f'<circle cx="{n(X(cx))}" cy="{n(oy + cluster.DIAL_Y + cluster.WINDOW_R)}" r="{n(cluster.WINDOW_D / 2)}" fill="#e3cb9b" stroke="#0f2a1e" stroke-width="0.15"/>')
    shutter.switch_svg(add, front, lambda x: X(x), oy, ghost=not front)
    add(f'<circle cx="{n(X(shutter.SW_X))}" cy="{n(oy + shutter.LED_Y)}" r="{n(cluster.LED_HOLE_D / 2)}" fill="#fff6c9" stroke="#0f2a1e" stroke-width="0.15"/>')
    for fx, fy, fw, fh in shutter.fets():                      # two SOT-23 each side of the LED
        rect(fx, fy, fw, fh, 'fill="#22262b" stroke="#0d0f11" stroke-width="0.08"' if front else ghost)

    # Parts.
    for name, x, y, w, h, kind, label in PARTS:
        fill, stroke, ink = STYLE[kind]
        rect(x, y, w, h, f'fill="{fill}" stroke="{stroke}" stroke-width="0.12"' if front else ghost, 'rx="0.4"')
        if label and front:
            text(x + w / 2, y + h / 2 + 0.5, label, 1.1 if kind == 'pads' or w <= 8 else 1.5, ink, weight='bold')
    # Camera: cut-out through the board, head in it, flex to the connector.
    c = HEAD / 2 + CUTOUT_CLEAR
    rect(LENS[0] - c, LENS[1] - c, 2 * c + 2.6, 2 * c, 'fill="#f6f5f1" stroke="#0f2a1e" stroke-width="0.2"')
    rect(LENS[0] + HEAD / 2, LENS[1] - 3.0, CONNECTOR_OFFSET - HEAD / 2 + 0.6, 6.0, 'fill="#c98a2b" fill-opacity="0.8" stroke="#7a4d0c" stroke-width="0.08"')
    rect(LENS[0] - HEAD / 2, LENS[1] - HEAD / 2, HEAD, HEAD, 'fill="#1c1c1c" stroke="#000" stroke-width="0.1"')
    if front:
        add(f'<circle cx="{n(X(LENS[0]))}" cy="{n(oy + LENS[1])}" r="2.4" fill="#3a4a66" stroke="#9db4d6" stroke-width="0.25"/>')
        add(f'<circle cx="{n(X(LENS[0]))}" cy="{n(oy + LENS[1])}" r="1.0" fill="#0b0f18"/>')
        text(LENS[0], LENS[1] + c + 2.0, 'lens', 1.3, '#ffffff')
        text(LENS[0], 36.2 - 0.9, 'regulators', 1.1, '#cfe9dc')
    else:
        text(LENS[0], LENS[1] + c + 2.0, 'module back, flush', 1.2, '#ffffff')
        text(7.5, SD_EDGE_Y + 0.5, 'SD', 1.5, '#ffffff', weight='bold')
    # Card slot marker on the left edge.
    add(f'<path d="M{n(X(0))} {n(oy + SD_EDGE_Y - 5.6)} V{n(oy + SD_EDGE_Y + 5.6)}" stroke="#ffffff" stroke-width="0.5"/>')
    return '\n'.join(o)


def build():
    width, height = 2 * W + 3 * PAD, H + 2 * PAD + 14
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{n(width * SCALE)}" height="{n(height * SCALE)}" viewBox="0 0 {n(width)} {n(height)}" '
           f'font-family="Helvetica, Arial, sans-serif">',
           f'<rect width="{n(width)}" height="{n(height)}" fill="#f6f5f1"/>',
           view(False, PAD, PAD + 4, 'Back (user side)'),
           view(True, W + 2 * PAD, PAD + 4, 'Front (parts side, as seen through a clear case)')]
    y = H + PAD + 9.5
    notes = ['Third draft for mark-up. Locked: the control group, with the dials 26 mm apart and the D2MQ shutter switch between them. From the user: lens, SD slot, right-edge keep-out, bare ST-LINK pads.',
             'Composition: SD slot, lens and cell share the horizontal centre line; MCU, lens and the regulator block share the lens axis; FETs flank the LED hole; ST-LINK pads and charge pads centred under the cell.',
             'Everything else is proposed. Pending a module in hand: the cut-out, the flex path and its direction. Pending: the size of the cell\'s unfolded protection board.']
    for i, s in enumerate(notes):
        out.append(f'<text x="{n(width / 2)}" y="{n(y + i * 2.6)}" font-size="1.45" text-anchor="middle" fill="#333">{s}</text>')
    out.append('</svg>')
    return '\n'.join(out) + '\n'


def main():
    OUT.write_text(build())
    print(f'lens at ({LENS[0]:.2f}, {LENS[1]:.2f}); cell x {CELL_X:.1f}-{CELL_X + CELL_W:.1f}, y {CELL_Y:.1f}-{CELL_Y + CELL_H:.1f}; '
          f'exposure dial rim reaches x {cluster.EXPOSURE_X + cluster.KNOB_R:.1f}, keep-out starts {W - RIGHT_KEEPOUT:.1f}')


if __name__ == '__main__':
    main()
