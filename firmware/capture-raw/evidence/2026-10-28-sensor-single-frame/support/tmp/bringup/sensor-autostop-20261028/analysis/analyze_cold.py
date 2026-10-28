"""Offline native-JS analysis for normal versus sensor automatic-stop cycles.

Inputs are completed recordings only. Imports offline analysis, never a bench
runner. Marker 11 is the first host observation of autonomous sensor standby,
not the physical transition; the capture proof separately establishes that no
STOP command was issued. Native current extrema and the first 5 ms remain
unqualified. Input manifest items: run, group ('normal' or 'autostop'), trace,
and optional evidence metadata.
"""
from pathlib import Path
import argparse,importlib.util,json
import numpy as np

HERE=Path(__file__).resolve().parent
CAMPAIGN=HERE.parent
SOURCE=CAMPAIGN.parent/'ethernet-normal-20261028/analysis/analyze_cycles.py'
spec=importlib.util.spec_from_file_location('autostop_offline_normal_decoder',SOURCE)
normal=importlib.util.module_from_spec(spec);spec.loader.exec_module(normal)
normal.HERE=HERE;normal.CAMPAIGN=CAMPAIGN
FS=normal.FS;metrics=normal.metrics;load=normal.load;sha=normal.sha
NAMES=dict(normal.EVENTS)
NAMES[11]='sensor_autonomous_standby_first_observed'

def decode(signals,autostop,awake=False):
    edges=normal.edges(signals,'gpi0')
    expected=list(range(1,10 if awake else 11))
    if autostop:expected.append(11)
    pulses=[]
    for a,b in zip(edges,edges[1:]):
        if a['level']==1 and b['level']==0:
            width=(b['sample_id']-a['sample_id'])/FS*1e6
            ids=[i for i in expected if abs(width-(2*i+.24))<=.80]
            pulses.append(dict(sample_id=a['sample_id'],end_sample_id=b['sample_id'],width_us=width,matching_ids=ids))
    precedence=tuple((a,b) for a,b in normal.PRECEDENCE if a in expected and b in expected)
    if autostop:precedence+=((3,11),(11,8))
    trains=[]
    for i,p in enumerate(pulses):
        if p['matching_ids']!=[1]:continue
        train=pulses[i:i+len(expected)]
        if len(train)!=len(expected) or any(len(q['matching_ids'])!=1 for q in train):continue
        if sorted(q['matching_ids'][0] for q in train)!=expected:continue
        by={q['matching_ids'][0]:q for q in train}
        if all(by[a]['sample_id']<by[b]['sample_id'] for a,b in precedence):trains.append(train)
    assert len(trains)==1,('Require one complete contiguous phase train',expected,len(trains))
    return trains[0],pulses,edges

