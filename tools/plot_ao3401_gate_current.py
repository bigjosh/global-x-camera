"""Plot sourced AO3401 transfer data; this is not a Nucleo load simulation.

Uses the digitized PDF vector paths saved alongside the chart. No hardware I/O.
"""
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
# Reuse the already installed local plotting environment on this bench.
sys.path.insert(0,str(ROOT/'tmp/hardware-review/nucleo-modifications/python-deps'))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT=ROOT/'docs/power'
data=json.loads((OUT/'ao3401-transfer-data.json').read_text(encoding='utf-8'))
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':12,'svg.fonttype':'none'})
fig,ax=plt.subplots(figsize=(11.8,7.8))
fig.subplots_adjust(left=.10,right=.97,bottom=.27,top=.73)
fig.text(.10,.94,'Q1 AO3401: current versus gate voltage',fontsize=21,fontweight='bold')
fig.text(.10,.891,'Typical transistor curves at VDS = −5 V • not a prediction of camera current',fontsize=13,color='#4c5f70')

for curve in data['curves']:
    pts=np.array(curve['points_abs_vgs_v_current_a'])
    temp=curve['temperature_c']
    ax.plot(-pts[:,0],pts[:,1],color='#176da1' if temp==25 else '#be7028',
            lw=3 if temp==25 else 2,ls='-' if temp==25 else '--',label=f'{temp} °C typical')

ax.set_xlim(-2,0);ax.set_ylim(0,2.2)
ax.set_xlabel('Gate relative to source: VGS = VG − VS  (V)',labelpad=11)
ax.set_ylabel('Current through Q1, source → drain  (A)',labelpad=10)
ax.set_xticks(np.arange(-2,.01,.25));ax.set_yticks(np.arange(0,2.21,.2))
ax.grid(color='#dbe2e8',lw=.7);ax.set_axisbelow(True)
ax.spines[['top','right']].set_visible(False)
for sp in ['left','bottom']:ax.spines[sp].set_color('#8796a3')
ax.tick_params(colors='#344958')
sec=ax.secondary_xaxis('top',functions=(lambda v:v+3.7,lambda v:v-3.7))
sec.set_xlabel('Equivalent gate-to-GND voltage if source is 3.7 V (axis conversion only)',labelpad=10)
sec.set_xticks([1.7,2.2,2.7,3.2,3.7]);sec.tick_params(colors='#344958')

ceiling=3.7/2.2
ax.axhline(ceiling,color='#9e4141',lw=1.6,ls=':')
ax.text(-1.04,ceiling+.055,'1.68 A = 3.7 V / 2.2 Ω',color='#9e4141',fontsize=12,fontweight='bold')
ax.text(-1.04,ceiling-.10,'Ideal initial-charging ceiling; real losses lower it',color='#9e4141',fontsize=10)
ax.axhline(.2,color='#697d8c',lw=1.2,ls=':')
ax.text(-.96,.26,'0.20 A example operating load',color='#526574',fontsize=11)

ax.legend(loc='upper right',frameon=False)
fig.text(.10,.145,'← More gate drive / more ON',fontsize=12,color='#176da1',fontweight='bold')
fig.text(.69,.145,'Gate approaches source → OFF',fontsize=12,color='#344958')
fig.text(.10,.097,'In the latch, ON means gate ≈ 0 V and VGS ≈ −3.7 V, beyond the left edge of this zoom.',fontsize=11)
fig.text(.10,.066,'Actual camera current is set by its load and rail voltages. The 2.2 Ω ceiling assumes a discharged input.',fontsize=11)
fig.text(.10,.035,'Source: AOS AO3401 Rev 6.1, Fig. 2. Curves traced from PDF vectors; low-current readings are approximate.',fontsize=10,color='#566877')
fig.savefig(OUT/'ao3401-gate-current.png',dpi=190,facecolor='white')
fig.savefig(OUT/'ao3401-gate-current.svg',facecolor='white')
print(OUT/'ao3401-gate-current.png')
