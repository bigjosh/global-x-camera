"""Offline CPU result comparison and phase-aligned current figure."""
from pathlib import Path
import json, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from analyze_isolated import HERE, CAMPAIGN
from analyze_warm_ablations import load
from analyze_existing_baseline import FS

names=['cpu400b','cpu200a','cpu100a','cpu50a','cpu400c']
reports=[json.loads((HERE/(name+'-analysis.json')).read_text()) for name in names]
rows=[]
for r in reports:
    v=r['intervals'];p=r['proof'];busy=v['busy_full'];mid=v['busy_middle'];sleep=v['sleep_middle'];n=p['BUSY_ITERATIONS']
    rows.append(dict(run=r['run'],cpu_MHz=p['CPU_HZ']/1e6,updates=n,busy_ms=busy['duration_ms'],
       updates_per_second=n/(busy['duration_ms']/1000),busy_mA=mid['current_mean_mA'],sleep_mA=sleep['current_mean_mA'],
       busy_energy_mJ=busy['energy_mJ'],total_busy_energy_uJ_per_update=busy['energy_mJ']*1000/n,
       incremental_energy_uJ_per_update=(mid['power_mean']-sleep['power_mean'])*(busy['duration_ms']/1000)*1e6/n))
base=np.mean([r['total_busy_energy_uJ_per_update'] for r in rows if r['cpu_MHz']==400])
for r in rows:r['fixed_work_energy_ratio_to_mean_400MHz']=r['total_busy_energy_uJ_per_update']/base
(HERE/'cpu-work-efficiency.json').write_text(json.dumps(dict(rows=rows,
    method='One update is one inner LFSR/SRAM buffer operation (BUSY_ITERATIONS counts256 per outer loop). Full busy window energy divided by completed updates. Incremental energy subtracts matched middle-sleep mean power; it is a model, not an isolated-core measurement.',
    caveats=['Workload and caches-off RAM execution are synthetic, not representative of every capture phase.',
             'Clock-divider changes retain PLLs, bus/memory clocks, rails, and other board loads.',
             'Fixed-work ratios extrapolate measured update throughput; they do not measure an actual longer job.']),indent=2)+'\n')
lines=['CPU workload efficiency, isolated Nucleo','',
       'Run | MHz | updates/s | busy mJ | uJ/update | fixed-work energy vs400MHz']
for r in rows:lines.append(f"{r['run']} | {r['cpu_MHz']:g} | {r['updates_per_second']:.0f} | {r['busy_energy_mJ']:.3f} | {r['total_busy_energy_uJ_per_update']:.6f} | {r['fixed_work_energy_ratio_to_mean_400MHz']:.3f}x")
lines+=['','50MHz reduces current a little but completes about half the work per second.',
        'For this caches-off RAM workload, fixed-work energy therefore increases; do not promote slowing the CPU on current alone.',
        'The remaining floor includes MCU fabric/PLLs/SRAM and board loads; it is not established as removable board overhead.']
(HERE/'cpu-work-efficiency.txt').write_text('\n'.join(lines)+'\n');print('\n'.join(lines))

im=Image.new('RGB',(1500,1040),'#ffffff');d=ImageDraw.Draw(im)
def font(size,bold=False):return ImageFont.truetype('C:/Windows/Fonts/'+('arialbd.ttf' if bold else 'arial.ttf'),size)
d.text((70,35),'Isolated Nucleo: CPU clock and bounded sleep',fill='#17212f',font=font(32,True))
d.text((70,85),'Camera and SD disconnected · 5 V input · LEDs off · caches off · no debugger during windows',fill='#536273',font=font(21))
colors=['#2166ac','#d95f02','#1b9e77','#b23a9b','#6c87a8']
x0,x1,y0,y1=100,1410,160,700
def xy(t,i):return (x0+(x1-x0)*t/410,y1-(y1-y0)*(i-66)/18)
for v in range(66,85,2):
    _,y=xy(0,v);d.line((x0,y,x1,y),fill='#e2e8ef');d.text((40,y-12),str(v),fill='#536273',font=font(18))
for t in range(0,401,50):
    x,_=xy(t,66);d.line((x,y0,x,y1),fill='#edf0f4');d.text((x-12,y1+10),str(t),fill='#536273',font=font(18))
d.text((22,125),'mA',fill='#536273',font=font(20))
d.text((1110,735),'ms since busy-start marker',fill='#536273',font=font(20))
for r,color in zip(reports,colors):
    sig,_=load(CAMPAIGN/r['run']/'trace');origin=r['markers'][0]['sample_id'];last=r['markers'][-1]['sample_id'];st,cur=sig['current'];pts=[]
    for a in range(origin,last-1999,2000):
        mean=float(np.mean(cur[a-st:a-st+2000],dtype=np.float64))*1000
        pts.append(xy((a-origin+1000)/FS*1000,mean))
    d.line(pts,fill=color,width=3)
x,_=xy(201.2,66);d.line((x,y0,x,y1),fill='#607080',width=2)
d.text((310,125),'Busy: LFSR + SRAM workload',fill='#223244',font=font(21,True))
d.text((950,125),'Sleep: 100 Hz timer wakes',fill='#223244',font=font(21,True))
d.text((70,795),'Middle-window mean current and measured fixed-work efficiency',fill='#17212f',font=font(23,True))
for k,(r,c) in enumerate(zip(rows,colors)):
    x=85+k*280;d.line((x,845,x+38,845),fill=c,width=5)
    d.text((x+48,832),r['run'],fill='#223244',font=font(19,True))
    d.text((x,870),f"Busy {r['busy_mA']:.2f} mA",fill='#223244',font=font(19))
    d.text((x,900),f"Sleep {r['sleep_mA']:.2f} mA",fill='#223244',font=font(19))
    d.text((x,930),f"Work energy {r['fixed_work_energy_ratio_to_mean_400MHz']:.2f}x",fill='#223244',font=font(19))
d.text((70,990),'1 ms current means; zoomed vertical axis. Sleep window includes interrupt work. The ~70 mA floor is not attributed to a single component.',fill='#536273',font=font(18))
im.save(HERE/'cpu-clock-sleep-current.png')
