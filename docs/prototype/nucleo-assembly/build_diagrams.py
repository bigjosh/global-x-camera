"""Render CAD-derived location guides. Requires pymupdf, matplotlib, numpy.

Input: mb1940-c02-assembly.pdf (ST schematic pages 16-17) and locations.json.
The PDF is rendered, never reinterpreted as a photograph. Labels and callouts
are drawn in the PDF's native page coordinates using ODB++/pick-place data.
"""
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parent
# Optional local tool dependencies used during initial generation.
local=ROOT.parents[2]/'tmp/hardware-review/nucleo-modifications/python-deps'
if local.exists(): sys.path.insert(0,str(local))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle
import pymupdf

DATA=json.loads((ROOT/'locations.json').read_text())
DOC=pymupdf.open(ROOT/'mb1940-c02-assembly.pdf')
RED='#bb2945'; BLUE='#176bad'; AMBER='#9a6000'; INK='#172b3a'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'text.color':INK})

def point(ref,pin=None):
    if pin is None:
        return tuple(DATA['components'][ref]['pdf_xy'])
    return tuple(DATA['pins'][f'{ref}.{pin}']['pdf_xy'])

def background(ax,side,clip):
    rect=pymupdf.Rect(*clip)
    pix=DOC[side].get_pixmap(matrix=pymupdf.Matrix(2.4,2.4),clip=rect,alpha=False)
    rgb=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width,3)
    ax.imshow(rgb,extent=(rect.x0,rect.x1,rect.y1,rect.y0))
    ax.set_xlim(rect.x0,rect.x1);ax.set_ylim(rect.y1,rect.y0)
    ax.set_aspect('equal'); ax.axis('off')

def callout(ax,ref,label,where,color=RED,r=10,pin=None,fs=11):
    xy=point(ref,pin)
    ax.add_patch(Circle(xy,r,fill=False,edgecolor=color,linewidth=1.6,zorder=10))
    ax.annotate(label,xy=xy,xytext=where,textcoords='data',fontsize=fs,
                ha='left',va='center',color=color,
                bbox=dict(boxstyle='round,pad=.3',fc='white',ec=color,lw=.8,alpha=.97),
                arrowprops=dict(arrowstyle='-',color=color,lw=1.3,shrinkA=3,shrinkB=r*.65),zorder=11)

def footer(fig,text):
    fig.text(.035,.018,text,fontsize=9,color='#536773',va='bottom')

def save(fig,name):
    fig.savefig(ROOT/f'{name}.png',dpi=180,facecolor='white')
    fig.savefig(ROOT/f'{name}.svg',facecolor='white')
    svg=ROOT/f'{name}.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8')
    plt.close(fig)

fig,axes=plt.subplots(1,2,figsize=(13,13.7))
fig.subplots_adjust(left=.025,right=.98,top=.89,bottom=.055,wspace=.08)
fig.suptitle('Nucleo MB1940 C02: component locations',x=.035,ha='left',y=.975,fontsize=22,fontweight='bold')
fig.text(.035,.939,'View each side directly. Keep the ST-LINK USB end at the top; flip left-to-right for the underside.',fontsize=11)
for ax,side in zip(axes,[0,1]):
    background(ax,side,(70,0,785,1325))
    ax.set_title('TOP: components and connectors' if side==0 else 'BOTTOM: underside of MCU',fontweight='bold',pad=14)
callout(axes[0],'D2','D2: remove',(95,150),r=15)
callout(axes[0],'R23','R23: remove',(420,225),r=13)
callout(axes[0],'R88','R88 + R89: remove',(525,470),r=14)
axes[0].add_patch(Circle(point('R89'),14,fill=False,ec=RED,lw=1.6))
callout(axes[0],'U24','U24: optional Ethernet removal',(510,925),AMBER,r=28,fs=10)
callout(axes[1],'SB24','SB24: open this bridge',(450,500),r=14)
axes[0].text(500,38,'CN10 / ST-LINK USB',ha='center',fontsize=9,color=BLUE,bbox=dict(fc='white',ec='none',alpha=.95))
axes[0].text(360,1257,'CN8 / target USB',ha='center',fontsize=9,color=BLUE,bbox=dict(fc='white',ec='none',alpha=.95))
axes[1].text(440,45,'ST-LINK end',ha='center',fontsize=10,color=BLUE)
axes[1].text(340,1270,'Ethernet-jack cutout',ha='center',fontsize=9,color=BLUE)
footer(fig,'CAD location guide, not a population photograph. Source: ST MB1940-N657X0Q-C02 schematic assembly pages 16-17.\nRed = core rework. Amber = separately gated Ethernet removal. See the build guide before changing anything.')
save(fig,'rework-overview')

