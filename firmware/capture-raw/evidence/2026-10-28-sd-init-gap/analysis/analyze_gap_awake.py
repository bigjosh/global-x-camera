"""Independently bind saved GAP1 proof to the warm RAM GPIO/power recording."""
from pathlib import Path
import argparse,json,struct
import numpy as np
from analyze_gap import HERE,FS,load,metrics,sha,decode,NAMES,normal

FIELDS='magic version state error entry frame_done stop_done gap_begin gap_end target_cycles commands_before commands_after frame_valid stopped clock_hz reserved'.split()
def analyze(run,verification_path):
    v=json.loads(verification_path.read_text());assert v['passed']
    p=v['proof'];assert json.loads((run/'capture/proof.json').read_text())==p
    assert p['result']==p['errors']==p['sd_error']==p['cleanup_error']==0
    assert p['media_idle']==1 and p['initialized']==p['controller_owned']==0
    assert p['written_sectors']==3730 and p['frames']==1 and p['camera_ready']==1909600
    assert v['board_eth']['qualified_powerdown']
    assert sha(run/'capture/bootstrap/executable-readback.bin')==v['binary_sha256']
    rawpath=run/'capture/bootstrap/completed-sd-init-gap.bin';raw=rawpath.read_bytes();assert len(raw)==64
    g=dict(zip(FIELDS,struct.unpack('<16I',raw)))
    parsed=v['sd_init_gap'];assert all(parsed[k]==g[k] for k in FIELDS)
    assert parsed['completed'] and parsed['attempted']
    assert (g['magic'],g['version'],g['state'],g['error'],g['target_cycles'],g['clock_hz'])==(0x31504147,1,3,0,80000000,400000000)
    assert g['commands_before']==g['commands_after']==g['reserved']==0
    assert g['frame_valid']==g['stopped']==1 and g['frame_done']==p['frame_done'] and g['stop_done']==p['camera_stop']
    elapsed=lambda a,b:(a-b)&0xffffffff
    assert 80000000<=elapsed(g['gap_end'],g['gap_begin'])<100000000
    assert elapsed(g['gap_begin'],g['stop_done'])<4000000 and elapsed(p['sd_begin'],g['gap_end'])<4000000
    signals,checks=load(run/'trace');train,pulses,edges=decode(signals,True,awake=True)
    markers={q['matching_ids'][0]:q for q in train}
    anchors={3:'frame_done',4:'sd_begin',5:'sd_ready',6:'first_write',8:'commit_done',9:'deinit_done'}
    cycles={i:elapsed(p[k],p['begin']) for i,k in anchors.items()}
    slopes=[(markers[b]['sample_id']-markers[a]['sample_id'])/(cycles[b]-cycles[a]) for a in anchors for b in anchors if cycles[b]-cycles[a]>1000000]
    slope=float(np.median(slopes));assert all(abs(s/(FS/400000000)-1)<.02 for s in slopes)
    origin=float(np.median([markers[i]['sample_id']-cycles[i]*slope for i in anchors]))
    residual={i:(markers[i]['sample_id']-(origin+cycles[i]*slope))/FS*1e6 for i in anchors}
    assert max(abs(x) for x in residual.values())<100
    points=sorted((cycles[i],markers[i]['sample_id']) for i in anchors)
    def sample(tick):
        t=elapsed(tick,p['begin'])
        if t<points[0][0]:return round(points[0][1]+(t-points[0][0])*slope)
        if t>points[-1][0]:return round(points[-1][1]+(t-points[-1][0])*slope)
        return round(float(np.interp(t,[x[0] for x in points],[x[1] for x in points])))
    def measure(a,b):return metrics(signals,int(a),int(b),round(origin))
    mapped={k:dict(tick=g[k],sample_id_inferred=sample(g[k]),time_ms=(sample(g[k])-origin)/FS*1000) for k in ('entry','frame_done','stop_done','gap_begin','gap_end')}
    # Marker11 pulse finishes before GAP1.gap_begin is sampled. Marker12 rises
    # after GAP1.gap_end and final checks, so these are related, not equal times.
    begin_residual=(sample(g['gap_begin'])-markers[11]['end_sample_id'])/FS*1e6
    end_residual=(markers[12]['sample_id']-sample(g['gap_end']))/FS*1e6
    assert abs(begin_residual)<100 and abs(end_residual)<100
    windows={
      'strobe_to_frame_IRQ':measure(markers[2]['sample_id'],markers[3]['sample_id']),
      'strobe_to_STOP_proof':measure(markers[2]['sample_id'],sample(g['stop_done'])),
      'frame_IRQ_to_STOP_proof':measure(markers[3]['sample_id'],sample(g['stop_done'])),
      'gap_proof':measure(sample(g['gap_begin']),sample(g['gap_end'])),
      'gap_GPIO':measure(markers[11]['sample_id'],markers[12]['sample_id']),
      'gap_last100ms':measure(markers[12]['sample_id']-FS//10,markers[12]['sample_id']),
      'SD_init':measure(markers[4]['sample_id'],markers[5]['sample_id']),
      'scan_prep':measure(markers[5]['sample_id'],markers[6]['sample_id']),
      'slot_transport':measure(markers[6]['sample_id'],markers[7]['sample_id'])}
    segments=[dict(name=k,**q) for k,q in windows.items()]
    for name,q in windows.items():
        for width in (1,10):
            q[f'peaks_{width}ms']=normal.peak_windows(signals,q['start_sample_id'],q['end_sample_id_exclusive'],round(origin),width,segments) if q['duration_ms']>=width else []
    overall={str(width)+'ms':normal.peak_windows(signals,round(origin),sample(p['end']),round(origin),width,segments) for width in (1,10)}
    profile=[]
    for a in range(round(origin),sample(p['end'])+FS//10-1999,2000):
        z=measure(a,a+2000);profile.append(dict(time_ms=(a+1000-origin)/FS*1000,current_mA=z['current_mean_mA']))
    (HERE/(run.name+'-profile.json')).write_text(json.dumps(profile,indent=2)+'\n')
    out=dict(run=run.name,verification_path=str(verification_path),verification_sha256=sha(verification_path),binary_sha256=v['binary_sha256'],raw_gap_proof_sha256=sha(rawpath),gap_proof=g,
      checks=checks,markers=[dict(id=q['matching_ids'][0],name=NAMES[q['matching_ids'][0]],**q) for q in train],all_gpi0_edges=edges,unclassified_edges=len(edges)-2*len(train),unclassified_pulses=[q for q in pulses if q not in train],
      clock_alignment=dict(JS_samples_per_DWT_tick=slope,origin_sample=origin,global_fit_anchor_residual_us=residual,mapping='Piecewise linear between actual normal GPIO/DWT anchors; local extrapolation outside. Inferred proof timestamps retain up to100us alignment allowance; GPIO11/12 boundaries are primary.',gap_begin_after_marker11_fall_residual_us=begin_residual,marker12_rise_after_gap_end_residual_us=end_residual),mapped_gap_events=mapped,windows=windows,overall_peaks=overall,
      scope='Same-run warm RAM diagnostic GAP1 independently matched to native GPIO/DWT anchors. No cold boot or Standby measurement. Card electrically powered, zero recorded SD commands through gap. Source-image/card readback remains separate evidence. STOP and proof-gap endpoints are locally interpolated with up to100us allowance, not physical edge measurements.')
    (HERE/(run.name+'-proof-aligned.json')).write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(dict(run=run.name,gap_GPIO_ms=windows['gap_GPIO']['duration_ms'],gap_proof_ms=windows['gap_proof']['duration_ms'],gap_last100ms_mA=windows['gap_last100ms']['current_mean_mA']),indent=2))
    return out

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('run',type=Path);ap.add_argument('verification',type=Path);a=ap.parse_args();analyze(a.run,a.verification)
