"""Render the November 8 selected SPDT LiPo latch as a PNG/SVG wiring figure.

No instruments are accessed. Requires Pillow; labels use Windows Segoe UI.
"""
from pathlib import Path
import html
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/power'
W, H, SCALE = 1800, 1260, 2
INK, POWER, CTRL, GND, MUTED = '#1c3044', '#b13b35', '#136b9b', '#526474', '#5d7080'

class Drawing:
    def __init__(self):
        self.im = Image.new('RGB', (W*SCALE,H*SCALE), 'white')
        self.d = ImageDraw.Draw(self.im)
        self.svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
                    '<title>SPDT capacitor trigger and PD7 LiPo power-hold wiring</title>',
                    '<rect width="100%" height="100%" fill="white"/>']
    def text(self,x,y,s,size=22,color=INK,bold=False):
        font=ImageFont.truetype('C:/Windows/Fonts/'+('segoeuib.ttf' if bold else 'segoeui.ttf'),size*SCALE)
        self.d.text((x*SCALE,y*SCALE),s,font=font,fill=color,anchor='lt')
        self.svg.append(f'<text x="{x}" y="{y+size*.84}" font-family="Segoe UI,Arial,sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}">{html.escape(s)}</text>')
    def line(self,pts,color=CTRL,width=3):
        self.d.line([(x*SCALE,y*SCALE) for x,y in pts],fill=color,width=width*SCALE)
        self.svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in pts)}" fill="none" stroke="{color}" stroke-width="{width}"/>')
    def rect(self,x,y,w,h,fill='#f4f8fb',color=CTRL):
        self.d.rectangle((x*SCALE,y*SCALE,(x+w)*SCALE,(y+h)*SCALE),fill=fill,outline=color,width=2*SCALE)
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{color}" stroke-width="2"/>')
    def dot(self,x,y,color=CTRL,r=5):
        self.d.ellipse(((x-r)*SCALE,(y-r)*SCALE,(x+r)*SCALE,(y+r)*SCALE),fill=color)
        self.svg.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}"/>')
    def resistor_h(self,x1,x2,y,label,color=CTRL):
        mid=(x1+x2)/2
        self.line([(x1,y),(mid-40,y)],color)
        self.rect(mid-40,y-12,80,24,'white',color)
        self.line([(mid+40,y),(x2,y)],color)
        self.text(mid-75,y-47,label,21,color,True)
    def ground(self,x,y):
        self.line([(x,y),(x,y+12)],GND)
        for dy,half in [(12,16),(20,10),(28,4)]:self.line([(x-half,y+dy),(x+half,y+dy)],GND,2)
    def capacitor_h(self,x1,x2,y,label):
        mid=(x1+x2)/2
        self.line([(x1,y),(mid-6,y)])
        self.line([(mid+6,y),(x2,y)])
        self.line([(mid-6,y-18),(mid-6,y+18)])
        self.line([(mid+6,y-18),(mid+6,y+18)])
        self.text(mid-55,y+22,label,21,CTRL,True)
    def resistor_v(self,x,y1,y2):
        mid=(y1+y2)/2
        self.line([(x,y1),(x,mid-32)])
        self.rect(x-12,mid-32,24,64,'white',CTRL)
        self.line([(x,mid+32),(x,y2)])
    def contact(self,x,y):
        r=7
        self.d.ellipse(((x-r)*SCALE,(y-r)*SCALE,(x+r)*SCALE,(y+r)*SCALE),fill='white',outline=CTRL,width=3*SCALE)
        self.svg.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="white" stroke="{CTRL}" stroke-width="3"/>')

c=Drawing()
c.text(45,30,'LiPo shutter / power-hold latch',38,bold=True)
c.text(45,84,'Selected SPDT prototype wiring — November 8  |  Arduino D9 / PD7 HOLD',25,CTRL,True)
c.text(45,125,'First-test values. Minimum press, cold-start takeover and actual power-off timing still need measurement.',21,MUTED)

# All positive battery current, including the latch, passes through the Joulescope.
c.text(45,205,'1S LiPo +',24,POWER,True)
c.line([(45,250),(215,250)],POWER,4)
c.rect(215,205,220,90,'#fff5f3',POWER)
c.text(238,221,'JS110',25,POWER,True)
c.text(238,261,'IN+             OUT+',19,POWER)
c.line([(435,250),(690,250)],POWER,4)
c.dot(490,250,POWER)
c.text(472,205,'VBAT',22,POWER,True)
c.rect(690,200,240,140,'#fff5f3',POWER)
c.text(727,215,'Q1  AO3401',25,POWER,True)
c.text(748,251,'P-channel',22,POWER)
c.text(788,302,'1 G',20,POWER,True)
c.text(644,255,'2 S',19,POWER)
c.text(941,255,'3 D',19,POWER)
c.line([(930,250),(1030,250)],POWER,4)
c.resistor_h(1030,1330,250,'R0  2.2 ohm',POWER)
c.line([(1330,250),(1410,250)],POWER,4)
c.rect(1410,205,345,90,'#fff5f3',POWER)
c.text(1430,220,'CN5 pin 5  /  5V',26,POWER,True)
c.text(1430,260,'Battery voltage here, not 5 V',19,POWER)
c.text(1047,295,'Existing pulse-rated resistor',19,MUTED)

