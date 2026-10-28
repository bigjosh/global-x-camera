"""Offline cold normal-cycle comparison. Reads traces only; never controls hardware.

Input manifest: [{"run":"baseline01", "group":"baseline", "trace":"...",
                 "evidence": {optional explicit qualification/provenance}}]
Trace paths are absolute or relative to the campaign directory. Outputs stay here.
"""
from pathlib import Path
import argparse, json, sys
import numpy as np

HERE=Path(__file__).resolve().parent
CAMPAIGN=HERE.parent
DEPS=CAMPAIGN.parent/'power-ablation-20261028'
sys.path.insert(0,str(DEPS))
from analyze_warm_ablations import load
from analyze_existing_baseline import FS, metrics, sha, peak_windows

EVENTS={1:'receiver_entry',2:'first_strobe_irq_observed',3:'first_frame_complete_irq_observed',
 4:'sd_initialization_begin',5:'sd_initialization_complete',6:'first_slot_transport_submission',
 7:'slot_transport_returned_success',8:'full_slot_commit_complete',9:'sd_deinitialization_complete',10:'pre_standby_wfi'}
PRECEDENCE=((1,2),(2,3),(1,4),(4,5),(5,6),(6,7),(3,7),(7,8),(8,9),(9,10))

def edges(signals,name):
    st,v=signals[name];ix=np.flatnonzero(v[1:]!=v[:-1])+1
    return [dict(sample_id=int(st+i),level=int(v[i])) for i in ix]

