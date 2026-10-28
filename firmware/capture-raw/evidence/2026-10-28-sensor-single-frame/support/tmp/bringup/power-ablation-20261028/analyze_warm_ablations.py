"""Offline, variable-order marker decode and DWT alignment for warm RAM ablations."""
from pathlib import Path
import argparse,csv,hashlib,json
import numpy as np
from analyze_existing_baseline import FS, metrics, peak_windows, sha
BASE=Path(__file__).resolve().parent
NAMES={1:'receiver_entry',2:'first_strobe_irq_observed',3:'first_frame_complete_irq_observed',4:'sd_initialization_begin',5:'sd_initialization_complete',6:'first_slot_transport_submission',7:'slot_transport_returned_success',8:'full_slot_commit_complete',9:'sd_deinitialization_complete',11:'controlled_hold_begin',12:'controlled_hold_end'}
ANCHORS={3:'frame_done',4:'sd_begin',5:'sd_ready',6:'first_write',8:'commit_done',9:'deinit_done'}
HZ=400_000_000

def load(folder):
    result=json.loads((folder/'result.json').read_text());assert result['success']
    rows=[json.loads(x) for x in (folder/'chunks.jsonl').read_text().splitlines()]
    signals={};checks={}
    for s in ('current','voltage','power','gpi0','gpi1'):
        digital=s.startswith('gpi');rs=[r for r in rows if r['signal']==s]
        path=folder/(s+('.u1' if digital else '.f32'));assert sha(path)==result['sha256'][s]
        data=np.memmap(path,mode='r',dtype='u1' if digital else '<f4');offset=0;lengths=[]
        for j,r in enumerate(rs):
            assert r['byte_offset']==offset and r['sample_rate']==FS and r['decimate_factor']==1
            offset+=r['byte_count'];n=r['byte_count']*(8 if digital else .25);assert int(n)==n;n=int(n)
            if j+1<len(rs):
                delta=rs[j+1]['sample_id']-r['sample_id']
                assert 0<=n-delta<=7 if digital else n==delta
                if digital:n=delta
            elif digital:n=0
            lengths.append(n)
        assert offset==path.stat().st_size
        if digital:data=np.concatenate([np.unpackbits(data[r['byte_offset']:r['byte_offset']+r['byte_count']],bitorder='little')[:n] for r,n in zip(rs,lengths)])
        signals[s]=(rs[0]['sample_id'],data)
        checks[s]={'sha256':result['sha256'][s],'hash_passed':True,'contiguous':True,'first_sample_id':rs[0]['sample_id'],'analyzed_end_exclusive':rs[0]['sample_id']+len(data),'excluded_final_chunk':digital,'nonfinite':None if digital else int(np.count_nonzero(~np.isfinite(data)))}
    return signals,checks

