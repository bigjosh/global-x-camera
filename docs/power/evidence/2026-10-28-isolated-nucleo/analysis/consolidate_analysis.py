"""Consolidate completed, independently verified offline analyses."""
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from analyze_isolated import HERE

cpu=json.loads((HERE/'isolated-summary.json').read_text())
phy=json.loads((HERE/'phy-summary.json').read_text())
by={r['run']:r for r in cpu['runs']}
def mean(names,phase,metric):return float(np.mean([by[n]['intervals'][phase+'_middle'][metric] for n in names]))
changes=[]
changes.append(dict(name='Ethernet PHY power-down',saving_mW=float(np.mean([x['comparison']['saving_mW'] for x in phy])),saving_mA=float(np.mean([x['comparison']['saving_mA'] for x in phy])),basis='Two A/B/A runs; compare power-down with mean surrounding original/restored baseline. Restored bursts have not resumed within the measured hold.',runs=[x['run'] for x in phy]))
changes.append(dict(name='400 MHz busy workload to bounded sleep',saving_mW=(mean(['cpu400b','cpu400c'],'busy','power_mean')-mean(['cpu400b','cpu400c'],'sleep','power_mean'))*1000,saving_mA=mean(['cpu400b','cpu400c'],'busy','current_mean_mA')-mean(['cpu400b','cpu400c'],'sleep','current_mean_mA'),basis='Within-run v4 pairs, 100Hz wakeups, camera/SD absent; busy is LFSR/SRAM work.',runs=['cpu400b','cpu400c']))
changes.append(dict(name='CPU 400 MHz to 50 MHz, busy',saving_mW=(mean(['cpu400b','cpu400c'],'busy','power_mean')-mean(['cpu50a'],'busy','power_mean'))*1000,saving_mA=mean(['cpu400b','cpu400c'],'busy','current_mean_mA')-mean(['cpu50a'],'busy','current_mean_mA'),basis='Same v4 binary and elapsed-time workload;50MHz completes fewer updates and costs2.035x energy per update.',runs=['cpu400b','cpu50a','cpu400c']))
changes.append(dict(name='Unused SRAM1/2/3 RUN clocks gated',saving_mW=(mean(['ramcontrol01','ramcontrol02'],'busy','power_mean')-mean(['ramoff01'],'busy','power_mean'))*1000,saving_mA=mean(['ramcontrol01','ramcontrol02'],'busy','current_mean_mA')-mean(['ramoff01'],'busy','current_mean_mA'),basis='Same v5 binary flags0/2/0; clock gating only, not SRAM retention power-off. No measured sleep saving.',runs=['ramcontrol01','ramoff01','ramcontrol02']))
phase_rows=[]
for r in cpu['runs']+phy:
    for k,v in r['intervals'].items():
        if k.endswith('_middle'):
            phase_rows.append(dict(run=r['run'],phase=k[:-7],duration_ms=v['duration_ms'],mean_current_mA=v['current_mean_mA'],mean_power_mW=v['power_mean']*1000,energy_mJ=v['energy_mJ'],start_sample_id=v['start_sample_id'],end_sample_id_exclusive=v['end_sample_id_exclusive']))
cache_rows=[]
for r in cpu['runs']:
    p=r['proof']
    if p['VERSION']==6:
        q=r['intervals'];n=p['BUSY_ITERATIONS'];cache_rows.append(dict(run=r['run'],flags=p['FLAGS'],cpu_MHz=p['CPU_HZ']/1e6,iterations=n,updates_per_second=n/(q['busy_full']['duration_ms']/1000),busy_mW=q['busy_middle']['power_mean']*1000,sleep_mW=q['sleep_middle']['power_mean']*1000,energy_uJ_per_update=q['busy_full']['energy_mJ']*1000/n))
cache_comparison=None
if len(cache_rows)==3:
    controls=[r for r in cache_rows if r['flags']==0];active=next(r for r in cache_rows if r['flags']==4)
    assert len(controls)==2
    cache_comparison=dict(workrate_ratio=active['updates_per_second']/float(np.mean([r['updates_per_second'] for r in controls])),energy_per_update_ratio=active['energy_uJ_per_update']/float(np.mean([r['energy_uJ_per_update'] for r in controls])),busy_power_saving_mW=float(np.mean([r['busy_mW'] for r in controls]))-active['busy_mW'],scope='Same v6 binary flags 0/4/0; synthetic LFSR/SRAM loop only, not measured camera-save performance.',qualification='Original cache-on host validation failed from incorrect cache-bit mask; corrected read-only reobservation passed with identical raw completion proof and unchanged code. Original failure retained.')
plateau_path=HERE/'final-plateau-analysis.json'
plateau=json.loads(plateau_path.read_text()) if plateau_path.exists() else None
report=dict(power_method='Every mean power and energy comes directly from the native power.f32 stream, not mean(V)*mean(I).',changes=changes,phase_rows=phase_rows,icache_rows=cache_rows,
    icache_comparison=cache_comparison,final_shutdown_plateau=plateau,
    measurement_limits=['No camera or SD connected; warm RAM workloads, not complete cold capture/save cycles.',
     'All71 initial nonfinite current samples remain recorded. Whole-session current is invalid; reported bounded windows independently pass finite/continuity tests.',
     'Native2MSPS analog streams aligned by sample_id to packed GPI. Whole final GPI chunks excluded for unresolved packing padding.',
     'Middle windows discard25ms from both ends. PHY holds additionally follow100ms settle; restore DC state does not restore periodic bursts during the short window.',
     'Code/request/raw proof/final context, faults, restored GPIO/clock/debug/LP state and exact native file hashes verified. Full before/after RCC inventory matched for CPU probes.',
     'The current floor cannot be called MCU-only or removable-board-only; PHY difference includes upstream conversion losses.',
     'Changes are measured in separate states and are not additive. Do not project final camera cycle savings until reintegrated and tested.',
     'Compare throughput/energy per update within the same binary version; uncached instruction layout changes loop cost.',
     'Current burst suppression is associated with PHY power state; an Ethernet line waveform was not measured.'],
    excluded=cpu['excluded'],pending=cpu['pending'])
