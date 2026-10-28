"""Separate cold-awake FLASH analysis; it never admits an absent Standby marker.

Only saved inspection and native recorder files are read. AST schema2 means
context verification occurs after START; no schema1/prestart-counter assumption.
"""
from pathlib import Path
import argparse,json,struct
import numpy as np
from analyze_promotion import HERE,FS,load,metrics,sha,prior

FIELDS=('magic version words state error config_begin config_end repeat_readback '
    'next_readback counter_before start_begin start_end frame_cycles wait_begin fsm2_observed_cycles '
    'counter_at_stop strobes_at_frame strobes_at_stop explicit_stop_writes poll_attempts last_fsm '
    'last_ack stable_begin stable_end stable_fsm stable_counter stable_strobes stable_strobe_level '
    'receiver_frames sensor_delta flags timeout_cycles initial_strobes mirror_active '
    'reserved34 reserved35 reserved36 reserved37 reserved38 reserved39').split()
elapsed=lambda end,start:(end-start)&0xffffffff
def relative(end,start):
    value=elapsed(end,start)
    return value if value<0x80000000 else value-0x100000000

def analyze(name,trace,verification):
    trace=Path(trace);verification=Path(verification)
    done=json.loads((trace/'result.json').read_text());assert done['success'] and not done['errors'] and not done['cleanup_errors']
    v=json.loads(verification.read_text());assert v['passed'] and v['kind']=='raw-flash-inspection'
    p=v['proof'];assert p['nonce']==0 and p['operation']==1
    assert p['result']==p['errors']==p['sd_error']==p['cleanup_error']==0
    assert p['frames']==1 and p['camera_ready']==p['dma_bytes']==p['bytes']==1909600
    assert p['media_idle']==1 and p['initialized']==p['controller_owned']==0 and p['written_sectors']==3730
    assert v['board_eth']['qualified_powerdown']
    rawpath=verification.parent/'sensor-autostop-retained.bin';raw=rawpath.read_bytes();assert len(raw)==160
    a=dict(zip(FIELDS,struct.unpack('<40I',raw)));parsed=v['sensor_autostop'];assert all(a[k]==parsed[k] for k in FIELDS)
    assert (a['magic'],a['version'],a['words'],a['state'],a['error'])==(0x41535431,2,40,4,0)
    assert (a['repeat_readback'],a['next_readback'],a['explicit_stop_writes'],a['initial_strobes'])==(1,4,0,0)
    assert a['counter_before'] in (0,1) and a['counter_at_stop']==a['stable_counter']==a['sensor_delta']==1
    assert a['strobes_at_frame']==a['strobes_at_stop']==a['stable_strobes']==a['receiver_frames']==1
    assert a['last_fsm']==a['stable_fsm']==2 and a['last_ack']==a['stable_strobe_level']==0 and a['flags']==15
    assert parsed['production_single_frame'] and parsed['exact_one_frame_observed'] and parsed['counter_and_strobe_counts_agree']
    assert parsed['readback_timing']=='post-start'
    framepath=verification.parent/'frame.bin';assert framepath.stat().st_size==1909600 and sha(framepath)==v['frame_sha256']
    signals,checks=load(trace);train,pulses,edges=prior.decode(signals,True,awake=True)
    m={q['matching_ids'][0]:q for q in train};assert set(m)==set(range(1,10))|{11} and 10 not in m
    current_start,current=signals['current'];first=m[1]['sample_id'];lo=max(current_start,first-FS//2)
    crossings=np.flatnonzero(current[lo-current_start:first-current_start]>=.020);assert len(crossings)
    onset=lo+int(crossings[0]);before=current[onset-current_start-2000:onset-current_start]
    assert len(before)==2000 and np.all(np.isfinite(before)) and abs(float(np.mean(before)))<.0001
    anchors={3:p['frame_done'],4:p['sd_begin'],5:p['sd_ready'],6:p['first_write'],8:p['commit_done'],9:p['deinit_done'],11:a['fsm2_observed_cycles']}
    cycles={i:relative(t,p['begin']) for i,t in anchors.items()}
    slopes=[(m[b]['sample_id']-m[c]['sample_id'])/(cycles[b]-cycles[c]) for c in anchors for b in anchors if cycles[b]-cycles[c]>1000000]
    slope=float(np.median(slopes));assert slopes and all(abs(s/(FS/400000000)-1)<.02 for s in slopes)
    origin=float(np.median([m[i]['sample_id']-cycles[i]*slope for i in anchors]))
    residual={i:(m[i]['sample_id']-(origin+cycles[i]*slope))/FS*1e6 for i in anchors};assert max(abs(x) for x in residual.values())<100
    points=sorted((cycles[i],m[i]['sample_id']) for i in anchors)
    def sample(tick):
        t=relative(tick,p['begin'])
        if t<points[0][0]:return round(points[0][1]+(t-points[0][0])*slope)
        if t>points[-1][0]:return round(points[-1][1]+(t-points[-1][0])*slope)
        return round(float(np.interp(t,[q[0] for q in points],[q[1] for q in points])))
    def measure(start,end):
        assert end>=start
        return metrics(signals,int(start),int(end),onset)
    activation=sample(a['mirror_active']);first_strobe=m[2]['sample_id'];low_start=activation+200;low_end=first_strobe-200
    gst,levels=signals['gpi1'];assert low_end>low_start and np.all(levels[low_start-gst:low_end-gst]==0)
    stable_end=sample(a['stable_end']);all_edges=prior.normal.edges(signals,'gpi1')
    selected=[e for e in all_edges if low_start<=e['sample_id']<=stable_end]
    assert len(selected)==2 and [e['level'] for e in selected]==[1,0]
    rise,fall=selected;assert fall['sample_id']<m[3]['sample_id']<m[11]['sample_id']
    assert abs((rise['sample_id']-first_strobe)/FS*1e6)<100
    strobe=dict(external_complete_envelopes=1,rise_ms=(rise['sample_id']-onset)/FS*1000,
        fall_ms=(fall['sample_id']-onset)/FS*1000,duration_ms=(fall['sample_id']-rise['sample_id'])/FS*1000,
        first_rise_minus_phase2_us=(rise['sample_id']-first_strobe)/FS*1e6,
        window_start_sample_id=low_start,window_end_sample_id=stable_end,activation_inferred_sample_id=activation,
        low_before_first_strobe_proven=True,counter_and_IRQ_and_external_count_all_one=True,
        scope='External PD0 mirrors PA0 IRQ; boot HIGH/chatter excluded using AST activation plus a proven LOW interval. Sensor frame counter and retained IRQ count independently both1 through save completion.')
    windows={name:measure(m[i]['sample_id'],m[j]['sample_id']) for name,i,j in [
        ('receive_frame',2,3),('frame_to_autonomous_standby_observation',3,11),('SD_init',4,5),('scan_prepare',5,6),('slot_transport',6,7)]}
    windows['post5ms_to_SD_deinit']=measure(onset+FS//200,m[9]['sample_id'])
    segments=[dict(name=k,**q) for k,q in windows.items()]
    peaks={str(width)+'ms':prior.normal.peak_windows(signals,onset+FS//200,m[9]['sample_id'],onset,width,segments) for width in (1,10)}
    profile=[]
    for start in range(onset+FS//200,m[9]['sample_id']+FS//10-1999,2000):
        q=measure(start,start+2000);profile.append(dict(time_ms=(start+1000-onset)/FS*1000,current_mA=q['current_mean_mA']))
    out=dict(run=name,kind='cold-awake-flash-analysis',trace=str(trace),verification=str(verification),
        verification_sha256=sha(verification),binary_sha256=v['binary_sha256'],raw_AST_sha256=sha(rawpath),source_frame_sha256=sha(framepath),
        AST=a,checks=checks,onset_sample_id=onset,
        marker_events=[dict(id=q['matching_ids'][0],name=prior.NAMES[q['matching_ids'][0]],time_ms=(q['sample_id']-onset)/FS*1000,**q) for q in train],
        expected_markers='IDs1..9 plus11 exactly once; no10;3<11<8 with independent SD ordering',
        unclassified_pulses=[q for q in pulses if q not in train],clock_alignment=dict(samples_per_DWT=slope,origin_sample=origin,residual_us=residual,uncertainty_allowance_us=100),
        external_strobe=strobe,windows_overlapping_not_additive=windows,highest_mean_peaks=peaks,
        context_readback_nominal_ms=elapsed(a['config_end'],a['config_begin'])/400000,
        context_readback_scope='Schema2 is post-START verification; this is not pre-START setup cost.',
        scope='Cold boot of awake FLASH candidate. Inspection binds successful image/counter/standby/idle records and frame RAM. No MCU Standby or sleep plateau is expected or inferred; SD readback remains separate.',
        first5ms_unqualified=True,source_sha256=sha(Path(__file__)))
    (HERE/(name+'-awake-analysis.json')).write_text(json.dumps(out,indent=2)+'\n')
    (HERE/(name+'-awake-profile.json')).write_text(json.dumps(profile,indent=2)+'\n')
    return out

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--run',required=True);ap.add_argument('--trace',type=Path,required=True);ap.add_argument('--verification',type=Path,required=True);args=ap.parse_args()
    r=analyze(args.run,args.trace,args.verification)
    print(json.dumps({k:r[k] for k in ('run','external_strobe','windows_overlapping_not_additive','context_readback_nominal_ms')},indent=2))
