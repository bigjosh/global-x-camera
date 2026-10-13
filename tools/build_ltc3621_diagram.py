"""Rebuild the LTC3621 pushbutton connection diagram, as vector SVG and PNG.

Run with Python and Pillow installed. This script writes only the two named
diagram assets; it does not modify the KiCad design or the earlier power latch.
The illustrated L/C values are starting values, not qualified component MPNs.
"""

import html
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "power"
W, H, SCALE = 1600, 1560, 2
INK = "#172c43"
POWER = "#175a83"
CONTROL = "#127569"
MUTED = "#586777"
AMBER = "#875b0d"


class Drawing:
    """Emit the same drawing primitives into SVG and a high resolution PNG."""

    def __init__(self):
        self.image = Image.new("RGB", (W * SCALE, H * SCALE), "white")
        self.raster = ImageDraw.Draw(self.image)
        self.svg = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
            "<title>LTC3621 fixed 3.3 V regulator with a pushbutton and GPIO hold diode</title>",
            "<desc>Two panels connected by named RUN, BAT+ and GND nets. Power-stage pins use the MS8E package numbering. MODE/SYNC is connected to INTVCC for Burst Mode. A normally open button and resistor divider start RUN; a BAS116 diode holds RUN from a 3.3 V GPIO. STM32N6 sequencing and USB source control are not implemented in this diagram.</desc>",
            '<rect width="100%" height="100%" fill="white"/>',
        ]

    def line(self, points, color=INK, width=3):
        self.raster.line([(x * SCALE, y * SCALE) for x, y in points], fill=color, width=width * SCALE)
        self.svg.append(
            f'<polyline points="{" ".join(f"{x},{y}" for x, y in points)}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"/>'
        )

    def box(self, x, y, width, height, fill="#f3f7fb", color=INK):
        self.raster.rectangle((x * SCALE, y * SCALE, (x + width) * SCALE, (y + height) * SCALE), fill=fill, outline=color, width=2 * SCALE)
        self.svg.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="{fill}" stroke="{color}" stroke-width="2"/>')

    def text(self, x, y, value, size=21, color=INK, bold=False, anchor="left"):
        font_names = [
            Path("C:/Windows/Fonts") / ("segoeuib.ttf" if bold else "segoeui.ttf"),
            Path("/usr/share/fonts/truetype/dejavu") / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),
        ]
        font_path = next((p for p in font_names if p.exists()), None)
        if font_path is None:
            raise RuntimeError("Install Segoe UI or DejaVu Sans to reproduce the PNG.")
        font = ImageFont.truetype(str(font_path), size * SCALE)
        self.raster.text((x * SCALE, y * SCALE), value, font=font, fill=color, anchor={"left": "lt", "middle": "mt", "right": "rt"}[anchor])
        self.svg.append(
            f'<text x="{x}" y="{y + size * .82}" font-family="Segoe UI,DejaVu Sans,Arial,sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" text-anchor="{{}}" fill="{color}">{html.escape(value)}</text>'.format({"left": "start", "middle": "middle", "right": "end"}[anchor])
        )

    def dot(self, x, y, color=INK, radius=5):
        self.raster.ellipse(((x - radius) * SCALE, (y - radius) * SCALE, (x + radius) * SCALE, (y + radius) * SCALE), fill=color)
        self.svg.append(f'<circle cx="{x}" cy="{y}" r="{radius}" fill="{color}"/>')

    def ground(self, x, y):
        self.line([(x - 16, y), (x + 16, y)])
        self.line([(x - 11, y + 7), (x + 11, y + 7)])
        self.line([(x - 5, y + 14), (x + 5, y + 14)])

    def capacitor(self, x, y1, y2, ref, value):
        mid = (y1 + y2) / 2
        self.line([(x, y1), (x, mid - 6)], POWER)
        self.line([(x - 20, mid - 6), (x + 20, mid - 6)], POWER)
        self.line([(x - 20, mid + 6), (x + 20, mid + 6)], POWER)
        self.line([(x, mid + 6), (x, y2)], POWER)
        self.text(x + 32, mid - 24, ref, 20, POWER, True)
        self.text(x + 32, mid + 6, value, 20, POWER)

    def resistor_h(self, x1, x2, y, ref, value):
        mid = (x1 + x2) / 2
        self.line([(x1, y), (mid - 42, y)], CONTROL)
        self.box(mid - 42, y - 13, 84, 26, "white", CONTROL)
        self.line([(mid + 42, y), (x2, y)], CONTROL)
        self.text(mid, y - 75, ref, 21, CONTROL, True, "middle")
        self.text(mid, y - 44, value, 21, CONTROL, False, "middle")

    def resistor_v(self, x, y1, y2, ref, value):
        mid = (y1 + y2) / 2
        self.line([(x, y1), (x, mid - 30)], CONTROL)
        self.box(x - 12, mid - 30, 24, 60, "white", CONTROL)
        self.line([(x, mid + 30), (x, y2)], CONTROL)
        self.text(x + 30, mid - 25, ref, 21, CONTROL, True)
        self.text(x + 30, mid + 7, value, 21, CONTROL)

    def inductor(self, x1, x2, y):
        points = []
        for i in range(4):
            for j in range(21):
                x = x1 + (x2 - x1) * (i + j / 20) / 4
                points.append((x, y - 22 * math.sin(math.pi * j / 20)))
        self.line(points, POWER, 3)

    def diode(self, x, y):
        # Standard diode outline: anode at left, cathode bar at right.
        points = [(x - 18, y - 18), (x - 18, y + 18), (x + 18, y), (x - 18, y - 18)]
        self.line(points, CONTROL, 3)
        self.line([(x + 18, y - 22), (x + 18, y + 22)], CONTROL, 3)

    def save(self):
        OUT.mkdir(parents=True, exist_ok=True)
        svg_path = OUT / "ltc3621-pushbutton.svg"
        png_path = OUT / "ltc3621-pushbutton.png"
        svg_path.write_text("\n".join(self.svg + ["</svg>"]) + "\n", encoding="utf-8")
        self.image.save(png_path)
        print(svg_path)
        print(png_path)


