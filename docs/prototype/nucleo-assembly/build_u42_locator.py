"""Render U42's verified location from ST's C02 bottom assembly drawing."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
LOCAL = HERE.parents[2] / 'tmp/hardware-review/nucleo-modifications/python-deps'
if LOCAL.exists():
    sys.path.insert(0, str(LOCAL))
import pymupdf
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

# Body rectangle independently read from page 17's vector drawing, not inferred
# from a top-side mirror or designator text position. Pick/place: BottomLayer,
# X=16.8686 mm, Y=29.0750 mm, rotation 180, REG_SOT223-TAB.
BODY = (561.251220703125, 988.3436889648438, 624.3273315429688, 1023.2562866210938)
DOC = pymupdf.open(HERE / 'mb1940-c02-assembly.pdf')
PAGE = DOC[1]
INK, RED, BLUE = '#203040', '#c32642', '#176bad'
plt.rcParams.update({'font.family': 'DejaVu Sans', 'text.color': INK})

def assembly(ax, clip, scale):
    rect = pymupdf.Rect(clip)
    pix = PAGE.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=rect, alpha=False)
    rgb = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3)
    ax.imshow(rgb, extent=(rect.x0, rect.x1, rect.y1, rect.y0))
    ax.set_xlim(rect.x0, rect.x1)
    ax.set_ylim(rect.y1, rect.y0)
    ax.set_aspect('equal')
    ax.axis('off')

fig = plt.figure(figsize=(12, 9.3), facecolor='white')
fig.text(.035, .956, 'U42: unused camera regulator', fontsize=23, weight='bold')
fig.text(.035, .920, 'UNDERSIDE VIEW  |  Keep the ST-LINK USB end at the top; flip the board left-to-right.', fontsize=11)
left = fig.add_axes([.035, .10, .40, .77])
assembly(left, (78, 5, 765, 1300), 1.6)
left.set_title('Locate this area on the back', fontsize=12, pad=8)
left.add_patch(Rectangle((539, 961), 101, 91, fill=False, ec=RED, lw=2.2))
left.annotate('U42', xy=(590,1006), xytext=(420, 940), color=RED, fontsize=13,
              weight='bold', arrowprops={'arrowstyle':'->','color':RED,'lw':1.8})
left.text(420, 75, 'ST-LINK / debugger end', ha='center', fontsize=9, color=BLUE,
          bbox={'facecolor':'white','edgecolor':'none','pad':3})
left.text(420, 1258, 'Camera / target-USB end', ha='center', fontsize=9, color=BLUE,
          bbox={'facecolor':'white','edgecolor':'none','pad':3})

right = fig.add_axes([.49, .335, .475, .50])
assembly(right, (470, 932, 670, 1108), 4)
right.set_title('Close-up: remove only U42', fontsize=15, weight='bold', pad=13)
right.add_patch(Rectangle((557, 967), 72, 79, fill=False, ec=RED, lw=2.2))
right.annotate('U42 / LD1117S33', xy=(593,1004), xytext=(541,945), color=RED,
               fontsize=12, weight='bold', arrowprops={'arrowstyle':'->','color':RED,'lw':1.5})
right.annotate('SB10: KEEP', xy=(514,983), xytext=(474,959), color=BLUE,
               fontsize=10, arrowprops={'arrowstyle':'->','color':BLUE,'lw':1.2})
right.text(594, 1080, '3 small leads + large metal tab\nLeave the pads unconnected.',
           fontsize=11, ha='center', va='center', linespacing=1.5)
fig.text(.49, .245, 'U42 is beside C155 and just above C17.\nThe camera stays powered through SB10.\nDisconnect every power source before soldering.',
         fontsize=12, va='top', linespacing=1.65)
fig.text(.035, .038, 'Source: ST MB1940-N657X0Q-C02, bottom assembly (sheet 17), schematic sheet 11 and C02 BOM.\nCAD location guide, not a photograph. Removal has not yet been performed or measured.',
         fontsize=9, color='#536773', va='bottom')
fig.savefig(HERE / 'u42-location.png', dpi=160, facecolor='white')
fig.savefig(HERE / 'u42-location.svg', facecolor='white')
plt.close(fig)
