from pathlib import Path
import sys
ROOT = Path(r'D:\Github\global-x-camera')
sys.path.insert(0, str(ROOT / 'tmp/hardware-review/nucleo-modifications/python-deps'))
import pymupdf
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle
doc = pymupdf.open(ROOT / 'docs/prototype/nucleo-assembly/mb1940-c02-assembly.pdf')
page = doc[1]
# Actual pad outline from the bottom assembly vector drawing, independently
# located beside the TP9 text. ODB bottom TP9 pad is 1.05,2.30499 inches.
point = (500.51641845703125, 727.731689453125)
outline = pymupdf.Rect(491.1020812988281,718.296630859375,509.9307556152344,737.166748046875)
assert any(abs(d['rect'].x0-outline.x0)<.01 and abs(d['rect'].y0-outline.y0)<.01
           and abs(d['rect'].x1-outline.x1)<.01 and abs(d['rect'].y1-outline.y1)<.01
           for d in page.get_drawings())
def background(ax, clip):
    rect=pymupdf.Rect(clip)
    pix=page.get_pixmap(matrix=pymupdf.Matrix(3,3),clip=rect,alpha=False)
    rgb=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width,3)
    ax.imshow(rgb,extent=(rect.x0,rect.x1,rect.y1,rect.y0))
    ax.set_xlim(rect.x0,rect.x1);ax.set_ylim(rect.y1,rect.y0)
    ax.set_aspect('equal');ax.axis('off')
fig=plt.figure(figsize=(12,8.4),facecolor='white')
fig.text(.04,.952,'TP9: buffered exposure-knob signal',fontsize=22,weight='bold',color='#17324d')
fig.text(.04,.91,'BOTTOM VIEW — keep the ST-LINK USB end at the top; flip the board left-to-right.',fontsize=11)
left=fig.add_axes([.035,.10,.43,.77]);background(left,(70,0,785,1325))
left.add_patch(Rectangle((425,660),145,140,fill=False,ec='#c22c40',lw=2))
left.annotate('TP9',xy=point,xytext=(590,620),fontsize=14,weight='bold',color='#c22c40',arrowprops={'arrowstyle':'->','color':'#c22c40','lw':2})
left.text(420,45,'ST-LINK / debugger end',ha='center',fontsize=10,color='#176bad',bbox={'facecolor':'white','edgecolor':'none'})
right=fig.add_axes([.50,.31,.46,.52]);background(right,(420,655,575,815))
right.add_patch(Circle(point,13,fill=False,ec='#c22c40',lw=2.2))
right.annotate('Probe this round pad',xy=point,xytext=(425,670),fontsize=12,color='#c22c40',weight='bold',arrowprops={'arrowstyle':'->','color':'#c22c40','lw':1.5},bbox={'facecolor':'white','edgecolor':'none'})
fig.text(.50,.23,'Meter black lead: board GND\nMeter red lead: TP9\nExpected: about 0 to 1.78 V as A4 moves from 0 to 3.28 V.',fontsize=12,linespacing=1.5)
fig.text(.04,.045,'Source: ST MB1940-N657X0Q-C02 bottom assembly, sheet 17.\nTP9 = U9A output = PF3 / ADC1_INP16. CAD locator; no component removal.',fontsize=9,color='#526273')
out=ROOT/'tmp/bringup/control-smoke-20261107/tp9-location.png'
fig.savefig(out,dpi=160,facecolor='white')
print(out)
