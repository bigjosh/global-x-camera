"""Build the archived September 5 PMOS diagram and engineering estimates.

The calculations are a DC screening model, not a SPICE model or qualification.
"""
import html
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import pypdfium2 as pdfium

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/power'
OUT.mkdir(parents=True, exist_ok=True)
W, H, SCALE = 1600, 1020, 2
im = Image.new('RGB', (W*SCALE, H*SCALE), 'white')
draw = ImageDraw.Draw(im)
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
       '<rect width="100%" height="100%" fill="white"/>',
       '<title>Proposed battery latch with side-actuated shutter switch</title>',
       '<desc>Two common-source PMOS devices, a protected gate divider, a mechanical switch and an NMOS holding driver. MAIN_HOLD is an interface to a required, unimplemented sequencer.</desc>']
INK, POWER, GATE, LOGIC, MUTED = '#172c43', '#175a83', '#a55a0b', '#127569', '#586777'

def line(points, color=INK, width=3):
    draw.line([(x*SCALE,y*SCALE) for x,y in points], fill=color, width=width*SCALE)
    svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round"/>')

def box(x,y,w,h,fill='#f3f7fb',color=INK):
    draw.rectangle((x*SCALE,y*SCALE,(x+w)*SCALE,(y+h)*SCALE),fill=fill,outline=color,width=2*SCALE)
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="{fill}" stroke="{color}" stroke-width="2"/>')

def text(x,y,value,size=21,color=INK,bold=False,anchor='left'):
    fontpath = Path('C:/Windows/Fonts') / ('segoeuib.ttf' if bold else 'segoeui.ttf')
    font = ImageFont.truetype(str(fontpath),size*SCALE)
    pilanchor = {'left':'lt','middle':'mt','right':'rt'}[anchor]
    draw.text((x*SCALE,y*SCALE),value,font=font,fill=color,anchor=pilanchor)
    svga = {'left':'start','middle':'middle','right':'end'}[anchor]
    svg.append(f'<text x="{x}" y="{y+size*.82}" font-family="Segoe UI,Arial,sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" text-anchor="{svga}" fill="{color}">{html.escape(value)}</text>')

def dot(x,y,color=INK,r=5):
    draw.ellipse(((x-r)*SCALE,(y-r)*SCALE,(x+r)*SCALE,(y+r)*SCALE),fill=color)
    svg.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}"/>')

def resistor(x,y1,y2,ref,value,color):
    mid=(y1+y2)/2
    line([(x,y1),(x,mid-25)],color)
    box(x-12,mid-25,24,50,'white',color)
    line([(x,mid+25),(x,y2)],color)
    text(x+28,mid-26,ref,21,color,True)
    text(x+28,mid+1,value,21,color)

def ground(x,y):
    line([(x-15,y),(x+15,y)])
    line([(x-10,y+7),(x+10,y+7)])
    line([(x-5,y+14),(x+5,y+14)])

text(55,30,'Battery power latch',34,bold=True)
text(55,78,'Side-actuated reference circuit  |  8–13.2 V battery  |  Common ground',22,color=MUTED)

# MOSFET blocks intentionally identify electrical pins, not package orientation.
for x,ref,left,right in [(280,'Q1','D','S'),(780,'Q3','S','D')]:
    box(x,160,220,155)
    text(x+110,176,ref+'  P-MOS',24,bold=True,anchor='middle')
    text(x+110,211,'DMP2077UCA3-7',19,anchor='middle')
    text(x+12,245,left,22,POWER,True)
    text(x+207,245,right,22,POWER,True,anchor='right')
    text(x+110,274,'G',22,GATE,True,anchor='middle')
    text(x+110,129,('Body diode: D → S' if ref=='Q1' else 'Body diode: S ← D'),18,color=MUTED,anchor='middle')
    line([(x+110,315),(x+110,420)],GATE)
text(55,177,'BAT+',24,POWER,True)
text(55,209,'8–13.2 V',20,POWER)
line([(55,260),(280,260)],POWER,4)
line([(500,260),(780,260)],POWER,4)
dot(640,260,POWER)
text(640,211,'COMMON_SOURCE',18,POWER,True,anchor='middle')
line([(1000,260),(1510,260)],POWER,4)
text(1210,181,'SYS_IN',25,POWER,True)
text(1100,213,'To regulators / USB source path (§4)',20,POWER)
line([(1495,251),(1510,260),(1495,269)],POWER)
line([(390,420),(890,420)],GATE)
dot(640,420,GATE)
text(904,411,'PMOS_GATE',20,GATE,True)
resistor(640,260,420,'R1','4.7 kΩ, 1%',GATE)
resistor(640,420,600,'R2','2.2 kΩ, 1%',GATE)
line([(420,600),(900,600)],GATE)
dot(640,600,GATE)
text(655,565,'ACTUATE — battery-level node',20,GATE,True)

# Button and gate driver in parallel below R2.
line([(420,600),(420,675)],GATE)
dot(420,675,GATE,4)
line([(420,749),(444,690)],INK)
dot(420,749,INK,4)
line([(420,749),(420,915)])
text(95,652,'SW1  KMS223G LFG',24,bold=True)
text(95,687,'Order: Y28B22310FP',20)
text(95,721,'Momentary, normally open',19)
text(95,754,'Side push · gold · 32 V',19)
text(95,787,'Specified minimum load: 1 mA',18,color=MUTED)
text(95,823,'Case / ground terminal → GND',18,color=MUTED)

