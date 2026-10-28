"""Offline analysis of cold camera/STOP -> diagnostic gap -> SD cycles.

Never imports a hardware runner. Old analysis source is read-only; its in-memory
output directory is redirected here before use. All output stays in this folder.
Input manifest entries: run, group (normal or gap), absolute trace, evidence.
"""
from pathlib import Path
import argparse, importlib.util, json, sys
import numpy as np

HERE=Path(__file__).resolve().parent
CAMPAIGN=HERE.parent
SOURCE=CAMPAIGN.parent/'ethernet-normal-20261028/analysis/analyze_cycles.py'
spec=importlib.util.spec_from_file_location('sd_gap_readonly_normal_decoder',SOURCE)
normal=importlib.util.module_from_spec(spec)
spec.loader.exec_module(normal)
normal.HERE=HERE
normal.CAMPAIGN=CAMPAIGN
FS=normal.FS;metrics=normal.metrics;sha=normal.sha;load=normal.load
NAMES=dict(normal.EVENTS,**{})
NAMES.update({11:'validated_STOP_gap_begin',12:'gap_end'})

def decode(signals,gap,awake=False):
    es=normal.edges(signals,'gpi0');pulses=[];expected=list(range(1,10 if awake else 11))
    if gap:expected+=[11,12]
    for a,b in zip(es,es[1:]):
        if a['level']==1 and b['level']==0:
            width=(b['sample_id']-a['sample_id'])/FS*1e6
            ids=[i for i in expected if abs(width-(2*i+.24))<=.80]
            pulses.append(dict(sample_id=a['sample_id'],end_sample_id=b['sample_id'],width_us=width,matching_ids=ids))
    precedence=tuple((a,b) for a,b in normal.PRECEDENCE if a in expected and b in expected)+(((3,11),(11,12),(12,4)) if gap else ())
    candidates=[]
    for i,p in enumerate(pulses):
        if p['matching_ids']!=[1]:continue
        train=pulses[i:i+len(expected)]
        if len(train)!=len(expected) or any(len(x['matching_ids'])!=1 for x in train):continue
        if sorted(x['matching_ids'][0] for x in train)!=expected:continue
        by={x['matching_ids'][0]:x for x in train}
        if all(by[a]['sample_id']<by[b]['sample_id'] for a,b in precedence):candidates.append(train)
    assert len(candidates)==1,('Require unique contiguous complete train',expected,len(candidates))
    train=candidates[0]
    return train,pulses,es

