"""Draw the recovered camera power tree as SVG and PNG.

This is a documented connectivity view, not a proposed schematic or simulation.
The battery-chain topology comes from spec.md; rail wiring comes from the
reconstructed connectivity JSON. No KiCad files are changed.
"""
import hashlib
import html
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/power'
W, H, SCALE = 2400, 2240, 2
INK, MUTED = '#172c43', '#5d6e80'
BLUE, TEAL, PURPLE, ORANGE = '#17648d', '#12796e', '#714c9e', '#a36214'
RULE = '#d4e0e9'


class Drawing:
    def __init__(self):
        self.image = Image.new('RGB', (W*SCALE, H*SCALE), 'white')
        self.draw = ImageDraw.Draw(self.image)
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
            '<title>Global X Camera: recovered power supply tree</title>',
            '<desc>Battery and USB-C input paths, the shared 3.3 V supply, external 1.8 V buck, internal MCU core supply, camera rails, memory, RTC and accelerometer. The proposed LTC3621 and AON/AUX split are explicitly not implemented in this recovered tree.</desc>',
            '<rect width="100%" height="100%" fill="white"/>',
        ]
        self.text_bounds = []

    def text(self, x, y, value, size=26, color=INK, bold=False, align='left'):
        font = ImageFont.truetype('C:/Windows/Fonts/' + ('segoeuib.ttf' if bold else 'segoeui.ttf'), size*SCALE)
        anchor = {'left':'lt','center':'mt','right':'rt'}[align]
        self.draw.text((x*SCALE,y*SCALE),value,font=font,fill=color,anchor=anchor)
        self.parts.append(f'<text x="{x}" y="{y+size*.82}" font-family="Segoe UI,Arial,sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" text-anchor="{dict(left="start",center="middle",right="end")[align]}" fill="{color}">{html.escape(value)}</text>')
        width = self.draw.textlength(value,font=font)/SCALE
        left = x if align=='left' else x-width/2 if align=='center' else x-width
        self.text_bounds.append((value,left,y,width,size))

    def box(self, x, y, w, h, fill='#f4f8fb', border=RULE, width=2):
        self.draw.rounded_rectangle((x*SCALE,y*SCALE,(x+w)*SCALE,(y+h)*SCALE),radius=8*SCALE,fill=fill,outline=border,width=width*SCALE)
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="{border}" stroke-width="{width}"/>')

    def line(self, points, color=BLUE, width=4, arrow=False):
        self.draw.line([(x*SCALE,y*SCALE) for x,y in points],fill=color,width=width*SCALE)
        self.parts.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" stroke="{color}" stroke-width="{width}" fill="none" stroke-linejoin="round"/>')
        if arrow:
            x,y=points[-1]; px,py=points[-2]
            if x>px: triangle=[(x,y),(x-13,y-7),(x-13,y+7)]
            elif x<px: triangle=[(x,y),(x+13,y-7),(x+13,y+7)]
            elif y>py: triangle=[(x,y),(x-7,y-13),(x+7,y-13)]
            else: triangle=[(x,y),(x-7,y+13),(x+7,y+13)]
            self.draw.polygon([(a*SCALE,b*SCALE) for a,b in triangle],fill=color)
            self.parts.append(f'<polygon points="{" ".join(f"{a},{b}" for a,b in triangle)}" fill="{color}"/>')

    def dot(self,x,y,color=BLUE):
        self.draw.ellipse(((x-6)*SCALE,(y-6)*SCALE,(x+6)*SCALE,(y+6)*SCALE),fill=color)
        self.parts.append(f'<circle cx="{x}" cy="{y}" r="6" fill="{color}"/>')

    def card(self,x,y,w,h,title,lines,color=BLUE,fill='#ffffff',title_size=28,body_size=25):
        self.box(x,y,w,h,fill,color)
        self.text(x+18,y+15,title,title_size,color,True)
        for i,value in enumerate(lines):
            self.text(x+18,y+54+i*31,value,body_size)

    def branch(self,xbus,y,xcard,color=BLUE):
        self.dot(xbus,y,color)
        self.line([(xbus,y),(xcard,y)],color,arrow=True)


