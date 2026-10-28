"""Offline chart/report rendering from completed analyzer outputs only."""
from pathlib import Path
import json, math
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE=Path(__file__).resolve().parent
summary=json.loads((HERE/'comparison.json').read_text())
groups=summary['groups']
selected=[]
for name in ('baseline','candidate'):
    if name in groups:
        for row in groups[name]['runs']:
            r=json.loads((HERE/(row['run']+'-analysis.json')).read_text())
            assert r['group']==name and r['unique_marker_train'] and r['marker_precedence_pass']
            selected.append(r)
assert selected
colors={'baseline':['#2c5f9a','#5984b2','#8aa6c5'],'candidate':['#007563','#2b9c89','#66baa9']}
def font(n,bold=False):return ImageFont.truetype('C:/Windows/Fonts/'+('arialbd.ttf' if bold else 'arial.ttf'),n)
def canvas(title,subtitle,height=1000):
    im=Image.new('RGB',(1560,height),'white');d=ImageDraw.Draw(im)
    d.text((65,32),title,fill='#182d42',font=font(31,True));d.text((65,80),subtitle,fill='#566b7e',font=font(20));return im,d
status='Candidate recordings pending' if 'candidate' not in groups else f"{groups['baseline']['count']} baseline + {groups['candidate']['count']} PHY-power-down cold cycles"

# Overlay current without time-normalizing or stretching SD write intervals.
im,d=canvas('Normal capture: current versus elapsed time',status+' · first 5 ms excluded · native samples averaged into 1 ms bins')
left,right,top,bottom=95,1470,150,690
endmax=max(r['whole_cycle_raw_unqualified']['duration_ms']+50 for r in selected)
xmax=math.ceil(endmax/100)*100;ymax=250
def x(t):return left+(right-left)*t/xmax
def y(v):return bottom-(bottom-top)*v/ymax
for v in range(0,ymax+1,50):
    yy=y(v);d.line((left,yy,right,yy),fill='#dce4eb');d.text((left-52,yy-10),str(v),fill='#566b7e',font=font(17))
for t in range(0,xmax+1,100):
    xx=x(t);d.line((xx,top,xx,bottom),fill='#e8edf2');d.text((xx-15,bottom+12),str(t),fill='#566b7e',font=font(17))