def analyze(item):
    gap=item['group']=='gap';assert item['group'] in ('gap','normal')
    r=normal.analyze(item)
    signals,checks=load(Path(r['trace']))
    train,pulses,es=decode(signals,gap);markers={p['matching_ids'][0]:p for p in train}
    onset=r['onset_sample_id'];plateau=r['plateau_sample_id']
    def measure(a,b):return metrics(signals,int(a),int(b),onset)
    def interval(a,b):return measure(markers[a]['sample_id'],markers[b]['sample_id'])
    r['marker_events']=[dict(id=p['matching_ids'][0],name=NAMES[p['matching_ids'][0]],sample_id=p['sample_id'],end_sample_id=p['end_sample_id'],width_us=p['width_us'],time_ms=(p['sample_id']-onset)/FS*1000) for p in train]
    r['marker_rule']='Unique contiguous pulse train containing each ID exactly once; normal1..10, gap1..12. abs(width_us-(2*ID+0.24))<=0.80 at native0.5us grid. Gap requires3<11<12<4<5; all unmatched edges retained.'
    r['unclassified_gpi0_edges']=len(es)-2*len(train)
    r['unclassified_pulses']=[p for p in pulses if p not in train]
    windows={
      'camera_strobe_to_frame_IRQ':interval(2,3),
      'SD_initialization':interval(4,5),
      'SCR_scan_write_preparation':interval(5,6),
      'slot_transport':interval(6,7)}
    if gap:
        windows['camera_strobe_to_validated_STOP']=interval(2,11)
        windows['frame_IRQ_to_validated_STOP']=interval(3,11)
        windows['gap_full']=interval(11,12)
        assert 190<=windows['gap_full']['duration_ms']<=215,'200ms nominal gap should stay within explicit bounded expectation'
        a=markers[12]['sample_id']-FS//10
        assert a>=markers[11]['sample_id']+FS//40
        windows['gap_last100ms']=measure(a,markers[12]['sample_id'])
        windows['gap_end_to_SD_init_hook']=interval(12,4)
        r['gap_boundary_qualification']='Direct native GPIO11/12 rising edges; no200ms subtraction or DWT-clock inference. Marker11 follows full-frame validation and sensor STOP; it is not the hardware STOP edge itself.'
        r['gap_baseline_scope']='All board loads remain powered. Sensor has completed STOP, PHY power-down is intended, and SD is electrically powered but not initialized; not a measurement of SD-only idle current.'
    else:
        r['gap_boundary_qualification']='No gap markers. Exact sensor STOP timing is not observed in these cold normal traces; do not substitute frame IRQ for STOP.'
    # Repartition actual event order, including new gap markers.
    points={onset+10000:'post5ms_begin',plateau:'low_plateau'}
    for e in r['marker_events']:
        if onset+10000<=e['sample_id']<plateau:points[e['sample_id']]=e['name']
    segments=[];ss=sorted(points.items())
    for (a,aa),(b,bb) in zip(ss,ss[1:]):
        if b>a:segments.append(dict(name=aa+' -> '+bb,**measure(a,b)))
    assert abs(sum(s['energy_mJ'] for s in segments)-r['post5ms_to_plateau']['energy_mJ'])<1e-7
    r['segments_disjoint']=segments
    for name,w in windows.items():
        w['peaks_1ms']=normal.peak_windows(signals,w['start_sample_id'],w['end_sample_id_exclusive'],onset,1,segments) if w['duration_ms']>=1 else []
        w['peaks_10ms']=normal.peak_windows(signals,w['start_sample_id'],w['end_sample_id_exclusive'],onset,10,segments) if w['duration_ms']>=10 else []
    r['gap_phase_windows_overlapping_not_additive']=windows
    r['peaks_1ms']=normal.peak_windows(signals,onset+10000,plateau,onset,1,segments)
    r['peaks_10ms']=normal.peak_windows(signals,onset+10000,plateau,onset,10,segments)
    r['analysis_source_sha256']=sha(SOURCE)
    r['qualification']+=' Gap is a diagnostic scheduling change, not a selected energy optimization. Peak comparisons use1ms/10ms mean windows, never native extrema.'
    (HERE/(item['run']+'-analysis.json')).write_text(json.dumps(r,indent=2)+'\n')
    return r

