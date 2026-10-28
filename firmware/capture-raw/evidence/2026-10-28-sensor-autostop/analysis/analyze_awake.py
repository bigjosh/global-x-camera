"""Bind completed warm RAM capture proof to native JS phase and STROBE traces.

This file reads recordings only. It never imports a bench controller. The normal
STOP timestamp is an acknowledged software observation; automatic FSM2 is a
polling observation. PD0 mirrors the PA0 IRQ and is not a direct sensor probe.
"""
from pathlib import Path
import argparse,json,struct
import numpy as np
from analyze_cold import HERE,FS,load,metrics,sha,decode,NAMES,normal

FIELDS=('magic version words state error config_begin config_end repeat_readback '
    'next_readback counter_before start_begin start_end frame_cycles wait_begin fsm2_observed_cycles '
    'counter_at_stop strobes_at_frame strobes_at_stop explicit_stop_writes poll_attempts last_fsm '
    'last_ack stable_begin stable_end stable_fsm stable_counter stable_strobes stable_strobe_level '
    'receiver_frames sensor_delta flags timeout_cycles initial_strobes mirror_active '
    'reserved34 reserved35 reserved36 reserved37 reserved38 reserved39').split()
elapsed=lambda end,start:(end-start)&0xffffffff

def analyze(run,autostop=False):
    run=Path(run);vp=run/'capture/verified.json';v=json.loads(vp.read_text());assert v['passed']
    p=v['proof'];assert json.loads((run/'capture/proof.json').read_text())==p
    assert p['result']==p['errors']==p['sd_error']==p['cleanup_error']==0
    assert p['media_idle']==1 and p['initialized']==p['controller_owned']==0
    assert p['written_sectors']==3730 and p['frames']==1 and p['camera_ready']==1909600
    assert v['board_eth']['qualified_powerdown']
    assert sha(run/'capture/bootstrap/executable-readback.bin')==v['binary_sha256']
    a=None
    if autostop:
        rawpath=run/'capture/bootstrap/completed-sensor-autostop.bin'
        raw=rawpath.read_bytes();assert len(raw)==160
        a=dict(zip(FIELDS,struct.unpack('<40I',raw)));parsed=v['sensor_autostop']
        assert all(parsed[k]==a[k] for k in FIELDS)
        assert parsed['completed'] and parsed['attempted']
        assert (a['magic'],a['version'],a['words'],a['state'],a['error'])==(0x41535431,1,40,4,0)
        assert (a['repeat_readback'],a['next_readback'],a['counter_before'],a['explicit_stop_writes'])==(1,4,0,0)
        assert a['counter_at_stop']==a['stable_counter']==a['sensor_delta']
        assert a['strobes_at_stop']==a['stable_strobes'] and a['initial_strobes']==0
        assert a['last_fsm']==a['stable_fsm']==2 and a['last_ack']==a['stable_strobe_level']==0
        assert a['receiver_frames']==1 and a['flags']==15
    signals,checks=load(run/'trace');train,pulses,edges=decode(signals,autostop,awake=True)
    marker={q['matching_ids'][0]:q for q in train}
    anchors={3:p['frame_done'],4:p['sd_begin'],5:p['sd_ready'],6:p['first_write'],8:p['commit_done'],9:p['deinit_done']}
    if autostop:anchors[11]=a['fsm2_observed_cycles']
    cycles={i:elapsed(t,p['begin']) for i,t in anchors.items()}
    slopes=[(marker[b]['sample_id']-marker[c]['sample_id'])/(cycles[b]-cycles[c])
            for c in anchors for b in anchors if cycles[b]-cycles[c]>1000000]
    slope=float(np.median(slopes));assert all(abs(s/(FS/400000000)-1)<.02 for s in slopes)
    origin=float(np.median([marker[i]['sample_id']-cycles[i]*slope for i in anchors]))
    residual={i:(marker[i]['sample_id']-(origin+cycles[i]*slope))/FS*1e6 for i in anchors}
    assert max(abs(x) for x in residual.values())<100
    points=sorted((cycles[i],marker[i]['sample_id']) for i in anchors)
    def sample(tick):
        t=elapsed(tick,p['begin'])
        if t<points[0][0]:return round(points[0][1]+(t-points[0][0])*slope)
        if t>points[-1][0]:return round(points[-1][1]+(t-points[-1][0])*slope)
        return round(float(np.interp(t,[q[0] for q in points],[q[1] for q in points])))
    def measure(start,end):
        assert end>=start
        return metrics(signals,int(start),int(end),round(origin))
    stop=sample(a['fsm2_observed_cycles'] if autostop else p['camera_stop'])
    windows={
        'strobe_to_frame_IRQ':measure(marker[2]['sample_id'],marker[3]['sample_id']),
        'strobe_to_sensor_stop_observation':measure(marker[2]['sample_id'],stop),
        'frame_IRQ_to_sensor_stop_observation':measure(marker[3]['sample_id'],stop),
        'SD_init':measure(marker[4]['sample_id'],marker[5]['sample_id']),
        'scan_prep':measure(marker[5]['sample_id'],marker[6]['sample_id']),
        'slot_transport':measure(marker[6]['sample_id'],marker[7]['sample_id']),
        'runtime_begin_to_completion':measure(round(origin),sample(p['end']))}
    if stop<marker[6]['sample_id']:windows['sensor_stopped_to_transport']=measure(stop,marker[6]['sample_id'])
    segments=[dict(name=k,**q) for k,q in windows.items()]
    for q in windows.values():
        for width in (1,10):q[f'peaks_{width}ms']=normal.peak_windows(signals,q['start_sample_id'],q['end_sample_id_exclusive'],round(origin),width,segments) if q['duration_ms']>=width else []
    mapped={k:dict(tick=p[k],sample_id_inferred=sample(p[k]),time_ms=(sample(p[k])-origin)/FS*1000)
        for k in ('begin','sensor_reset_begin','sensor_reset_end','sensor_start_begin','sensor_start_end','arm','frame_done','camera_stop','sd_begin','sd_ready','scan_done','first_write','payload_done','commit_done','deinit_done','end')}
    startup=dict(first_strobe_phase2_from_runtime_begin_ms=(marker[2]['sample_id']-origin)/FS*1000,
        receiver_entry_phase1_from_runtime_begin_ms=(marker[1]['sample_id']-origin)/FS*1000,
        receiver_entry_to_first_strobe_ms=(marker[2]['sample_id']-marker[1]['sample_id'])/FS*1000,
        sensor_START_begin_from_runtime_begin_DWT_nominal_ms=elapsed(p['sensor_start_begin'],p['begin'])/400000,
        sensor_START_end_from_runtime_begin_DWT_nominal_ms=elapsed(p['sensor_start_end'],p['begin'])/400000,
        scope='Warm runtime only. First STROBE uses the identical phase2 IRQ marker and same-run GPIO/DWT-fitted runtime origin; not a cold button-to-exposure measurement.')
    if autostop:
        startup.update(config_begin_from_runtime_begin_DWT_nominal_ms=elapsed(a['config_begin'],p['begin'])/400000,
            config_end_from_runtime_begin_DWT_nominal_ms=elapsed(a['config_end'],p['begin'])/400000,
            config_write_readback_cost_DWT_nominal_ms=elapsed(a['config_end'],a['config_begin'])/400000,
            config_write_readback_cost_JS_aligned_ms=(sample(a['config_end'])-sample(a['config_begin']))/FS*1000,
            config_scope='Additional pre-START repeat/next writes and repeat/next/frame-counter readbacks; time from AST.config_begin through AST.config_end, before any START.')
    strobe=None
    if autostop:
        all_edges=normal.edges(signals,'gpi1');start=sample(a['mirror_active']);end=sample(a['stable_end'])
        # Allow 100 us alignment uncertainty before the first exposure, but the
        # complete LOW interval is proven in recorded samples, not assumed.
        first_expected=marker[2]['sample_id'];gstart,levels=signals['gpi1']
        low_start=start+int(.0001*FS);low_end=first_expected-int(.0001*FS)
        assert low_end>low_start and np.all(levels[low_start-gstart:low_end-gstart]==0)
        selected=[e for e in all_edges if low_start<=e['sample_id']<=end]
        assert selected and selected[0]['level']==1 and selected[-1]['level']==0
        assert len(selected)%2==0
        envelopes=[]
        for rise,fall in zip(selected[::2],selected[1::2]):
            assert rise['level']==1 and fall['level']==0 and fall['sample_id']>rise['sample_id']
            envelopes.append(dict(rise_sample_id=rise['sample_id'],fall_sample_id=fall['sample_id'],
                rise_ms=(rise['sample_id']-origin)/FS*1000,fall_ms=(fall['sample_id']-origin)/FS*1000,
                duration_ms=(fall['sample_id']-rise['sample_id'])/FS*1000))
        alignment_us=(selected[0]['sample_id']-first_expected)/FS*1e6
        assert abs(alignment_us)<100
        strobe=dict(window_begin_sample_id=low_start,window_end_sample_id=end,
            mirror_activation_inferred_sample_id=start,pre_first_strobe_low_proven=True,
            pulses=envelopes,external_complete_pulses=len(envelopes),first_rise_minus_phase2_us=alignment_us,
            external_count_matches_IRQ_count=len(envelopes)==a['stable_strobes'],
            external_count_matches_sensor_counter=len(envelopes)==a['stable_counter'],
            exact_one_exposure_observed=len(envelopes)==a['stable_strobes']==a['stable_counter']==1,
            startup_edges_excluded=[e for e in all_edges if e['sample_id']<low_start],
            scope='PD0 mirror of PA0 EXTI interrupts after explicit activation, through stable post-save sensor observation. Boot HIGH/chatter excluded. This confirms IRQ waveform/count externally, not independent direct PA0 electrical capture.')
    profile=[]
    for start in range(round(origin),sample(p['end'])+FS//10-1999,2000):
        q=measure(start,start+2000);profile.append(dict(time_ms=(start+1000-origin)/FS*1000,current_mA=q['current_mean_mA']))
    out=dict(run=run.name,group='autostop' if autostop else 'normal',verification_path=str(vp),verification_sha256=sha(vp),
        binary_sha256=v['binary_sha256'],checks=checks,ast=a,
        markers=[dict(id=q['matching_ids'][0],name=NAMES[q['matching_ids'][0]],**q) for q in train],
        unclassified_gpi0_edges=len(edges)-2*len(train),unclassified_pulses=[q for q in pulses if q not in train],
        clock_alignment=dict(JS_samples_per_DWT_tick=slope,origin_sample=origin,global_fit_anchor_residual_us=residual,
            mapping='Piecewise linear between actual same-run GPIO/DWT anchors, local extrapolation outside; inferred timestamp allowance100us.'),
        mapped_proof_events=mapped,startup=startup,windows_overlapping_not_additive=windows,external_strobe=strobe,
        DWT_frame_to_stop_observation_ms=elapsed(a['fsm2_observed_cycles'] if autostop else p['camera_stop'],p['frame_done'])/400000,
        scope='Warm RAM, no cold power-on or Standby. All currents include populated board and card. Source-image equality is separate evidence. Normal STOP and automatic FSM2 are software observations, not exact sensor transitions.',
        source_sha256=sha(Path(__file__)))
    (HERE/(run.name+'-awake-analysis.json')).write_text(json.dumps(out,indent=2)+'\n')
    (HERE/(run.name+'-awake-profile.json')).write_text(json.dumps(profile,indent=2)+'\n')
    print(json.dumps(dict(run=run.name,frame_to_stop_ms=out['DWT_frame_to_stop_observation_ms'],windows={k:{f:q[f] for f in ('duration_ms','current_mean_mA','energy_mJ')} for k,q in windows.items()},external_strobe=strobe),indent=2))
    return out

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('run',type=Path);ap.add_argument('--autostop',action='store_true');args=ap.parse_args()
    analyze(args.run,args.autostop)
