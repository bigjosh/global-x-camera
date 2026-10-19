"""Generate the selected prototype's conceptual power/wiring diagram.

This is an electrical connection diagram, not a physical component locator.
Physical locations are in the separately sourced MB1940 assembly diagrams.
Requires Pillow; writes only docs/prototype/nucleo-assembly/power-wiring.*.
"""
import html
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/prototype/nucleo-assembly"
W, H = 1600, 1190
INK, BLUE, GREEN, RED, MUTED = "#183047", "#146a94", "#08766a", "#aa3737", "#52687a"

class Canvas:
    def __init__(self):
        self.im = Image.new("RGB", (W * 2, H * 2), "white")
        self.d = ImageDraw.Draw(self.im)
        self.svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">', '<title>Global X Camera: selected 5 V prototype power and 1.8 V NAND wiring</title>', '<rect width="100%" height="100%" fill="white"/>']

    def text(self, x, y, s, size=23, color=INK, bold=False):
        font = ImageFont.truetype(str(Path("C:/Windows/Fonts") / ("segoeuib.ttf" if bold else "segoeui.ttf")), size * 2)
        self.d.text((x*2, y*2), s, fill=color, font=font, anchor="lt")
        self.svg.append(f'<text x="{x}" y="{y+size*.84}" font-family="Segoe UI,Arial,sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}">{html.escape(s)}</text>')

    def box(self, x, y, w, h, color=BLUE, fill="#f1f7fb"):
        self.d.rounded_rectangle((x*2, y*2, (x+w)*2, (y+h)*2), radius=12, fill=fill, outline=color, width=4)
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" stroke="{color}" stroke-width="2"/>')

    def line(self, points, color=BLUE, width=4):
        self.d.line([(x*2,y*2) for x,y in points], fill=color, width=width*2)
        self.svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" stroke="{color}" stroke-width="{width}"/>')

    def cross(self,x,y):
        self.line([(x-12,y-12),(x+12,y+12)],RED)
        self.line([(x-12,y+12),(x+12,y-12)],RED)

c=Canvas()
c.text(50,35,"Selected prototype wiring",36,bold=True)
c.text(50,90,"LTC output = 5.0 V  |  NAND and its five bus GPIOs = 1.8 V",25,BLUE,True)
c.text(50,134,"Connection diagram — use the assembly guide for actual board locations.",21,MUTED)

c.box(50,205,245,150)
c.text(70,226,"4 × CR2032",27,bold=True)
c.text(70,267,"Series pack",23)
c.text(70,310,"Qualify pulse / sag",20,MUTED)
c.line([(295,280),(360,280)])
c.box(360,205,260,150)
c.text(380,227,"LTC3621 → 5.0 V",25,bold=True)
c.text(380,274,"DC1863A: JP7 = 5 V",21)
c.text(380,315,"JP1 ON for bring-up",20,MUTED)
c.line([(620,280),(700,280)])
c.box(700,205,245,150)
c.text(720,227,"JS110 (optional)",25,bold=True)
c.text(720,276,"IN+ → OUT+",23)
c.text(720,315,"5 V measurement",20,MUTED)
c.line([(945,280),(1030,280)])
c.box(1030,205,515,205)
c.text(1050,227,"NUCLEO target: CN9 pin 2",26,bold=True)
c.text(1050,272,"All CN9 source shunts REMOVED",22,RED,True)
c.text(1050,310,"CN8 USB and VIN disconnected",22)
c.text(1050,350,"Common GND: Arduino CN14 pin 7",21)

c.line([(1275,410),(1275,470)])
c.box(1030,470,515,168)
c.text(1050,493,"Keep stock downstream regulators",24,bold=True)
c.text(1050,535,"MCU main / AUX / core / 1.8 V",22)
c.text(1050,575,"Camera adapter and boot NOR",22)
c.line([(1030,547),(900,547),(900,730)],GREEN)
c.text(640,498,"CN12 pin 14: 1.8 V",24,GREEN,True)

c.box(50,440,530,198,color=MUTED,fill="#f7f8fa")
c.text(70,460,"CN10 USB → ST-LINK debugger",26,bold=True)
c.text(70,505,"Powered separately during development",21)
c.text(70,545,"Remove D2: open target → debugger feed",21,RED,True)
c.text(70,586,"Signal / sense links still cross this boundary",20,MUTED)
c.line([(580,547),(630,547)],MUTED)
c.cross(605,547)
c.text(50,661,"Remove R23 to disconnect LD1 power LED. Ethernet: see load-trimming stage.",22,RED)

c.box(50,730,690,255,color=GREEN,fill="#f0f8f5")
c.text(70,750,"Arduino signals → Alliance 1.8 V NAND",26,GREEN,True)
c.text(70,796,"D10 / CN14.3 → CS# (open-drain only)",23)
c.text(70,834,"A1 / CN4.2 → IO0       A4 / CN4.5 → IO1",23)
c.text(70,872,"D14 / CN14.9 → IO2    A5 / CN4.6 → IO3",23)
c.text(70,910,"D15 / CN14.10 → CLK; CN14.7 → GND",23)
c.text(70,950,"CS#, IO2 and IO3: each 10 kΩ to NAND 1.8 V",20,GREEN)

c.box(800,730,745,255,color=GREEN,fill="#f0f8f5")
c.text(820,750,"1.8 V conversion and distribution",26,GREEN,True)
c.text(820,796,"REMOVE SB24, R88 and R89 first",24,RED,True)
c.text(820,832,"CN12.14 → CN3.10 → CN14.8 / AREF",24)
c.text(820,867,"CN14.8 → NAND pin 8 / VCC",24)
c.text(820,902,"R125 unfitted; label AREF 1.8 V",22,RED,True)
c.text(820,934,"100 nF + ~1 µF at NAND VCC / GND",21)
c.text(820,964,"CN12.13 is NOT ground. Keep R104 fitted.",19,RED)

c.text(50,1030,"Before power: verify supply isolation and 1.8 V wiring with a meter.",24,bold=True)
c.text(50,1074,"This rework does not implement NAND saving, RUN/HOLD or final shutdown firmware.",22,MUTED)
c.text(50,1116,"Main battery OFF current and debugger backfeed still require separate qualification.",22,MUTED)
OUT.mkdir(parents=True,exist_ok=True)
c.im.save(OUT/"power-wiring.png")
(OUT/"power-wiring.svg").write_text("\n".join(c.svg+["</svg>"]),encoding="utf-8")
print(OUT/"power-wiring.png")