# Q1 gate-source pull-up. C2 is intentionally omitted in this selected circuit.
c.line([(490,250),(490,400)])
c.line([(810,340),(810,570)])
c.resistor_h(490,810,400,'R1  100 kohm')
c.dot(810,400)
c.text(840,380,'Gate pull-up / OFF bias',21,MUTED)

# Small control MOSFET represented by explicitly labelled terminals.
c.rect(690,570,240,170)
c.text(788,583,'3 D',20,CTRL,True)
c.text(730,617,'Q2  AO3400',24,CTRL,True)
c.text(747,658,'N-channel',21,CTRL)
c.text(697,648,'1 G',19,CTRL,True)
c.text(788,708,'2 S',19,CTRL,True)
c.line([(810,740),(810,790)],GND)
c.ground(810,790)

# SPDT: common is the capacitor top, never Q1 gate. Shown released / NC.
c.text(45,450,'SW1  momentary SPDT',24,CTRL,True)
c.text(45,484,'Break-before-make; shown RELEASED',19,MUTED)
c.line([(810,495),(550,495),(550,550)])
c.dot(810,495)
c.line([(300,550),(220,550),(220,610)])
c.contact(300,550);c.contact(550,550)
c.line([(420,630),(306,554)],CTRL,4)
c.dot(420,630)
c.text(269,516,'NC',21,CTRL,True)
c.text(564,532,'NO',21,CTRL,True)
c.text(440,620,'COM',21,CTRL,True)
c.text(60,574,'Released: NC',20,CTRL)
c.text(530,583,'Pressed: NO',19,CTRL)

# Reset resistor only in NC branch; trigger capacitor only at common.
c.resistor_v(220,610,710)
c.text(58,631,'R5  1 kohm',22,CTRL,True)
c.ground(220,710)
c.line([(420,630),(420,720)])
c.line([(398,720),(442,720)])
c.line([(398,735),(442,735)])
c.line([(420,735),(420,790)],GND)
c.ground(420,790)
c.text(450,699,'C3  2.2 uF',22,CTRL,True)
c.text(450,739,'X7R, 10–16 V',19,MUTED)
c.text(45,836,'C3 resets to zero through R5 when released.',21,MUTED)

# GPIO drives Q2 directly through R4; only R2 sets its default OFF state.
c.text(45,883,'GPIO HOLD: Arduino D9 / PD7',24,CTRL,True)
c.text(45,918,'CN14 pin 2',21,CTRL)
c.line([(65,985),(150,985)])
c.resistor_h(150,380,985,'R4  1 kohm')
c.line([(380,985),(620,985),(620,650),(690,650)])
c.line([(620,850),(745,850)])
c.dot(620,850)
c.resistor_v(745,850,960)
c.ground(745,960)
c.text(780,866,'R2',22,CTRL,True)
c.text(780,904,'100 kohm',21,CTRL,True)
c.text(45,1031,'C1, C2 and D1 omitted by choice. No independent shutdown off-delay.',21,POWER,True)

# Practical right-side pinout and hookup notes.
c.rect(1030,445,725,355,'#f5f8fa',GND)
c.text(1055,464,'Both MOSFETs: SOT-23, TOP VIEW',23,bold=True)
c.text(1055,502,'Marking side up; single leg at the top.',20,MUTED)
c.rect(1115,565,190,90,'#263947',INK)
c.rect(1190,538,40,27,'#c5ced4',GND)
c.rect(1125,655,40,27,'#c5ced4',GND)
c.rect(1255,655,40,27,'#c5ced4',GND)
c.text(1360,561,'3 = Drain (single leg)',22,bold=True)
c.text(1360,607,'1 = Gate (lower left)',22,bold=True)
c.text(1360,653,'2 = Source (lower right)',22,bold=True)
c.text(1198,571,'3',22,'white',True)
c.text(1128,622,'1',22,'white',True);c.text(1271,622,'2',22,'white',True)
c.text(1055,716,'Q1: source to VBAT. Q2: source to GND.',21,bold=True)
c.text(1055,755,'Left blocks show connections, not package orientation.',18,MUTED)
c.text(1030,840,'PRESS: discharged C3 pulls Q1 gate low.',23,CTRL,True)
c.text(1030,879,'HOLD HIGH: Q2 keeps Q1 gate low.',23,CTRL,True)
c.text(1030,918,'RELEASE HOLD: R2 turns Q2 off.',23,CTRL,True)
c.text(1030,957,'If SW1 stays pressed, C3 charges and Q1 turns off.',20,MUTED)
c.text(1030,991,'If SW1 is released, Q1 turns off without C3 delay.',20,MUTED)
c.text(1030,1025,'A short tap must still last through GPIO takeover.',20,POWER,True)

c.line([(45,1090),(1755,1090)],GND,2)
c.text(45,1111,'COMMON GROUND',22,GND,True)
c.text(310,1111,'LiPo negative + JS ground + Arduino CN5 pin 6 + latch GND. No CN15 / TP19 connection.',22,GND)
c.text(45,1153,'Hold PD7 HIGH through capture, save and recovery; float it immediately before Standby.',22)
c.text(45,1190,'Use one target supply: no CN9 shunts, CN8 or VIN feed. LiPo headroom and shutdown sequencing remain unqualified.',20,MUTED)

c.im.save(OUT/'lipo-latch-wiring.png')
(OUT/'lipo-latch-wiring.svg').write_text('\n'.join(c.svg+['</svg>']),encoding='utf-8')
print(OUT/'lipo-latch-wiring.png')