(HERE/'consolidated-analysis.json').write_text(json.dumps(report,indent=2)+'\n')
lines=['Isolated Nucleo power findings — measured2026-10-28','',report['power_method'],'',
 'Change | observed reduction mA | observed reduction mW | interpretation']
for x in changes:lines.append(f"{x['name']} | {x['saving_mA']:.3f} | {x['saving_mW']:.3f} | {x['basis']}")
lines+=['','Every waveform: run | phase | duration ms | mean mA | mean mW | energy mJ']
for x in phase_rows:lines.append(f"{x['run']} | {x['phase']} | {x['duration_ms']:.4f} | {x['mean_current_mA']:.4f} | {x['mean_power_mW']:.4f} | {x['energy_mJ']:.4f}")
lines+=['','I-cache work efficiency (same-version controls only):',json.dumps(cache_rows,indent=2),json.dumps(cache_comparison,indent=2)]
if plateau:lines+=['','Final missing-camera shutdown plateau: '+json.dumps({k:plateau['metrics'][k] for k in ('duration_ms','current_mean_mA','power_mean','energy_mJ')}),plateau['qualification']]
lines+=['','Limits:']+['- '+x for x in report['measurement_limits']]
lines+=['','Recommendation: implement and qualify software PHY power-down before considering removal; it is the largest measured removable support load. Preserve a matched full capture/readback test after camera and SD are reconnected. Continue runtime idle/clock/cache optimization only against total energy and completed work. Main/auxiliary LDO branch current measurements are needed before estimating a custom-board power floor. Small ADC buffers, NOR idle bias, and debugger divider removal are lower priorities. See board-load-research.txt for sourced circuit estimates.']
(HERE/'consolidated-analysis.txt').write_text('\n'.join(lines)+'\n')
print('\n'.join(lines[:9]))

im=Image.new('RGB',(1500,750),'white');d=ImageDraw.Draw(im)
def f(s,b=False):return ImageFont.truetype('C:/Windows/Fonts/'+('arialbd.ttf' if b else 'arial.ttf'),s)
d.text((65,35),'Measured power reductions on the isolated Nucleo',fill='#192a3c',font=f(30,True))
d.text((65,85),'Camera and SD absent · separate controlled comparisons · reductions cannot simply be added',fill='#556779',font=f(20))
x0,x1=620,1360
for i,x in enumerate(changes):
    y=170+i*105;d.text((65,y+7),x['name'],fill='#25364a',font=f(21,True))
    right=x0+(x1-x0)*x['saving_mW']/200
    d.rectangle((x0,y,right,y+43),fill='#137f76' if i==0 else '#3674a4')
    d.text((right+14,y+8),f"{x['saving_mW']:.2f} mW",fill='#25364a',font=f(21))
d.text((65,635),'PHY power-down: about 183 mW removed; about 184 mW remains in that matched busy-loop test.',fill='#192a3c',font=f(23,True))
d.text((65,680),'Slowing the CPU reduced power slightly but increased energy per completed update. RAM gating showed no sleep saving.',fill='#556779',font=f(19))
im.save(HERE/'measured-power-reductions.png')

# Show separately observed states, without implying a combined control or sum.
states=[('400 MHz synthetic workload',mean(['cpu400b','cpu400c'],'busy','power_mean')*1000),('Bounded shallow sleep, PHY unchanged',mean(['cpu400b','cpu400c'],'sleep','power_mean')*1000),('PHY powered down, separate busy loop',float(np.mean([r['intervals']['powerdown_middle']['power_mean'] for r in phy]))*1000)]
if plateau:states.append(('Final error-shutdown low plateau',plateau['metrics']['power_mean']*1000))
im=Image.new('RGB',(1500,760),'white');d=ImageDraw.Draw(im)
d.text((65,35),'Measured board power in separately observed states',fill='#192a3c',font=f(30,True))
d.text((65,85),'Camera and SD disconnected · warm test windows and final cold error-shutdown plateau',fill='#556779',font=f(20))
for i,(label,mw) in enumerate(states):
    y=165+i*105;d.text((65,y+8),label,fill='#25364a',font=f(21,True));right=620+700*mw/400
    d.rectangle((620,y,right,y+43),fill=['#3674a4','#3674a4','#137f76','#6e5c96'][i]);d.text((right+12,y+8),f'{mw:.2f} mW',fill='#25364a',font=f(21))
d.text((65,620),'The 40 mW plateau has retained Standby-history flags; it is not a successful capture-cycle test.',fill='#192a3c',font=f(22,True))
if cache_comparison:d.text((65,666),f'I-cache: {cache_comparison["workrate_ratio"]:.3f}x work rate and {100*(1-cache_comparison["energy_per_update_ratio"]):.1f}% less energy per update in the matched synthetic loop.',fill='#556779',font=f(21))
im.save(HERE/'measured-board-power-states.png')