line([(900,600),(900,670)],GATE)
box(810,670,180,135,'#f1f8f6',LOGIC)
text(900,680,'D',20,GATE,True,anchor='middle')
text(900,710,'Q2  N-MOS',21,bold=True,anchor='middle')
text(900,739,'BSS138LT1G',19,anchor='middle')
text(977,709,'G',20,LOGIC,True,anchor='right')
text(900,779,'S',20,INK,True,anchor='middle')
line([(900,805),(900,915)])
line([(990,725),(1100,725)],LOGIC)
dot(1040,725,LOGIC)
resistor(1040,725,915,'R3','47 kΩ, 1%',LOGIC)

box(1100,545,440,245,'#fff8e8','#9b6a12')
text(1120,563,'REQUIRED CONTROL INTERFACE',21,'#805509',True)
text(1120,604,'Sequencer + source-selection logic',21)
text(1120,640,'Component implementation still required',18,color=MUTED)
text(1120,679,'MAIN_HOLD: ≥2.75 V HIGH / LOW to release',18,LOGIC,True)
text(1120,722,'Keep HIGH until all N6 AUX rails <0.6 V',18)
text(1120,755,'USB-only startup must leave it LOW',18)

line([(55,915),(1510,915)],INK,4)
text(55,875,'BAT− = GND = MCU ground',22,bold=True)
for x in [420,900,1040]: dot(x,915)
ground(1450,915)
text(55,957,'Connection diagram, not a footprint view. Only filled dots join branches. Q1/Q3 sources and gates are paired.',19,color=MUTED)
text(55,986,'All discrete latch parts are shown. The highlighted control block and downstream supply sequencing are not yet implemented.',18,color=MUTED)
svg.append('</svg>')
(OUT/'power-latch.svg').write_text('\n'.join(svg),encoding='utf-8')
im.save(OUT/'power-latch.png')

# Explicit DC model: Q1 supplies both the system current and the divider.
def operating_point(vbat, iload, rgs=4700.0, rdown=2200.0, rn=10.0, rp=0.1):
    iact=(vbat-iload*rp)/(rgs+rdown+rn+rp)
    vs=vbat-(iload+iact)*rp
    vout=vs-iload*rp
    return dict(vbat=vbat, iload=iload, iact=iact, ibat=iload+iact,
                common_source=vs, sys_in=vout, pair_drop=vbat-vout,
                vgs_magnitude=iact*rgs, actuator_voltage=iact*rn,
                p_q1=(iload+iact)**2*rp, p_q3=iload**2*rp,
                p_r1=iact**2*rgs, p_r2=iact**2*rdown, p_q2=iact**2*rn)

def constant_power(vbat,power=4.4,rgs=4700,rdown=2200,rn=10,rp=0.1):
    a=rgs+rdown+rn+rp
    veff=vbat*(1-rp/a)
    reff=2*rp-rp*rp/a
    iload=2*power/(veff+math.sqrt(veff*veff-4*reff*power))
    point=operating_point(vbat,iload,rgs,rdown,rn,rp)
    assert abs(point['sys_in']*point['iload']-power)<1e-9
    return point

result={
    'status':'Engineering estimates; not guaranteed assembled-circuit limits',
    'fixed_load': [operating_point(v,0.55) for v in (8,12,13.2)],
    'constant_4p4w_system': [constant_power(v) for v in (8,12,13.2)],
    'alternative_ulc_fixed_load': [operating_point(v,0.55,100000,47000) for v in (8,12,13.2)],
    'gate_ratio_min_1pct':4700*.99/(4700*.99+2200*1.01),
    'gate_ratio_max_1pct':4700*1.01/(4700*1.01+2200*.99),
    'gate_vgs_max_unloaded_1pct':13.2*4700*1.01/(4700*1.01+2200*.99),
    'hold_pulldown_current_3p3v':3.3/47000,
    'hold_pulldown_power_3p3v':3.3**2/47000,
    'off_screening_nA':{str(v):100+100+v for v in (8,12,13.2)},
    'ten_year_charge_mAh':{str(n):n*1e-6*24*365*10 for n in (100,200,213.2,300,1000)},
}
(OUT/'power-calculations.json').write_text(json.dumps(result,indent=2)+'\n')
for section in ('fixed_load','constant_4p4w_system','alternative_ulc_fixed_load'):
    print(section)
    for p in result[section]:
        print('VBAT %.1f, Iload %.6f A, Iact %.3f mA, VGS %.4f V, drop %.3f mV, FET %.3f mW, gate %.3f mW' %
              (p['vbat'],p['iload'],p['iact']*1e3,p['vgs_magnitude'],p['pair_drop']*1e3,
               (p['p_q1']+p['p_q3'])*1e3,(p['p_r1']+p['p_r2']+p['p_q2'])*1e3))
print('1pct VGS max',result['gate_vgs_max_unloaded_1pct'])

# Read-only datasheet renders for terminal/parameter review.
qa=ROOT/'tmp/power-document'
qa.mkdir(parents=True,exist_ok=True)
for filename,page in [('Diodes_DMP2077UCA3.pdf',0),('onsemi_BSS138L.pdf',1)]:
    document=pdfium.PdfDocument(ROOT/'datasheets/candidates/power-latch'/filename)
    document[page].render(scale=1.8).to_pil().save(qa/(Path(filename).stem+'.png'))