d.text((25,115),'mA',fill='#263c50',font=font(19,True));d.text((620,735),'ms from measured current onset',fill='#263c50',font=font(20))
counts={}
for i,r in enumerate(selected):
    group=r['group'];j=counts.get(group,0);counts[group]=j+1;color=colors[group][j%3]
    p=json.loads((HERE/(r['run']+'-profile.json')).read_text())
    assert all(math.isfinite(v['current_mA']) and v['current_mA']<=ymax for v in p),'Raise y-scale; never clip waveform'
    d.line([(x(v['time_ms']),y(v['current_mA'])) for v in p],fill=color,width=2)
    lx=65+(i%3)*485;ly=805+(i//3)*43
    d.line((lx,ly+12,lx+35,ly+12),fill=color,width=4)
    energy=r['post5ms_to_plateau']['energy_mJ'];ms=r['whole_cycle_raw_unqualified']['duration_ms']
    d.text((lx+48,ly),f'{r["run"]}: {energy:.1f} mJ, {ms:.1f} ms',fill='#263c50',font=font(20))
d.text((65,935),'Longer SD intervals remain longer on this plot. No time warping, card-latency correction or startup-energy estimate.',fill='#566b7e',font=font(19))
im.save(HERE/'cycle-current-comparison.png')

# Every repetition is visible; empty candidate area remains explicitly pending.
im,d=canvas('Normal capture: energy and SD timing by repetition',status+' · compare phase power before attributing duration changes',height=1040)
rowy=165;left=340;span=1000
emax=math.ceil(max(r['post5ms_to_plateau']['energy_mJ'] for r in selected)/50)*50
for i,r in enumerate(selected):
    e=r['post5ms_to_plateau']['energy_mJ'];t=r['phase_windows_overlapping_not_additive']['slot_transport']['duration_ms'];color=colors[r['group']][0]
    yy=rowy+i*75;d.text((65,yy+7),r['run'],fill='#263c50',font=font(22,True));end=left+span*e/emax
    d.rectangle((left,yy,end,yy+37),fill=color);d.text((end+12,yy+4),f'{e:.1f} mJ',fill='#263c50',font=font(20))
    d.text((left,yy+43),f'SD transport {t:.2f} ms; mean {r["phase_windows_overlapping_not_additive"]["slot_transport"]["power_mean"]*1000:.1f} mW',fill='#566b7e',font=font(17))
gy=690
for i,g in enumerate(('baseline','candidate')):
    xx=65+i*750
    if g not in groups:d.text((xx,gy),'Candidate: pending measured recordings',fill='#566b7e',font=font(21,True));continue
    st=groups[g]['statistics'];e=st['post5ms_energy_mJ'];t=st['slot_transport_ms']
    d.text((xx,gy),g.capitalize(),fill=colors[g][0],font=font(24,True))
    d.text((xx,gy+42),f'Energy mean {e["mean"]:.1f}, median {e["median"]:.1f} mJ',fill='#263c50',font=font(21))
    d.text((xx,gy+80),f'Energy range {e["min"]:.1f}–{e["max"]:.1f} mJ',fill='#566b7e',font=font(20))
    d.text((xx,gy+118),f'SD time mean {t["mean"]:.1f}, median {t["median"]:.1f} ms',fill='#263c50',font=font(20))
d.text((65,930),'Energy runs from current onset + 5 ms to low plateau; it excludes the unqualified startup transient.',fill='#566b7e',font=font(19))
d.text((65,965),'The card’s varying write latency changes energy even with identical firmware. Three trials show the observed range.',fill='#566b7e',font=font(19))
im.save(HERE/'cycle-energy-comparison.png')

if 'candidate' in groups:
    pair=[next(r for r in selected if r['run']==n) for n in ('baseline02','candidate02')]
    im,d=canvas('Lower power, with unchanged first-strobe timing',
      'Waveforms: baseline02 and candidate02, with similar SD write times · statistics below use all three runs per firmware',height=1050)
    left,right,top,bottom=95,1470,150,620;xmax=500;ymax=250
    def px(t):return left+(right-left)*t/xmax
    def py(v):return bottom-(bottom-top)*v/ymax
    for value in range(0,251,50):
        yy=py(value);d.line((left,yy,right,yy),fill='#dce4eb');d.text((left-52,yy-10),str(value),fill='#566b7e',font=font(17))
    for t in range(0,501,50):
        xx=px(t);d.line((xx,top,xx,bottom),fill='#e8edf2');d.text((xx-15,bottom+12),str(t),fill='#566b7e',font=font(17))
    d.text((25,115),'mA',fill='#263c50',font=font(19,True))
    for i,r in enumerate(pair):
        p=json.loads((HERE/(r['run']+'-profile.json')).read_text());color=colors[r['group']][0]
        assert all(z['time_ms']<=xmax and z['current_mA']<=ymax for z in p)
        d.line([(px(z['time_ms']),py(z['current_mA'])) for z in p],fill=color,width=3)
        yy=170+i*42;d.line((1110,yy+12,1150,yy+12),fill=color,width=4)
        d.text((1165,yy),r['run'],fill=color,font=font(22,True))
    d.text((630,665),'ms from measured current onset',fill='#263c50',font=font(20))
    a=groups['baseline']['statistics'];b=groups['candidate']['statistics']
    cards=[('Median energy, excluding first 5 ms',f'{a["post5ms_energy_mJ"]["median"]:.1f} -> {b["post5ms_energy_mJ"]["median"]:.1f} mJ',f'{100*(1-b["post5ms_energy_mJ"]["median"]/a["post5ms_energy_mJ"]["median"]):.1f}% lower'),
      ('Median SD-transport mean power',f'{a["slot_transport_mean_power_mW"]["median"]:.1f} -> {b["slot_transport_mean_power_mW"]["median"]:.1f} mW',f'{100*(1-b["slot_transport_mean_power_mW"]["median"]/a["slot_transport_mean_power_mW"]["median"]):.1f}% lower'),
      ('Median first strobe observation',f'{a["strobe_from_onset_ms"]["median"]:.3f} -> {b["strobe_from_onset_ms"]["median"]:.3f} ms','Effectively unchanged')]
    for i,(label,value,note) in enumerate(cards):
        xx=65+i*495;d.text((xx,735),label,fill='#566b7e',font=font(19));d.text((xx,778),value,fill='#182d42',font=font(26,True));d.text((xx,823),note,fill='#007563',font=font(22,True))
    d.text((65,910),f'Median cycle duration: {a["cycle_onset_to_plateau_ms"]["median"]:.1f} -> {b["cycle_onset_to_plateau_ms"]["median"]:.1f} ms. SD init and scanning varied; no cycle-speed gain claimed.',fill='#263c50',font=font(21))
    d.text((65,955),'Energy ends at measured low plateau. First 5 ms remain unqualified; image readback and shutdown flags are separate evidence.',fill='#566b7e',font=font(19))
    im.save(HERE/'typical-cycle-power-comparison.png')

phase_groups={}
for group in ('baseline','candidate'):
    rs=[r for r in selected if r['group']==group]
    if not rs:continue
    phase_groups[group]={}
    for phase in rs[0]['phase_windows_overlapping_not_additive']:
        rows=[dict(run=r['run'],duration_ms=r['phase_windows_overlapping_not_additive'][phase]['duration_ms'],power_mW=r['phase_windows_overlapping_not_additive'][phase]['power_mean']*1000,energy_mJ=r['phase_windows_overlapping_not_additive'][phase]['energy_mJ']) for r in rs]
        phase_groups[group][phase]=dict(rows=rows,statistics={key:dict(mean=float(np.mean([v[key] for v in rows])),median=float(np.median([v[key] for v in rows])),min=float(min(v[key] for v in rows)),max=float(max(v[key] for v in rows))) for key in ('duration_ms','power_mW','energy_mJ')})
(HERE/'phase-power-summary.json').write_text(json.dumps(phase_groups,indent=2)+'\n')
lines=['Normal capture PHY power comparison',status,'','Measured baseline:']
for group in ('baseline','candidate'):
    if group not in groups:continue
    st=groups[group]['statistics'];lines+=['',group.upper()]
    for key in ('post5ms_energy_mJ','cycle_onset_to_plateau_ms','strobe_from_onset_ms','SD_init_ms','SD_ready_to_first_submission_ms','slot_transport_ms','slot_transport_mean_power_mW'):
        q=st[key];lines.append(f'{key}: mean {q["mean"]:.6f}; median {q["median"]:.6f}; range {q["min"]:.6f}..{q["max"]:.6f}')
    lines+=['Phase power (overlapping phase windows are not additive):']
    for phase,q in phase_groups[group].items():
        p=q['statistics']['power_mW'];t=q['statistics']['duration_ms'];lines.append(f'{phase}: power mean {p["mean"]:.3f} mW, range {p["min"]:.3f}..{p["max"]:.3f}; duration mean {t["mean"]:.3f} ms, range {t["min"]:.3f}..{t["max"]:.3f}')
if 'candidate' in groups:
    lines+=['','BASELINE TO CANDIDATE (positive delta = candidate increase):']
    for key,q in summary['comparison'].items():
        lines.append(f'{key}: mean delta {q["candidate_minus_baseline"]:.6f}, median delta {q["candidate_minus_baseline_median"]:.6f}; mean reduction {q["reduction_percent"]:.3f}%, median reduction {q["median_reduction_percent"]:.3f}%')
lines+=['','SD_ready_to_first_submission includes SCR read, slot-header scan and write preparation; markers do not isolate the scan alone. Slot occupancy grows as images are saved.',
 'Qualification: all reported energy windows are finite/contiguous and bound by native sample IDs; initial current NaNs remain outside the qualified interval. First5ms/full-cycle raw energy remains unqualified. Source-side voltage is not a target-rail measurement. All digital edges are retained; unmatched startup edges are not labeled firmware. Firmware identity/installation, PHY proof, image readback and Standby flags remain separate evidence.',
 'Interpretation: per-run mean/median/range are descriptive, not statistical significance. SD timing varies enough to obscure small energy differences. Compare matched firmware phases and transport mean power, while preserving the observed duration distribution.']
if 'candidate' not in groups:lines+=['','Candidate conclusion: deferred until recordings and independent qualification exist.']
(HERE/'comparison-report.txt').write_text('\n'.join(lines)+'\n')
print(status)
print('Wrote cycle-current-comparison.png, cycle-energy-comparison.png, phase-power-summary.json and comparison-report.txt')
