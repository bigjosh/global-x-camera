"""Render concise analysis artifacts from completed, offline phase partitions."""
import json, math
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
BASE=Path(__file__).resolve().parent

def read_csv(path):
    import csv
    with path.open() as f:return list(csv.DictReader(f))

def interval(run,name):return next(x for x in run['intervals_overlapping_not_additive'] if x['name']==name)
def fnt(size,bold=False):return ImageFont.truetype('C:/Windows/Fonts/'+('arialbd.ttf' if bold else 'arial.ttf'),size)

def draw_plot(profiles,selected,filename,title,xmax,panels,subtitle='Warm RAM tests; 1 ms current means. The 200 ms hold is diagnostic, not an optimized capture cycle.'):
    W,H=1500,970;im=Image.new('RGB',(W,H),'white');d=ImageDraw.Draw(im)
    d.text((65,28),title,fill='#17243b',font=fnt(29,True))
    d.text((65,75),subtitle,fill='#42536b',font=fnt(19))
    colors=['#7c3aed','#059669','#ea580c','#2563eb','#be123c','#0891b2']
    left,right=100,1430
    for panel,span in enumerate(panels):
        top=170+panel*360;bottom=top+245;maxma=230
        xx=lambda t:left+t/span*(right-left)
        yy=lambda ma:bottom-ma/maxma*(bottom-top)
        d.text((left,top-35),'Full warm capture' if panel==0 else 'Capture and STOP interval (zoom)',fill='#17243b',font=fnt(21,True))
        for ma in (0,50,100,150,200):
            y=yy(ma);d.line((left,y,right,y),fill='#e1e5eb',width=1);d.text((left-55,y-10),str(ma),fill='#536177',font=fnt(16))
        step=100 if span>300 else 20
        for ms in range(0,span+1,step):
            x=xx(ms);d.line((x,top,x,bottom),fill='#ebedf1',width=1);d.text((x-14,bottom+8),str(ms),fill='#536177',font=fnt(16))
        for color,run in zip(colors,selected):
            rows=[p for p in profiles if p['run']==run['run'] and 0<=float(p['time_ms'])<=span]
            pts=[(xx(float(p['time_ms'])),yy(float(p['current_mean_mA']))) for p in rows]
            if len(pts)>1:d.line(pts,fill=color,width=2)
        d.text((left,top-7),'mA',fill='#536177',font=fnt(16))
        d.text((620,bottom+38),'ms from aligned runtime start',fill='#536177',font=fnt(17))
    lx=100
    for color,run in zip(colors,selected):
        d.line((lx,115,lx+24,115),fill=color,width=4);d.text((lx+32,102),run['run'],fill='#17243b',font=fnt(19));lx+=170
    d.text((65,913),'Each trace measures the entire shared rail; colors are test conditions, not individual component power.',fill='#42536b',font=fnt(18))
    d.text((65,942),'Normal cold-cycle energy remains separate; these warm tests omit boot/shutdown and change the card power-up history.',fill='#42536b',font=fnt(17))
    im.save(BASE/filename)

cold=json.loads((BASE/'baseline-phase-partition.json').read_text())
warm=json.loads((BASE/'warm-ram-analysis.json').read_text())
rows=read_csv(BASE/'warm-ram-current-1ms.csv')
sel=[r for name in ('normal01','hold01','reset01','normal02','hold02','reset02') for r in warm if r['run']==name]
draw_plot(rows,sel,'warm-ram-current-comparison.png','Capture activity and deferred SD activity: controlled current comparison',620,[620,140])
normals=[r for r in warm if r['run'].startswith('normal')]
if len(normals)>1:
    draw_plot(rows,normals,'warm-normal-repeat-comparison.png','Normal firmware repeats: storage latency dominates variation',620,[620,140],subtitle='Same warm RAM firmware; 1 ms current means. Normal03 spent about 216 ms longer in slot transport.')
lines=['POWER ABLATION ANALYSIS — 2026-10-28','Offline analysis only. Existing recordings and completed warm experiments; no hardware operations by this analyzer.','','COLD NORMAL BASELINE (three runs; excludes unqualified first 5 ms)']
for a in cold['aggregates']:
    if a['qualified']:
        lines.append(f"{a['name']}: {a['duration_ms_mean']:.3f} ms mean; {a['energy_mJ_mean']:.3f} mJ mean; {a['current_mean_mA_mean']:.3f} mA mean")