def analyze(item):
    assert item['group'] in ('normal','autostop')
    auto=item['group']=='autostop'
    result=normal.analyze(item)
    signals,checks=load(Path(result['trace']))
    train,pulses,edges=decode(signals,auto)
    marker={q['matching_ids'][0]:q for q in train}
    onset=result['onset_sample_id'];plateau=result['plateau_sample_id']
    measure=lambda a,b:metrics(signals,int(a),int(b),onset)
    interval=lambda a,b:measure(marker[a]['sample_id'],marker[b]['sample_id'])
    result['marker_events']=[dict(id=q['matching_ids'][0],name=NAMES[q['matching_ids'][0]],
        sample_id=q['sample_id'],end_sample_id=q['end_sample_id'],width_us=q['width_us'],
        time_ms=(q['sample_id']-onset)/FS*1000) for q in train]
    result['marker_rule']='Unique contiguous normal1..10 or autostop1..11 train; each ID once; width2*ID+0.24us +/-0.80us at native0.5us grid; normal lifecycle plus3<11<8.'
    result['unclassified_gpi0_edges']=len(edges)-2*len(train)
    result['unclassified_pulses']=[q for q in pulses if q not in train]
    windows={
        'camera_strobe_to_frame_IRQ':interval(2,3),
        'SD_initialization':interval(4,5),
        'SCR_scan_write_preparation':interval(5,6),
        'slot_transport':interval(6,7),
    }
    if auto:
        delta=(marker[11]['sample_id']-marker[3]['sample_id'])/FS*1000
        result['frame_IRQ_to_standby_observation_ms']=delta
        windows['strobe_to_standby_observation']=interval(2,11)
        if delta>=0:windows['frame_IRQ_to_standby_observation']=interval(3,11)
        result['standby_marker_qualification']='Marker11 follows the first firmware I2C observation of sensor FSM2. It is an upper bound on autonomous standby transition time, with polling/service latency. AST proof and no-STOP audit are separate required evidence.'
        # AST RAM does not survive cold Standby. Qualify the external mirror
        # using the firmware's explicit post-entry LOW transition instead.
        gpi1_edges=normal.edges(signals,'gpi1')
        pre=[e for e in gpi1_edges if marker[1]['end_sample_id']<=e['sample_id']<marker[2]['sample_id']-200]
        assert len(pre)==1 and pre[0]['level']==0,('Require explicit post-entry mirror LOW before first strobe',pre)
        scope_start=pre[0]['sample_id']+200;scope_end=marker[10]['sample_id']
        selected=[e for e in gpi1_edges if scope_start<=e['sample_id']<scope_end]
        assert selected and len(selected)%2==0
        envelopes=[]
        for rise,fall in zip(selected[::2],selected[1::2]):
            assert rise['level']==1 and fall['level']==0
            envelopes.append(dict(rise_sample_id=rise['sample_id'],fall_sample_id=fall['sample_id'],
                rise_ms=(rise['sample_id']-onset)/FS*1000,fall_ms=(fall['sample_id']-onset)/FS*1000,
                duration_ms=(fall['sample_id']-rise['sample_id'])/FS*1000))
        first_offset_us=(envelopes[0]['rise_sample_id']-marker[2]['sample_id'])/FS*1e6
        assert abs(first_offset_us)<100
        result['external_strobe']=dict(pulses=envelopes,complete_pulses=len(envelopes),first_rise_minus_phase2_us=first_offset_us,
            explicit_mirror_low_sample_id=pre[0]['sample_id'],window_begin_sample_id=scope_start,window_end_sample_id=scope_end,
            scope='PD0 mirror of PA0 IRQ after its explicit post-entry LOW transition through pre-Standby marker10. It counts observed sensor STROBE IRQ envelopes; cold AST counter proof is unavailable after Standby unless separately retained.')
    else:
        result['standby_marker_qualification']='Normal cold firmware has no sensor STOP marker. Do not substitute frame IRQ or infer an exact normal STOP tail from this waveform.'
    points={onset+FS//200:'post5ms_begin',plateau:'low_plateau'}
    for event in result['marker_events']:
        if onset+FS//200<=event['sample_id']<plateau:points[event['sample_id']]=event['name']
    segments=[];ss=sorted(points.items())
    for (a,aa),(b,bb) in zip(ss,ss[1:]):
        if b>a:segments.append(dict(name=aa+' -> '+bb,**measure(a,b)))
    assert abs(sum(q['energy_mJ'] for q in segments)-result['post5ms_to_plateau']['energy_mJ'])<1e-7
    result['segments_disjoint']=segments
    for w in windows.values():
        for width in (1,10):
            w[f'peaks_{width}ms']=normal.peak_windows(signals,w['start_sample_id'],w['end_sample_id_exclusive'],onset,width,segments) if w['duration_ms']>=width else []
    result['autostop_phase_windows_overlapping_not_additive']=windows
    result['peaks_1ms']=normal.peak_windows(signals,onset+FS//200,plateau,onset,1,segments)
    result['peaks_10ms']=normal.peak_windows(signals,onset+FS//200,plateau,onset,10,segments)
    result['analysis_sources']={str(Path(__file__).resolve()):sha(Path(__file__).resolve()),str(SOURCE):sha(SOURCE)}
    result['qualification']+=' Auto-stop frame count and autonomous FSM2 must be qualified from retained AST/sensor/STROBE evidence; the receiver snapshot and one phase2 marker cannot count all sensor exposures.'
    (HERE/(item['run']+'-analysis.json')).write_text(json.dumps(result,indent=2)+'\n')
    return result

def summarize(runs):
    rows=[]
    for r in runs:
        p=r['autostop_phase_windows_overlapping_not_additive']
        row=dict(run=r['run'],group=r['group'],post5ms_energy_mJ=r['post5ms_to_plateau']['energy_mJ'],
            onset_to_plateau_ms=r['whole_cycle_raw_unqualified']['duration_ms'],
            peak_1ms_mA=r['peaks_1ms'][0]['current_mean_mA'],peak_1ms_at_ms=r['peaks_1ms'][0]['start_ms'],
            peak_10ms_mA=r['peaks_10ms'][0]['current_mean_mA'],
            first_strobe_ms=next(x['time_ms'] for x in r['marker_events'] if x['id']==2),
            SD_init_ms=p['SD_initialization']['duration_ms'],scan_prep_ms=p['SCR_scan_write_preparation']['duration_ms'],
            slot_transport_ms=p['slot_transport']['duration_ms'])
        if 'frame_IRQ_to_standby_observation_ms' in r:row['frame_IRQ_to_standby_observation_ms']=r['frame_IRQ_to_standby_observation_ms']
        rows.append(row)
    report=dict(runs=rows,scope='Native JS analog/GPIO, finite post5ms window; powered whole-board5V input, not isolated sensor rail.',
        peak_definition='Highest1ms/10ms mean on0.1ms search grid, not instantaneous analog maximum.',
        limits=['Sensor auto-stop success and frame count require independent AST/I2C/STROBE proof and image readback.',
                'Marker11 measures first host observation of FSM2, not the instant the sensor stopped.',
                'Normal cold firmware has no STOP marker; its exact STOP tail is unavailable from GPIO alone.',
                'Do not equate a receiver snapshot frame count of one with one sensor exposure.',
                'Card timing and slot scan length vary; compare individual measured runs and retain source identity.'])
    (HERE/'autostop-comparison.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('manifest',type=Path);args=parser.parse_args()
    result=summarize([analyze(item) for item in json.loads(args.manifest.read_text())])
    print(json.dumps(result,indent=2))