def summarize(runs):
    rows=[]
    for r in runs:
        phase=r['gap_phase_windows_overlapping_not_additive'];total=r['post5ms_to_plateau']
        row=dict(run=r['run'],group=r['group'],post5ms_energy_mJ=total['energy_mJ'],onset_to_plateau_ms=r['whole_cycle_raw_unqualified']['duration_ms'],first_strobe_ms=next(x['time_ms'] for x in r['marker_events'] if x['id']==2),peak_1ms_mA=r['peaks_1ms'][0]['current_mean_mA'],peak_1ms_at_ms=r['peaks_1ms'][0]['start_ms'],peak_10ms_mA=r['peaks_10ms'][0]['current_mean_mA'],SD_init_ms=phase['SD_initialization']['duration_ms'],scan_prep_ms=phase['SCR_scan_write_preparation']['duration_ms'],slot_ms=phase['slot_transport']['duration_ms'])
        if r['group']=='gap':row.update(gap_ms=phase['gap_full']['duration_ms'],gap_last100ms_mean_mA=phase['gap_last100ms']['current_mean_mA'],gap_energy_mJ=phase['gap_full']['energy_mJ'])
        rows.append(row)
    statistics={}
    reference_groups={'fresh_normal':[r for r in rows if r['run'] in ('control-before','control-after')],
      'gap':[r for r in rows if r['group']=='gap'],
      'historical_normal_context':[r for r in rows if r['group']=='normal' and r['run'] not in ('control-before','control-after')]}
    for group,subset in reference_groups.items():
        if not subset:continue
        statistics[group]={k:dict(mean=float(np.mean([r[k] for r in subset])),median=float(np.median([r[k] for r in subset])),min=float(min(r[k] for r in subset)),max=float(max(r[k] for r in subset))) for k in subset[0] if k not in ('run','group')}
    floor_comparisons=[]
    fresh=[r for r in runs if r['run'] in ('control-before','control-after')]
    fresh_energy=float(np.mean([r['post5ms_to_plateau']['energy_mJ'] for r in fresh])) if fresh else None
    for r in runs:
        if r['group']!='gap':continue
        phases=r['gap_phase_windows_overlapping_not_additive'];floor=phases['gap_last100ms'];items=[]
        for name in ('camera_strobe_to_validated_STOP','SD_initialization','SCR_scan_write_preparation','slot_transport'):
            q=phases[name];base_mJ=floor['power_mean']*q['duration_ms']
            items.append(dict(phase=name,duration_ms=q['duration_ms'],mean_current_mA=q['current_mean_mA'],excess_current_above_gap_mA=q['current_mean_mA']-floor['current_mean_mA'],energy_mJ=q['energy_mJ'],gap_floor_energy_for_same_duration_mJ=base_mJ,excess_energy_above_gap_mJ=q['energy_mJ']-base_mJ))
        total=r['post5ms_to_plateau']['energy_mJ'];wait=phases['gap_full']['energy_mJ']
        floor_comparisons.append(dict(run=r['run'],gap_floor_current_mA=floor['current_mean_mA'],gap_floor_power_mW=floor['power_mean']*1000,gap_full_energy_mJ=wait,post5ms_energy_mJ=total,post5ms_energy_excluding_measured_gap_mJ=total-wait,fresh_normal_reference_energy_mJ=fresh_energy,additional_energy_vs_fresh_normal_mJ=None if fresh_energy is None else total-fresh_energy,remaining_difference_after_removing_measured_gap_mJ=None if fresh_energy is None else total-wait-fresh_energy,phase_excess=items))
    report=dict(runs=rows,statistics=statistics,reference_groups={k:[r['run'] for r in v] for k,v in reference_groups.items()},gap_floor_comparisons=floor_comparisons,fresh_normal_reference_runs=[r['run'] for r in fresh],scope='Matched fresh control-before/control-after are the primary references for the two cold gap cycles. Older normal01..03 are separate historical context, never pooled into primary means/medians. First5ms excluded; all energy/means from finite native power/current windows.',
      peak_definition='Highest1ms or10ms current mean with window starts sampled every0.1ms from each queried interval start; this is a sampled search, not an exact sliding maximum. Different phase origins may produce slightly different maxima. Native instantaneous peak remains unqualified.',
      gap_definition='Direct markers11/12 after validated frame+sensorSTOP and beforeSDinit marker4. Gap baseline is last100ms before12, with electrically powered but uninitializedSD.',
      limitations=['Camera2->3 is directly comparable across all cold runs; camera2->11 is available only for gap runs and includes validation/STOP overhead.','Actual capture, SD and whole-board demand may overlap; phase attribution is temporal, not per-component power.','Excess over the quiet-gap floor subtracts whole-board mean power for an equal duration; it includes changing CPU/card/camera work and is not a measurement of a component rail or guaranteed removable energy.','Artificial waiting adds energy and changes SD startup history; it is a diagnostic experiment, not automatically a better capture policy.','Removing measured gap energy arithmetically does not predict a zero-gap implementation: ordering, timing and card startup history also changed.','Card latency/slot occupancy varies; preserve per-run data and means/medians rather than assigning all timing changes to the gap.','Native GPIO11/12 validates the gap boundary; RAM proof/readback remains separate evidence.'],
      dependencies={str(SOURCE):sha(SOURCE),**{str(normal.DEPS/n):sha(normal.DEPS/n) for n in ('analyze_warm_ablations.py','analyze_existing_baseline.py')}})
    (HERE/'gap-comparison.json').write_text(json.dumps(report,indent=2)+'\n')
    lines=['Cold SD-gap diagnostic comparison; first5ms excluded.','Run | group | energy mJ | onset->plateau ms | peak1ms mA | peak10ms mA | SD init ms | scan/prep ms | write ms']
    for r in rows:lines.append(f'{r["run"]} | {r["group"]} | {r["post5ms_energy_mJ"]:.3f} | {r["onset_to_plateau_ms"]:.3f} | {r["peak_1ms_mA"]:.3f} | {r["peak_10ms_mA"]:.3f} | {r["SD_init_ms"]:.3f} | {r["scan_prep_ms"]:.3f} | {r["slot_ms"]:.3f}')
    lines+=['',json.dumps(statistics,indent=2),'','Measured gap cost and whole-board excess above its quiet floor:',json.dumps(floor_comparisons,indent=2),'']+report['limitations']
    (HERE/'gap-comparison.txt').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines[:7]));return report

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('manifest',type=Path);args=ap.parse_args()
    items=json.loads(args.manifest.read_text());summarize([analyze(i) for i in items])