def analyze(item):
    path=Path(item['trace']);path=path if path.is_absolute() else CAMPAIGN/path
    signals,checks=load(path)
    all_edges={name:edges(signals,name) for name in ('gpi0','gpi1')}
    pulses=[]
    for a,b in zip(all_edges['gpi0'],all_edges['gpi0'][1:]):
        if a['level']==1 and b['level']==0:
            width=(b['sample_id']-a['sample_id'])/FS*1e6
            ids=[i for i in EVENTS if abs(width-(2*i+.24))<=.80]
            pulses.append(dict(start_sample_id=a['sample_id'],end_sample_id=b['sample_id'],width_us=width,matching_ids=ids))
    # Permit additional wider diagnostic IDs without silently throwing away edges.
    recognized=[p for p in pulses if len(p['matching_ids'])==1]
    trains=[]
    for i,p in enumerate(recognized):
        if p['matching_ids']!=[1]:continue
        train=recognized[i:i+10]
        if len(train)!=10 or sorted(p['matching_ids'][0] for p in train)!=list(range(1,11)):continue
        by={p['matching_ids'][0]:p for p in train}
        if all(by[a]['start_sample_id']<by[b]['start_sample_id'] for a,b in PRECEDENCE):trains.append(train)
    assert len(trains)==1,('Unique complete normal marker train required',len(trains))
    train=trains[0];marker={p['matching_ids'][0]:p for p in train}
    current_start,current=signals['current'];first=marker[1]['start_sample_id']
    lo=max(current_start,first-FS//2)
    crossings=np.flatnonzero(current[lo-current_start:first-current_start]>=.020)
    assert len(crossings)
    onset=lo+int(crossings[0]);pre=current[onset-current_start-2000:onset-current_start]
    assert len(pre)==2000 and np.all(np.isfinite(pre)) and abs(float(np.mean(pre)))<.0001
    wfi_end=marker[10]['end_sample_id'];bin0=((wfi_end+1999)//2000)*2000
    stop=min(bin0+2*FS,current_start+len(current));nb=(stop-bin0)//2000
    bins=current[bin0-current_start:bin0-current_start+nb*2000].reshape(nb,2000).mean(axis=1,dtype=np.float64)
    good=(bins>.006)&(bins<.012)
    candidates=np.flatnonzero(np.convolve(good.astype(int),np.ones(10,dtype=int),'valid')==10)
    assert len(candidates),'No matching stable low-current plateau'
    plateau=bin0+int(candidates[0])*2000
    def measure(a,b):return metrics(signals,int(a),int(b),onset)
    events=[dict(id=p['matching_ids'][0],name=EVENTS[p['matching_ids'][0]],sample_id=p['start_sample_id'],end_sample_id=p['end_sample_id'],time_ms=(p['start_sample_id']-onset)/FS*1000,width_us=p['width_us']) for p in train]
    # Disjoint slices follow actual order, rather than presuming init is slower than exposure.
    pointmap={onset+10000:'post5ms_begin',plateau:'low_plateau'}
    for e in events:
        if onset+10000<=e['sample_id']<plateau:pointmap[e['sample_id']]=e['name']
    points=sorted(pointmap.items());segments=[]
    for (a,an),(b,bn) in zip(points,points[1:]):
        if b>a:segments.append(dict(name=an+' -> '+bn,**measure(a,b)))
    total=measure(onset+10000,plateau)
    assert abs(sum(s['energy_mJ'] for s in segments)-total['energy_mJ'])<1e-7
    windows={}
    definitions=[('receiver_to_strobe',1,2),('strobe_to_frame_complete',2,3),('SD_initialization',4,5),('SD_ready_to_first_submission',5,6),('slot_transport',6,7),('post_transport_commit',7,8),('storage_deinit',8,9),('cleanup_to_pre_WFI',9,10)]
    for name,a,b in definitions:windows[name]=measure(marker[a]['start_sample_id'],marker[b]['start_sample_id'])
    windows['pre_WFI_to_low_plateau']=measure(marker[10]['start_sample_id'],plateau)
    overlap=max(0,min(marker[3]['start_sample_id'],marker[5]['start_sample_id'])-max(marker[2]['start_sample_id'],marker[4]['start_sample_id']))/FS*1000
    profile=[]
    for a in range(onset+10000,plateau+int(.05*FS)-1999,2000):
        m=measure(a,a+2000);profile.append(dict(time_ms=(a+1000-onset)/FS*1000,current_mA=m['current_mean_mA'],power_mW=m['power_mean']*1000))
    r=dict(run=item['run'],group=item['group'],trace=str(path),evidence=item.get('evidence',{}),result_sha256=sha(path/'result.json'),checks=checks,
      marker_events=events,marker_precedence_pass=True,unique_marker_train=True,
      marker_rule='Protocol2: abs(width_us - (2*ID+0.24)) <=0.80, native0.5us grid; unique IDs1..10 plus semantic precedence, arbitrary permitted ordering.',
      all_gpi_edges=all_edges,unclassified_gpi0_edges=len(all_edges['gpi0'])-20,unclassified_pulses=[p for p in pulses if p not in train],
      onset_sample_id=onset,onset_definition='First >=20mA native sample in500ms before receiver marker; preceding1ms finite with absolute mean<100uA.',
      plateau_sample_id=plateau,plateau_definition='First whole1ms bin after marker10 with10 consecutive bin means6..12mA;1ms endpoint resolution.',
      first5ms_raw_unqualified=measure(onset,onset+10000),whole_cycle_raw_unqualified=measure(onset,plateau),
      post5ms_to_plateau=total,post5ms_to_pre_WFI=measure(onset+10000,marker[10]['start_sample_id']),
      low_plateau_100ms=measure(plateau,plateau+FS//10),segments_disjoint=segments,phase_windows_overlapping_not_additive=windows,
      capture_SD_init_overlap_ms=overlap,peaks_1ms=peak_windows(signals,onset+10000,plateau,onset,1,segments),
      whole_session_finite=all(checks[s]['nonfinite']==0 for s in ('current','voltage','power')),
      qualification='Post5ms window finite/contiguous, native power integrated; first5ms and whole-cycle integrals remain provisional. Markers establish firmware observations, not independent image integrity or Standby flags.',
      limits=['Input-side JS voltage, not target voltage after sense/wire drops.','Final packed GPIO chunk excluded; all remaining unmatched edges preserved.','Normal flash cycles include camera, card and populated Nucleo support loads.','Card initialization, slot scan and write latency can vary; report each run and interval rather than attributing every time change to PHY power-down.','Native extrema are retained but not qualified physical peaks.'])
    (HERE/(item['run']+'-analysis.json')).write_text(json.dumps(r,indent=2)+'\n')
    (HERE/(item['run']+'-profile.json')).write_text(json.dumps(profile,indent=2)+'\n')
    return r

def summarize(runs):
    groups={}
    for name in sorted({r['group'] for r in runs}):
        selected=[r for r in runs if r['group']==name]
        rows=[]
        for r in selected:
            p=r['post5ms_to_plateau'];ph=r['phase_windows_overlapping_not_additive']
            rows.append(dict(run=r['run'],post5ms_energy_mJ=p['energy_mJ'],post5ms_duration_ms=p['duration_ms'],post5ms_mean_power_mW=p['power_mean']*1000,cycle_onset_to_plateau_ms=r['whole_cycle_raw_unqualified']['duration_ms'],strobe_from_onset_ms=next(e['time_ms'] for e in r['marker_events'] if e['id']==2),SD_init_ms=ph['SD_initialization']['duration_ms'],SD_ready_to_first_submission_ms=ph['SD_ready_to_first_submission']['duration_ms'],slot_transport_ms=ph['slot_transport']['duration_ms'],slot_transport_mean_power_mW=ph['slot_transport']['power_mean']*1000,slot_transport_energy_mJ=ph['slot_transport']['energy_mJ'],plateau_mA=r['low_plateau_100ms']['current_mean_mA']))
        stats={k:dict(mean=float(np.mean([r[k] for r in rows])),median=float(np.median([r[k] for r in rows])),min=float(min(r[k] for r in rows)),max=float(max(r[k] for r in rows))) for k in rows[0] if k!='run'}
        groups[name]=dict(count=len(rows),runs=rows,statistics=stats)
    comparison=None
    if 'baseline' in groups and 'candidate' in groups:
        a=groups['baseline']['statistics'];b=groups['candidate']['statistics']
        comparison={k:dict(baseline_mean=a[k]['mean'],candidate_mean=b[k]['mean'],candidate_minus_baseline=b[k]['mean']-a[k]['mean'],reduction_percent=100*(1-b[k]['mean']/a[k]['mean']),baseline_median=a[k]['median'],candidate_median=b[k]['median'],candidate_minus_baseline_median=b[k]['median']-a[k]['median'],median_reduction_percent=100*(1-b[k]['median']/a[k]['median'])) for k in a}
    result=dict(groups=groups,comparison=comparison,repeat_plan='Three baseline and three candidate cold cycles; each run reported. No paired statistical significance or card-latency correction inferred.',
      scope='Compare post-onset5ms to measured low plateau, not whole cold-cycle energy. Run-time PHY change plus any duration/card variability remains visible.',
      input_proofs='Firmware identities and independent readback evidence are explicit input evidence only; marker decoding alone does not prove either.',
      dependencies={str(DEPS/name):sha(DEPS/name) for name in ('analyze_warm_ablations.py','analyze_existing_baseline.py')})
    (HERE/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    lines=['Normal capture PHY power comparison; native JS traces, post5ms energy only.','', 'Run | group | energy mJ | onset-to-plateau ms | SD init ms | slot transport ms | slot mean mW | plateau mA']
    for group,g in groups.items():
        for r in g['runs']:lines.append(f"{r['run']} | {group} | {r['post5ms_energy_mJ']:.3f} | {r['cycle_onset_to_plateau_ms']:.3f} | {r['SD_init_ms']:.3f} | {r['slot_transport_ms']:.3f} | {r['slot_transport_mean_power_mW']:.3f} | {r['plateau_mA']:.3f}")
    if comparison:lines+=['','Mean comparison (retain per-run SD variability):',json.dumps(comparison,indent=2)]
    (HERE/'comparison.txt').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines[:12]))
    return result

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('manifest',type=Path);a=ap.parse_args()
    items=json.loads(a.manifest.read_text());runs=[analyze(item) for item in items]
    summarize(runs)