lines += ['', 'Stable post-5-ms peak: about 207 mA over 1 ms at 77–78 ms; about 194.5 mA over 10 ms at 71–81 ms. This occurs during SD initialization after frame IRQ, but the camera has not necessarily stopped.', 'Slot transport consumes about two-thirds of post-5-ms energy. Its entire MCU + card + board load is included.', '', 'WARM RAM EXPERIMENTS (not cold-cycle equivalents)']
for r in warm:
    whole=interval(r,'runtime_to_terminal');transport=interval(r,'whole_slot_transport');scan=interval(r,'slot_scan') if any(i['name']=='slot_scan' for i in r['intervals_overlapping_not_additive']) else None
    line=f"{r['run']}: {whole['duration_ms']:.3f} ms / {whole['energy_mJ']:.3f} mJ; slot transport {transport['duration_ms']:.3f} ms / {transport['energy_mJ']:.3f} mJ; scan {r['scan_headers']} headers"
    if scan:line+=f" in {scan['duration_ms']:.3f} ms / {scan['energy_mJ']:.3f} mJ"
    lines.append(line)
    if any(i['name']=='controlled_hold_middle' for i in r['intervals_overlapping_not_additive']):
        hold=interval(r,'controlled_hold_middle');lines.append(f"  Middle hold: {hold['duration_ms']:.3f} ms, {hold['current_mean_mA']:.5f} mA; first/last25ms excluded.")
    lines.append(f"  Sensor STOP at {r['sensor_stop_ms']:.3f} ms; peak1ms {r['peaks']['1ms'][0]['current_mean_mA']:.3f} mA at {r['peaks']['1ms'][0]['start_ms']:.3f} ms.")
means={}
for group in ('hold','reset','receiver'):
    vals=[interval(r,'controlled_hold_middle')['current_mean_mA'] for r in warm if r['run'].startswith(group)]
    if vals:
        means[group]=float(np.mean(vals));lines.append(f'{group} middle-hold mean over {len(vals)} runs: {means[group]:.5f} mA')
if all(k in means for k in ('hold','reset','receiver')):
    lines.append(f'Sensor reset reduction {means["hold"]-means["reset"]:.5f} mA; additional receiver-off reduction {means["reset"]-means["receiver"]:.5f} mA; combined {means["hold"]-means["receiver"]:.5f} mA.')
lines.append('Normal03 slot transport took380.628ms/251.018mJ versus164.165–164.523ms/~103.4mJ in normal01/02. The cause is not established, but total-cycle variation cannot be assigned to small firmware changes without repetition.')
lines.append('Ethernet control ethcontrol01 failed before SD initialization (result0x509, zero written sectors). It is excluded; no Ethernet power-down savings are established.')
lines += ['', 'INTERPRETATION AND NEXT TESTS', '1. Keep phase-timing interventions distinct from component isolation. Delaying SD until after STOP lowers the capture-period load, but includes CPU work, SD bus activity and card demand together.', '2. Hold versus sensor-reset middle windows isolate an incremental post-STOP reset benefit with a matched busy loop. Do not subtract the 79 mA awake floor from the separate 8.7 mA cold Standby plateau as if they were the same state.', '3. Prioritize independent Ethernet PHY power-down versus its matched control, then relevant MCU clock/peripheral gating. U24 remains a real candidate for overhead, but these traces alone do not quantify it.', '4. Reduce scan cost or add a validated allocation hint: the current scan reads one header per previously used slot. More occupied slots confound whole-cycle comparisons, so retain scan count and phase energy for every trial.', '5. Characterize the SD write loop separately: current plots do not distinguish each data transfer from each card-busy interval. Match bytes, card state and fixed SD kernel clock when evaluating CPU sleep/frequency changes.', '6. Qualify the excluded first 5 ms independently before claiming real inrush peak or complete-cycle energy. Source-side JS voltage does not establish target-side rail droop.', '', 'LIMITS', 'All scoped analysis windows have finite, contiguous analog samples and matching raw hashes. Original whole-session initial NaNs remain; final packed GPIO chunk is excluded.', 'Phase7 retains the legacy name padded_payload_ready but in the installed magic-slot path it occurs after successful transport return.', 'Warm DWT time is mapped to JS samples using piecewise GPIO/counter anchors; global-fit drift residuals are saved; do not interpret inferred counter boundaries as sub-microsecond truth.', 'Firmware completion and downloaded original frame are not, by themselves, independent SD readback. Any later root-run SD equality checks belong to their own records.', '', 'ARTIFACTS', 'baseline-phase-partition.json / .csv: disjoint cold phase energies; baseline-phase-current.svg: three cold current traces.', 'warm-ram-analysis.json and RUN-aligned-analysis.json: completed warm results and checks; warm-ram-current-comparison.png: shared-axis comparison.']
(BASE/'analysis-report.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Rendered report and PNG for '+', '.join(r['run'] for r in warm))