def build():
    d=Drawing()
    d.text(45,30,'Global X Camera  |  Power supply tree',45,bold=True)
    d.text(45,91,'Recovered wiring • September 7, 2026 • Nominal voltages • Repeated rail labels connect the panels',28,MUTED)

    # Sources and main conversion.
    d.box(40,145,2320,610,'#f8fbfd')
    d.text(65,164,'1  BATTERIES AND USB-C',29,BLUE,True)
    d.card(80,220,360,130,'Four CR2032 cells',['Series stack: 8–13.2 V','External battery assembly'],title_size=30)
    d.card(520,220,380,130,'Battery latch',['Q1 + Q3: AO3401A','Q2 controls the gate latch'],title_size=30)
    d.line([(440,285),(520,285)],arrow=True)
    d.text(480,247,'BAT+',23,BLUE,align='center')
    d.line([(900,285),(935,285),(935,410),(970,410)],arrow=True)

    d.card(520,370,380,90,'U8 RTC backup input',['VBACKUP ← BAT_CELL1_TAP'],color=PURPLE,title_size=26,body_size=23)
    d.line([(250,350),(250,415),(520,415)],PURPLE,arrow=True)
    d.text(275,379,'Lowest-cell tap ≈3 V',23,PURPLE)

    d.card(80,495,360,140,'USB-C • J1',['USB_VBUS: nominal 5 V','Also feeds D1 ESD pin 5'],title_size=30)
    d.card(520,495,380,125,'D2 • SS34 diode',['5 V minus diode drop','USB → SYS_IN'],title_size=29)
    d.line([(440,557),(520,557)],arrow=True)
    d.line([(900,557),(935,557),(935,410)],arrow=False)
    d.dot(935,410)
    d.card(970,335,300,150,'SYS_IN',['Battery through latch','or USB through D2','No priority controller'],title_size=30,body_size=24)
    d.line([(1270,410),(1390,410)],arrow=True)
    d.card(1390,335,430,150,'U2 • Main buck',['TPS62132RGTR + L1 2.2 µH','SYS_IN → regulated 3.3 V','EN tied to SYS_IN'],title_size=30,body_size=25)
    d.line([(1820,410),(1920,410)],arrow=True)
    d.card(1920,335,370,150,'3V3 • Main 3.3 V',['Feeds panel 2 below','Available from battery','or USB input'],title_size=29,body_size=25)

    d.dot(470,557)
    d.line([(470,557),(470,695),(1040,695)],arrow=True)
    d.card(1040,645,490,100,'U4 • TLV70033DDCT LDO',['USB_VBUS → 3V3_USB, fixed 3.3 V'],title_size=28,body_size=24)
    d.line([(1530,695),(1630,695)],arrow=True)
    d.card(1630,645,660,100,'STM32 USB PHY supply',['3V3_USB → U1 VDD33USB (pin A4)'],title_size=28,body_size=26)

    # Main 3.3 V consumers and conversion branches.
    d.box(40,785,1120,1150,'#f8fbfd')
    d.text(65,805,'2  MAIN 3.3 V DISTRIBUTION',29,BLUE,True)
    d.text(85,849,'3V3 from U2',25,BLUE,True)
    d.line([(150,887),(150,1820)])
    d.card(260,895,840,150,'STM32N657 • main 3.3 V pins',[
        'U1 VDD + VDDIO2/3 + MCU VBAT',
        'Internal backup regulator → V08CAP / C19 bypass',
        'V08CAP is a separate internal node; not the core SMPS rail.'
    ],title_size=29,body_size=24)
    d.branch(150,970,260)
    d.card(260,1065,840,125,'Boot and image storage',[
        'U5 W25Q128JVPIQ • boot NOR • VCC = 3.3 V',
        'U6 MX30LF2G18AC-TI • NAND • VCC/VCC1 = 3.3 V'
    ],title_size=29)
    d.branch(150,1127,260)
    d.card(260,1210,840,105,'U8 • RV-3028 real-time clock',[
        'VDD = 3.3 V; separate single-cell VBACKUP shown in panel 1'
    ],title_size=29,body_size=24)
    d.branch(150,1262,260)
    d.card(260,1335,840,120,'Indicator and debug reference',[
        '3V3 → R12 1.5 kΩ → LED1 → MCU PC0 current sink',
        'J2 pin 1 = 3V3 / VTref • debug voltage sense, not a source'
    ],title_size=29,body_size=24)
    d.branch(150,1395,260)
    d.card(260,1490,395,150,'U9 • Camera analog LDO',[
        'TLV70028DDCR',
        '3.3 V → 2.8 V',
        'EN: CAM_AVDD_EN'
    ],title_size=26,body_size=24)
    d.branch(150,1560,260)
    d.line([(655,1560),(770,1560)],ORANGE,arrow=True)
    d.text(712,1520,'2.8 V',25,ORANGE,True,align='center')
    d.card(770,1490,330,150,'CAM1 • Analog',[
        'CAM_VANA_2V8',
        'Via J3 pin 1',
        'External camera module'
    ],color=ORANGE,title_size=27,body_size=23)
    d.card(260,1660,395,155,'U7 • External 1.8 V buck',[
        'TPS62825DMQR',
        'L2 0.47 µH; EN tied 3V3',
        '3.3 V → 1.8 V'
    ],title_size=26,body_size=24)
    d.branch(150,1737,260)
    d.line([(655,1737),(770,1737)],TEAL,arrow=True)
    d.text(712,1697,'1.8 V',25,TEAL,True,align='center')
    d.card(770,1660,330,155,'1V8 • External 1.8 V',[
        'Feeds panel 3',
        'Shared AON + AUX',
        'in recovered wiring'
    ],color=TEAL,title_size=26,body_size=24)
    d.text(65,1862,'Local bypass capacitors and pull-up networks are grouped with their rails.',23,MUTED)

    # 1.8 V inputs/consumers and the derived core, camera and switched rail.
    d.box(1200,785,1160,1150,'#f6fbf9')
    d.text(1225,805,'3  EXTERNAL 1.8 V DISTRIBUTION',29,TEAL,True)
    d.text(1245,849,'1V8 from U7',25,TEAL,True)
    d.line([(1310,887),(1310,1820)],TEAL)
    d.card(1420,895,890,115,'STM32 main 1.8 V • VDDA18AON',[
        'VDDA18PLL is also connected to this same 1V8 net.',
        'No separate AON supply branch exists in the recovered wiring.'
    ],color=ORANGE,fill='#fffaf0',title_size=29,body_size=24)
    d.branch(1310,952,1420,TEAL)
    d.card(1420,1030,890,140,'STM32 1.8 V analog and I/O supplies',[
        'VDDA18ADC / VREF+ • VDDA18CSI • VDDA18USB',
        'VDDIO4 + VDDIO5',
        'These are external supply inputs to blocks inside U1.'
    ],color=TEAL,title_size=29,body_size=24)
    d.branch(1310,1100,1420,TEAL)
    d.card(1420,1190,400,170,'U1 internal SMPS + L3',[
        'IN: VDDSMPS / VDDA18PMU',
        '1.8 V input; external L3 = 1 µH',
        'Converter is inside STM32',
    ],color=TEAL,title_size=27,body_size=23)
    d.branch(1310,1275,1420,TEAL)
    d.line([(1820,1275),(1970,1275)],PURPLE,arrow=True)
    d.text(1895,1236,'~0.81 V',25,PURPLE,True,align='center')
    d.card(1970,1190,340,170,'STM32 core supply',[
        'VCORE_0V81',
        'VDDCORE + VDDCSI',
        '~0.81 / ~0.9 V by VOS'
    ],color=PURPLE,title_size=26,body_size=23)
    d.card(1420,1380,890,105,'CAM1 • Camera I/O supply',[
        '1V8 → J3 pin 5 → camera module VDDIO = 1.8 V'
    ],color=TEAL,title_size=29,body_size=25)
    d.branch(1310,1432,1420,TEAL)
    d.card(1420,1510,400,150,'U10 • Camera core LDO',[
        'NCP115AMX120TCG',
        '1.8 V → 1.2 V',
        'EN tied to 1V8'
    ],color=TEAL,title_size=27,body_size=24)
    d.branch(1310,1580,1420,TEAL)
    d.line([(1820,1580),(1970,1580)],PURPLE,arrow=True)
    d.text(1895,1540,'1.2 V',25,PURPLE,True,align='center')
    d.card(1970,1510,340,150,'CAM1 • Camera core',[
        'CAM_VCORE_1V2',
        'Via J3 pin 4',
        'External camera module'
    ],color=PURPLE,title_size=26,body_size=23)
    d.card(1420,1680,400,155,'U12 • Load switch',[
        'TPS22918DBVT',
        '1.8 V in → switched 1.8 V',
        'ON: ACCEL_PWR_EN'
    ],color=TEAL,title_size=28,body_size=24)
    d.branch(1310,1750,1420,TEAL)
    d.line([(1820,1750),(1970,1750)],TEAL,arrow=True)
    d.text(1895,1710,'1.8 V',25,TEAL,True,align='center')
    d.card(1970,1680,340,155,'U11 • Accelerometer',[
        'LIS2DW12TR',
        'ACCEL_1V8_SW',
        'VDD + VDDIO + CS'
    ],color=TEAL,title_size=26,body_size=24)
    d.text(1225,1862,'The internal SMPS powers the STM32 core / CSI receiver, not CAM1.',23,MUTED)

    d.box(40,1960,2320,175,'#fff9eb','#c5a561')
    d.text(65,1978,'PLANNED CHANGES • NOT APPLIED TO THIS TREE',29,ORANGE,True)
    d.text(65,2024,'The LTC3621 proposal changes the battery / main-converter path. USB source selection still needs a complete circuit.',28)
    d.text(65,2070,'Split shared 1V8 into main AON and switched AUX; keep main rails valid through auxiliary shutdown.',28)
    d.text(45,2160,'All grounds are common. Arrows show intended power flow; they do not guarantee reverse-current blocking or source priority.',24,MUTED)
    d.text(45,2197,'Battery assembly comes from spec.md. Remaining paths follow the recovered connectivity. Full pin and source details: power-tree.md.',24,MUTED)

    OUT.mkdir(parents=True,exist_ok=True)
    svg_path=OUT/'power-tree.svg'
    svg_path.write_text('\n'.join(d.parts+['</svg>'])+'\n',encoding='utf-8')
    d.image.save(OUT/'power-tree.png')
    overflow=[t for t in d.text_bounds if t[1]<0 or t[1]+t[3]>W or t[2]+t[4]>H]
    assert not overflow, overflow
    record={
        'diagram':'power-tree.svg', 'basis':'Recovered wiring; planned changes not implemented',
        'connectivity_sha256':hashlib.sha256((ROOT/'hardware/reconstruction/schematic-connectivity.json').read_bytes()).hexdigest(),
        'source_spec_sha256':hashlib.sha256((ROOT/'spec.md').read_bytes()).hexdigest(),
        'svg_sha256':hashlib.sha256(svg_path.read_bytes()).hexdigest(),
        'canvas':[W,H], 'png_pixels':list(d.image.size),
        'text_outside_canvas':overflow,
    }
    (OUT/'power-tree-validation.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(record,indent=2))


if __name__=='__main__':
    build()
