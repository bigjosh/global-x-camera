"""Render the deferred reuse of Nucleo U6. Offline architecture, not a cut map."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/power'
src = ROOT / 'tools/build_lipo_latch_wiring.py'
ns = {'__file__': str(src)}
exec(src.read_text(encoding='utf-8').split('c=Drawing()')[0], ns)
ns['W'], ns['H'] = 1900, 1250
c = ns['Drawing']()
P, B, M, G = '#b13b35', '#136b9b', '#5d7080', '#526474'
c.svg[1] = '<title>Deferred alternative: consolidated camera power using existing Nucleo U6</title>'

def arrow(x1, x2, y, color=B, width=3):
    c.line([(x1,y),(x2,y)],color,width)
    c.line([(x2-11,y-7),(x2,y),(x2-11,y+7)],color,width)

def diode(x, y):
    c.line([(x-22,y-19),(x+11,y),(x-22,y+19),(x-22,y-19)],P)
    c.line([(x+15,y-23),(x+15,y+23)],P,4)

c.text(40,28,'Consolidated camera power — reuse Nucleo U6',36,bold=True)
c.text(40,83,'DEFERRED — discrete circuit preferred  |  November 8, 2026  |  Existing parts only',23,B,True)
c.text(40,123,'Power connections are shown; enable combining and exact PCB isolation cuts still need a detailed wiring plan.',21,M)

# Protected USB path and diode. Keep the existing board consumer protection.
c.rect(40,192,390,94,'#fff5f3',P)
c.text(60,207,'CN8 USB → board protection',24,P,True)
c.text(60,249,'Takeoff: SB12 pad 1 / 5V_USB_SNK',19,P)
c.line([(430,235),(708,235)],P,4)
diode(730,235)
c.line([(745,235),(915,235),(915,435),(1050,435)],P,4)
c.text(670,185,'D_USB',23,P,True)
c.text(660,271,'Power Schottky',19,M)
c.text(659,302,'Band toward U6',19,M)

# Reversed battery-selection MOSFET. This is not a second shutter latch.
c.rect(40,395,275,83,'#fff5f3',P)
c.text(60,412,'1S LiPo',27,P,True)
c.text(60,451,'500 mAh',19,P)
c.line([(315,435),(470,435)],P,4)
c.rect(470,365,300,165,'#fff5f3',P)
c.text(586,378,'1  G',20,B,True)
c.text(494,417,'3 D     AO3401     2 S',22,P,True)
c.text(502,462,'Battery selector',22,P,True)
c.text(500,496,'Body diode: battery → U6',18,M)
c.line([(770,435),(915,435)],P,4)
c.dot(915,435,P)
c.text(825,480,'SELECTED SUPPLY',19,P,True)
c.text(820,516,'LiPo voltage, or',18,M)
c.text(820,546,'USB minus diode',18,M)

# The PMOS gate senses USB before the diode, with an external pulldown.
c.dot(490,235,P)
c.line([(490,235),(490,326),(620,326),(620,365)],B)
c.dot(490,326,B)
c.line([(490,326),(365,326)],B)
c.line([(365,326),(365,333)],B)
c.rect(353,333,24,28,'white',B)
c.line([(365,361),(365,370)],B)
c.ground(365,370)
c.text(65,309,'100 kΩ gate pull-down',19,B,True)
c.text(65,341,'USB absent → battery path ON',18,M)
c.text(520,292,'USB gate control',18,B)

# Common switch and output. JS is deliberately after the only master switch.
c.rect(1050,345,350,230,'#f0f6fa',B)
c.text(1080,362,'U6 — already on Nucleo',25,B,True)
c.text(1120,403,'TPS259535',25,B,True)
c.text(1066,450,'3,4 IN',20,P,True)
c.text(1300,450,'5 OUT',20,P,True)
c.text(1080,494,'2 EN',20,B,True)
c.text(1118,538,'6 QOD tied to OUT',19,M)
c.line([(1400,435),(1450,435)],P,4)
c.rect(1450,391,155,88,'#fff5f3',P)
c.text(1480,405,'JS110',25,P,True)
c.text(1465,449,'IN+       OUT+',16,P)
c.line([(1605,435),(1650,435)],P,4)
c.rect(1650,391,210,88,'#fff5f3',P)
c.text(1670,405,'CN5 pin 5',25,P,True)
c.text(1670,449,'System power input',17,P)
c.text(1450,507,'U6 output: CN15 pin 8',20,P,True)
c.text(1450,540,'Keep every CN9 jumper OUT.',19,M)
c.line([(1230,575),(1230,600)],G)
c.ground(1230,600)
c.text(1265,587,'8 + exposed pad → GND',19,G)

# A functional diagram avoids implying that USB/battery can directly drive PD7.
c.rect(40,605,910,440,'#f8fbfd',B)
c.text(62,622,'ENABLE CONTROL — functional blocks',24,B,True)
c.text(62,661,'Three independent ways to keep U6 enabled; they must not backfeed one another.',18,M)
rows = [(714,'SPDT + 2.2 µF startup pulse','Positive pulse; held trigger does not give permanent enable'),
        (824,'PD7 HOLD — Arduino D9 / CN14.2','MCU holds ON through capture, saving and recovery'),
        (934,'USB-present enable','Continuous ON while USB supplies the camera')]
for y,title,detail in rows:
    c.rect(65,y,580,84,'white',B)
    c.text(82,y+13,title,22,B,True)
    c.text(82,y+50,detail,17,M)
    arrow(645,710,y+42)
c.line([(710,756),(710,976)],B)
c.dot(710,866,B)
c.rect(750,815,155,103,'#e7f1f8',B)
c.text(781,829,'Isolated',21,B,True)
c.text(789,862,'enable',21,B,True)
c.text(798,892,'OR',17,B)
c.line([(710,866),(750,866)],B)
c.line([(905,866),(990,866),(990,510),(1050,510)],B,3)
c.text(953,900,'EN',20,B,True)

# Fitted support network stays mounted; no claim of a qualified current limit.
c.rect(1050,675,810,370,'#f5f8fa',G)
c.text(1075,693,'Keep U6 and its useful support parts in place',24,bold=True)
c.text(1075,743,'C18 = 10 nF: startup-ramp capacitor',22,B,True)
c.text(1075,782,'R7 = 3.9 kΩ: about 0.55 A nominal current limit',21)
c.text(1075,820,'R29 = 100 kΩ: default-OFF enable pull-down',21)
c.text(1075,858,'C15 = 10 µF: existing output capacitor',21)
c.text(1075,900,'Reuse C25 = 100 nF on the NEW isolated input.',21,P,True)
c.text(1075,940,'Rework must isolate ST-LINK input, enable, current-limit',20,M)
c.text(1075,973,'control and output-sense connections. Not a cut map.',20,M)
c.text(1075,1010,'No Q1/Q2 shutter latch in the qualified U6 version.',19,B,True)

c.line([(40,1083),(1860,1083)],G,2)
c.text(40,1103,'COMMON GROUND',21,G,True)
c.text(294,1103,'LiPo −, U6 ground, external controls, JS ground and CN5 pin 6.',21,G)
c.text(40,1145,'U6 replaces the master latch and is intended to replace R0 after startup qualification.',23,B,True)
c.text(40,1187,'No charger or voltage boost. Do not feed the target around U6. This drawing does not authorize unidentified trace cuts.',20,M)

c.im.save(OUT/'u6-consolidated-power.png')
(OUT/'u6-consolidated-power.svg').write_text('\n'.join(c.svg+['</svg>']),encoding='utf-8')
print(OUT/'u6-consolidated-power.svg')