panels=[
 ('D2 and R23 | top, just below ST-LINK MCU',0,(200,170,360,275),
  [('D2','D2: remove',(205,185),12),('R23','R23: remove',(282,257),10)]),
 ('R88 and R89 | top, above main MCU',0,(420,470,535,560),
  [('R89','R89',(485,483),8),('R88','R88',(485,540),8)]),
 ('SB24 | bottom, near upper MCU mounting holes',1,(340,510,470,610),
  [('SB24','SB24: open',(404,592),9)]),
 ('U24 | top, above camera connector / Ethernet jack',0,(365,865,530,1020),
  [('U24','U24: remove only for load trimming',(371,1000),24)]),
]
fig,axes=plt.subplots(2,2,figsize=(13.8,11.5))
fig.subplots_adjust(left=.035,right=.975,top=.92,bottom=.07,wspace=.12,hspace=.21)
fig.suptitle('Rework close-ups: identify the exact body or bridge',x=.035,ha='left',y=.978,fontsize=21,fontweight='bold')
fig.text(.035,.947,'All panels preserve the same orientation as the overview. Circles mark CAD component centers.',fontsize=11)
for ax,(title,side,clip,labels) in zip(axes.flat,panels):
    background(ax,side,clip);ax.set_title(title,fontsize=11,fontweight='bold',pad=10)
    for ref,label,where,r in labels:
        color=AMBER if ref=='U24' else RED
        callout(ax,ref,label,where,color,r,fs=10)
footer(fig,'Locations from ST assembly PDF + manufacturing pick-and-place / ODB++ data. SB24 is on the bottom.\nU24 removal has separate prerequisites. Leave the unused U14 regulator circuit (including R32/R33) unchanged.')
save(fig,'rework-details')

fig=plt.figure(figsize=(13.5,13.8));gs=fig.add_gridspec(3,2,left=.035,right=.975,top=.89,bottom=.07,hspace=.24,wspace=.19)
fig.suptitle('Header wiring: top-side view, ST-LINK USB at the top',x=.035,ha='left',y=.977,fontsize=21,fontweight='bold')
fig.text(.035,.945,'Red = 5 V. Purple = isolated 1.8 V. Blue = NAND signals. Black = ground.',fontsize=11)
ax=fig.add_subplot(gs[0,0]);background(ax,0,(350,275,480,375));ax.set_title('CN9: all shunts removed',fontweight='bold')
callout(ax,'CN9','2: regulated 5 V input',(355,360),RED,r=9,pin=2,fs=10)
ax=fig.add_subplot(gs[0,1]);background(ax,0,(560,75,765,170));ax.set_title('CN12: use pin 14, not pin 13',fontweight='bold')
callout(ax,'CN12','14: existing 1.8 V',(580,85),'#7b3d99',r=9,pin=14,fs=10)
ax=fig.add_subplot(gs[1,0]);background(ax,0,(100,300,190,440));ax.set_title('CN3: feed isolated VDDIO4',fontweight='bold')
callout(ax,'CN3','10: isolated bank supply',(105,425),'#7b3d99',r=9,pin=10,fs=9)
ax=fig.add_subplot(gs[1,1]);background(ax,0,(610,300,710,570));ax.set_title('CN14: NAND CS, clock, IO2 and ground',fontweight='bold')
for pin,label,color,where in [(10,'10 / D15: CLK',BLUE,(612,310)),(9,'9 / D14: IO2',BLUE,(612,368)),(7,'7: GND','#222222',(612,430)),(3,'3 / D10: CS#',BLUE,(612,548))]:
    callout(ax,'CN14',label,where,color,r=9,pin=pin,fs=9)
ax=fig.add_subplot(gs[2,0]);background(ax,0,(170,610,260,775));ax.set_title('CN4: NAND IO0, IO1 and IO3',fontweight='bold')
for pin,label,where in [(2,'2 / A1: IO0',(172,623)),(5,'5 / A4: IO1',(220,722)),(6,'6 / A5: IO3',(172,766))]:
    callout(ax,'CN4',label,where,BLUE,r=9,pin=pin,fs=9)
ax=fig.add_subplot(gs[2,1]);ax.axis('off')
ax.text(0,1,'Connections to make',fontsize=15,fontweight='bold',va='top')
ax.text(0,.87,'CN12.14  ->  CN3.10 and NAND VCC\n\nNAND VSS  ->  CN14.7 (GND)\n\nLTC 5 V  ->  CN9.2\nLTC GND  ->  common board ground\n\nNAND pinout and pullups: see the build guide.\n\nThe 1.8 V jumper is fitted only after SB24\nis open and R88 / R89 have been removed.',fontsize=11,va='top',linespacing=1.55)
footer(fig,'Exact pin coordinates come from ST ODB++ pad records, cross-checked against the assembly drawing.\nCN12.13 and CN12.14 are both sides of a current-sense link; neither is ground. The pin labels above are physical connector pin numbers.')
save(fig,'header-connections')