def main():
    d = Drawing()
    d.text(55, 30, "LTC3621 pushbutton power latch", 35, bold=True)
    d.text(55, 80, "8–13.2 V input  |  Fixed 3.3 V output  |  250 mA illustrative load  |  Common ground", 22, MUTED)

    # Power panel. Pin positions are schematic choices; numbers are MS8E pins.
    d.box(40, 135, 1520, 590, "#fbfdff", "#d1dce5")
    d.text(65, 155, "1  POWER STAGE", 23, POWER, True)
    d.text(600, 195, "U_PWR  LTC3621EMS8E-3.3#PBF", 23, bold=True)
    d.box(610, 250, 360, 370)
    d.text(790, 269, "MS8E + exposed pad", 18, MUTED, anchor="middle")
    for y, label in [(310, "2  VIN"), (390, "3  RUN"), (550, "4  PGOOD")]:
        d.text(630, y - 10, label, 21, POWER if y == 310 else INK, True)
    for y, label in [(310, "SW  1"), (390, "FB  5"), (470, "INTVCC  6"), (550, "MODE/SYNC  7")]:
        d.text(950, y - 10, label, 21, POWER if y == 310 else INK, True, "right")
    d.text(715, 592, "SGND  8", 19, bold=True, anchor="middle")
    d.text(865, 592, "GND  EP9", 19, bold=True, anchor="middle")

    d.text(90, 255, "BAT+", 23, POWER, True)
    d.text(90, 282, "8–13.2 V", 19, POWER)
    d.line([(90, 310), (610, 310)], POWER, 4)
    d.dot(310, 310, POWER)
    d.capacitor(310, 310, 470, "C_IN", "10 µF · 25 V")
    d.ground(310, 470)

    d.line([(500, 390), (610, 390)], CONTROL)
    d.text(525, 343, "RUN", 22, CONTROL, True, "right")
    d.text(525, 368, "from panel 2", 18, MUTED, anchor="right")
    d.line([(580, 550), (610, 550)])
    d.line([(572, 542), (588, 558)])
    d.line([(572, 558), (588, 542)])
    d.text(555, 539, "NC", 18, MUTED, anchor="right")
    for x in (715, 865):
        d.line([(x, 620), (x, 660)])
        d.ground(x, 660)

    d.line([(970, 310), (1040, 310)], POWER, 4)
    d.inductor(1040, 1152, 310)
    d.text(1096, 239, "L_PWR", 21, POWER, True, "middle")
    d.text(1096, 267, "6.8 µH", 21, POWER, anchor="middle")
    d.line([(1152, 310), (1460, 310)], POWER, 4)
    d.text(1450, 253, "3V3_MAIN", 23, POWER, True, "right")
    d.text(1450, 282, "3.3 V", 19, POWER, anchor="right")
    d.dot(1190, 310, POWER)
    d.line([(1190, 310), (1190, 390), (970, 390)], POWER)
    d.dot(1270, 310, POWER)
    d.capacitor(1270, 310, 430, "C_OUT", "22 µF · 10 V")
    d.ground(1270, 430)
    d.line([(1460, 310), (1460, 480)], POWER)
    d.box(1370, 480, 160, 118, "#f1f8f6", CONTROL)
    d.text(1450, 498, "Generic MCU", 21, bold=True, anchor="middle")
    d.text(1450, 535, "250 mA", 23, CONTROL, True, "middle")
    d.text(1450, 568, "design point", 18, MUTED, anchor="middle")
    d.line([(1460, 598), (1460, 660)])
    d.ground(1460, 660)

    # MODE and the capacitor share the INTVCC node. No crossings are used.
    d.line([(970, 470), (1210, 470)], POWER)
    d.dot(1090, 470, POWER)
    d.line([(1090, 470), (1090, 550), (970, 550)], POWER)
    d.capacitor(1210, 470, 650, "C_INT", "1 µF · 10 V")
    d.ground(1210, 650)
    d.text(1010, 586, "MODE → INTVCC", 17, POWER)
    d.text(1010, 611, "Burst Mode", 18, POWER, True)
    d.text(75, 670, "BAT− = GND = MCU ground", 22, bold=True)

    # Control panel: corresponding labels connect electrically to panel 1.
    d.box(40, 750, 1520, 490, "#fbfefd", "#cfdfd9")
    d.text(65, 770, "2  BUTTON START + GPIO HOLD", 23, CONTROL, True)
    d.text(90, 870, "BAT+", 23, POWER, True)
    d.line([(90, 930), (300, 930)], CONTROL)
    d.dot(300, 930, CONTROL, 4)
    d.line([(300, 930), (360, 903)], CONTROL)
    d.dot(375, 930, CONTROL, 4)
    d.line([(375, 930), (440, 930)], CONTROL)
    d.text(300, 816, "SW_START", 21, CONTROL, True, "middle")
    d.text(300, 846, "KMR232NG ULC LFS", 20, anchor="middle")
    d.text(300, 875, "Top-actuated · normally open", 18, MUTED, anchor="middle")
    d.resistor_h(440, 710, 930, "R_START", "330 kΩ · 1%")
    d.line([(710, 930), (1360, 930)], CONTROL)
    d.text(1390, 917, "RUN", 23, CONTROL, True)
    d.text(1388, 951, "to pin 3", 18, MUTED)
    d.dot(980, 930, CONTROL)
    d.resistor_v(980, 930, 1170, "R_OFF", "100 kΩ · 1%")
    d.ground(980, 1170)

    d.text(90, 1000, "GPIO HOLD", 23, CONTROL, True)
    d.text(90, 1033, "3.3 V domain", 19, CONTROL)
    d.line([(90, 1080), (562, 1080)], CONTROL)
    d.dot(280, 1080, CONTROL)
    d.resistor_v(280, 1080, 1200, "R_GPIO", "100 kΩ · 1%")
    d.ground(280, 1200)
    d.diode(580, 1080)
    d.line([(598, 1080), (820, 1080), (820, 930)], CONTROL)
    d.dot(820, 930, CONTROL)
    d.text(590, 1001, "D_HOLD", 21, CONTROL, True, "middle")
    d.text(590, 1032, "BAS116,235", 21, anchor="middle")
    d.text(555, 1108, "A · pin 1", 18, CONTROL, anchor="right")
    d.text(610, 1108, "K · pin 3", 18, CONTROL)
    d.text(590, 1145, "Pin 2: NC", 18, MUTED, anchor="middle")
    d.text(1170, 1015, "HOLD high: stays on", 20, CONTROL, True)
    d.text(1170, 1050, "HOLD low + button open:", 19)
    d.text(1170, 1080, "regulator shuts down", 19)
    d.text(1170, 1130, "A held button overrides OFF.", 18, MUTED)

    d.box(40, 1265, 1520, 235, "#fff9eb", "#c5a561")
    d.text(65, 1283, "INTEGRATION BOUNDARY", 22, AMBER, True)
    d.text(65, 1321, "N6 already controls internal-SMPS shutdown and PWR_ON. External AUX switching/discharge is not shown.", 20)
    d.text(65, 1353, "Main supplies must remain valid until every AUX rail is below 0.6 V; qualify the external delay or hold-up.", 20)
    d.text(65, 1385, "Direct GPIO HOLD is only the latch core. A dedicated sequencer IC is optional; USB source control is still required.", 20)
    d.text(65, 1417, "RUN must not exceed VIN in any supply state. Take over HOLD before the start button is released.", 20)
    d.text(65, 1449, "L/C values are starting values; qualify exact MPNs, derating, startup, load response and current capability.", 20)
    d.text(55, 1520, "Electrical connection diagram, not a package view. Filled dots join branches; matching RUN, BAT+ and GND labels join nets.", 19, MUTED)
    d.save()


if __name__ == "__main__":
    main()