def analyze(folder):
    verified=json.loads((folder/'capture/verified.json').read_text());assert verified['passed']
    p=dict(verified['proof']);anchors=dict(ANCHORS)
    if verified.get('power_probe'):
        p['power_hold_begin']=verified['power_probe']['hold_begin'];p['power_hold_end']=verified['power_probe']['hold_end']
        anchors.update({11:'power_hold_begin',12:'power_hold_end'})
    assert p['result']==p['sd_error']==p['cleanup_error']==p['errors']==0
    assert p['media_idle']==1 and p['initialized']==p['controller_owned']==0
    signals,checks=load(folder/'trace')
    start,v=signals['gpi0'];ei=np.flatnonzero(v[1:]!=v[:-1])+1
    edges=[{'sample_id':int(start+x),'level':int(v[x])} for x in ei]
    pulses=[]
    for a,b in zip(edges,edges[1:]):
        if a['level']==1 and b['level']==0:
            width=(b['sample_id']-a['sample_id'])/2
            ids=[i for i in NAMES if abs(width-(2*i+.24))<=.80]
            pulses.append({'start_sample_id':a['sample_id'],'end_sample_id':b['sample_id'],'width_us':width,'ids':ids})
    # Search arbitrary ordering; retain exactly one of each of the nine RAM IDs.
    trains=[]
    for expected in (list(range(1,10)),list(range(1,10))+[11,12]):
      for k in range(len(pulses)-len(expected)+1):
        t=pulses[k:k+len(expected)]
        if all(len(x['ids'])==1 for x in t) and sorted(x['ids'][0] for x in t)==expected:
            markers={x['ids'][0]:x for x in t}
            cycles={i:((p[field]-p['begin'])&0xffffffff) for i,field in anchors.items()}
            pairs=[(markers[j]['start_sample_id']-markers[i]['start_sample_id'])/(cycles[j]-cycles[i]) for i in anchors for j in anchors if cycles[j]-cycles[i]>1000000 and not (11 in markers and markers[i]['start_sample_id']<=markers[11]['start_sample_id'] and markers[j]['start_sample_id']>=markers[12]['start_sample_id'])]
            slope=float(np.median(pairs));assert abs(slope/(FS/HZ)-1)<.02
            offsets={i:markers[i]['start_sample_id']-cycles[i]*slope for i in ANCHORS}
            median=float(np.median(list(offsets.values())))
            residuals={i:(value-median)/FS*1e6 for i,value in offsets.items()}
            # GPIO follows DWT stores. Retain global drift; require all long-pair slopes within 2% nominal.
            if all(abs(z/(FS/HZ)-1)<.02 for z in pairs):trains.append((t,markers,median,residuals,slope))
    assert len(trains)==1,('waveform/proof match count',len(trains),pulses)
    train,markers,t0_float,residuals,slope=trains[0];t0=round(t0_float)
    ac=sorted((((p[field]-p['begin'])&0xffffffff),markers[i]['start_sample_id']) for i,field in anchors.items())
    def map_cycles(cyc):
        if cyc<ac[0][0]:
            aa,bb=next((aa,bb) for aa in ac for bb in ac if bb[0]-aa[0]>1000000)
            return ac[0][1]+(cyc-ac[0][0])*(bb[1]-aa[1])/(bb[0]-aa[0])
        if cyc>ac[-1][0]:return ac[-1][1]+(cyc-ac[-1][0])*slope
        return float(np.interp(cyc,[x[0] for x in ac],[x[1] for x in ac]))
    t0_float=map_cycles(0);t0=round(t0_float)
    def sample(field):return round(map_cycles((p[field]-p['begin'])&0xffffffff))
    end=sample('end')
    events=[{'id':x['ids'][0],'name':NAMES[x['ids'][0]],'sample_id':x['start_sample_id'],'time_from_runtime_begin_ms':(x['start_sample_id']-t0)/FS*1000,'width_us':x['width_us']} for x in train]
    events.sort(key=lambda x:x['sample_id'])
    # Disjoint intervals carry only temporal association; components share the same rail.
    points=[(t0,'runtime_begin')]+[(e['sample_id'],e['name']) for e in events]+[(end,'terminal')]
    points.sort();segments=[]
    for (a,an),(b,bn) in zip(points,points[1:]):
        if b<=a:continue
        m=metrics(signals,a,b,t0);m['name']=an+' → '+bn;segments.append(m)
    intervals=[]
    for name,a,b in [('runtime_to_terminal',t0,end),('strobe_to_frame',markers[2]['start_sample_id'],markers[3]['start_sample_id']),('sd_init',markers[4]['start_sample_id'],markers[5]['start_sample_id']),('after_sd_init_to_first_write',markers[5]['start_sample_id'],markers[6]['start_sample_id']),('whole_slot_transport',markers[6]['start_sample_id'],markers[7]['start_sample_id']),('frame_to_sensor_stop',sample('frame_done'),sample('camera_stop')),('sensor_start_to_stop',sample('sensor_start_begin'),sample('camera_stop')),('terminal_idle_100ms',end+int(.1*FS),end+int(.2*FS))]:
        if b>a:m=metrics(signals,a,b,t0);m['name']=name;intervals.append(m)
    if 11 in markers and 12 in markers:
        a=markers[11]['start_sample_id'];b=markers[12]['start_sample_id'];m=metrics(signals,a,b,t0);m['name']='controlled_hold_full';intervals.append(m)
        m=metrics(signals,a+int(.025*FS),b-int(.025*FS),t0);m['name']='controlled_hold_middle';intervals.append(m)
    counter_path=folder/'counters/cycle-trace.json'
    counter_info=None
    if counter_path.exists():
        c=json.loads(counter_path.read_text());assert c['status']=='complete' and c['result']==0
        for h in c['event_headers']:
            hp=BASE.parents[2]/h['path'];assert sha(hp)==h['sha256'],('event header hash',hp)
        ce={e['name']:e for e in c['events']};counter_info={'sha256':sha(counter_path),'events':[],'counter_header_hashes_verified':True,'upstream_decoder_claim':c['event_header_hashes_verified']}
        for e in c['events']:
            ss=round(map_cycles((e['ticks']-p['begin'])&0xffffffff))
            counter_info['events'].append({'name':e['name'],'ticks':e['ticks'],'sample_id_inferred':ss,'time_ms':(ss-t0)/FS*1000})
        pairs=[('slot_scan','SLOT_SCAN_BEGIN','SLOT_SCAN_DONE'),('frame_validation','FRAME_CHECK_BEGIN','FRAME_VALIDATED'),('sensor_stop_ack_wait','SENSOR_STOP_COMMAND_DONE','SENSOR_STOP_ACK_DONE'),('SD_wire_data_plus_internal_block_waits','SD_CMD25_DONE','SD_DATAEND'),('SD_final_ready','SD_WRITE_FINAL_READY_BEGIN','SD_WRITE_FINAL_READY_DONE'),('SD_acmd41','SD_ACMD41_BEGIN','SD_ACMD41_DONE')]
        for name,aa,bb in pairs:
            if aa in ce and bb in ce:
                a=round(map_cycles((ce[aa]['ticks']-p['begin'])&0xffffffff));b=round(map_cycles((ce[bb]['ticks']-p['begin'])&0xffffffff))
                if b>a:
                    m=metrics(signals,a,b,t0);m['name']=name;intervals.append(m)
    def iv(name):return next(i for i in intervals if i['name']==name)
    peaks={str(ms)+'ms':peak_windows(signals,t0,end,t0,ms,segments) for ms in (1,10)}
    proof_events=[]
    for key in ('begin','sensor_reset_begin','sensor_reset_end','sensor_start_begin','sensor_start_end','arm','frame_done','camera_stop','sd_begin','sd_ready','scan_done','slot_begin','first_write','payload_done','commit_done','deinit_done','end'):
        if p.get(key):proof_events.append({'name':key,'cycles':p[key],'time_from_runtime_begin_ms':(sample(key)-t0)/FS*1000,'nominal_400MHz_time_ms':((p[key]-p['begin'])&0xffffffff)/HZ*1000,'inferred_sample_id':sample(key)})
    result={'run':folder.name,'binary_sha256':verified['binary_sha256'],'proof_sha256':sha(folder/'capture/verified.json'),'counter_alignment':counter_info,'power_probe':verified.get('power_probe'),'power_phy':verified.get('power_phy'),'power_receiver':verified.get('power_receiver'),'scope':'Warm RAM execution; no cold boot, automatic shutdown, or complete battery-cycle comparison. Hardware verification record is retained separately.','checks':checks,'decoded_ids':[e['id'] for e in events],'events':events,'all_gpi0_edges':edges,'unclassified_gpi0_edges':len(edges)-2*len(events),'clock_alignment':{'nominal_cpu_hz':HZ,'cpu_hz_relative_to_nominal_js_clock':FS/slope,'pulse_rule':'abs(width_us - (2*ID+.24)) <= .80; first RAM pulse observed 3.0 us','method':'Piecewise linear interpolation between available GPIO/DWT anchors, including11/12 holds; extrapolation before first anchor uses earliest >1M-cycle pair. Long-pair slopes outside the controlled hold within2% nominal; hold-crossing pairs excluded for possible sleep. Global median-pair slope and residuals are diagnostics, not a constant-clock assertion.','inferred_runtime_begin_sample':t0,'anchor_residual_us':residuals},'proof_events':proof_events,'segments':segments,'intervals_overlapping_not_additive':intervals,'peaks':peaks,'slot':p['slot'],'scan_headers':p['scan_headers'],'transport_mode':verified['magic_format']['stream']['mode'],'initial_available_bytes':verified['magic_format']['stream']['initial_available_bytes'],'write_sectors':p['written_sectors'],'exposure_us':verified['magic_format']['sensor']['exposure_us'],'sensor_stop_ms':(sample('camera_stop')-t0)/FS*1000,'independent_sd_readback_claimed_here':False,'energy_qualification':'Compared windows finite and contiguous. Whole recording startup NaNs retained. The duty cycle is warm/awake and has a different SD power-up history from the cold baseline.'}
    # Profile is native data averaged into 1 ms bins, not peak values.
    profile=[]
    for a in range(t0,end+int(.1*FS)-1999,2000):
        m=metrics(signals,a,a+2000,t0);profile.append({'run':folder.name,'time_ms':(a+1000-t0)/FS*1000,'current_mean_mA':m['current_mean_mA'],'voltage_mean_V':m['voltage_mean']})
    return result,profile

def main():
    ap=argparse.ArgumentParser();ap.add_argument('runs',nargs='*');args=ap.parse_args()
    runs=args.runs or [p.name for p in BASE.iterdir() if p.is_dir() and (p/'trace/result.json').exists() and (p/'capture/verified.json').exists()]
    results=[];profiles=[]
    for name in sorted(runs):
        r,profile=analyze(BASE/name);results.append(r);profiles.extend(profile)
        (BASE/(name+'-aligned-analysis.json')).write_text(json.dumps(r,indent=2)+'\n')
        print(json.dumps({'run':name,'ids':r['decoded_ids'],'alignment':r['clock_alignment'],'intervals':r['intervals_overlapping_not_additive'],'peaks':{k:v[0] for k,v in r['peaks'].items()}},indent=2))
    (BASE/'warm-ram-analysis.json').write_text(json.dumps(results,indent=2)+'\n')
    if profiles:
        with (BASE/'warm-ram-current-1ms.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(profiles[0]));w.writeheader();w.writerows(profiles)
if __name__=='__main__':main()






