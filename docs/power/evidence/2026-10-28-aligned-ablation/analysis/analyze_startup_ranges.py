"""Offline fixed-range vs autorange startup comparison. No hardware APIs."""
from pathlib import Path
import argparse,csv,json
import numpy as np
from analyze_existing_baseline import FS,metrics,sha
from analyze_warm_ablations import load
BASE=Path(__file__).resolve().parent

def analyze(folder):
    res=json.loads((folder/'result.json').read_text());assert res['success']
    events=[json.loads(x) for x in (folder/'events.jsonl').read_text().splitlines()]
    assert any(x['event']=='power_on' for x in events)
    signals,checks=load(folder)
    rows=[json.loads(x) for x in (folder/'chunks.jsonl').read_text().splitlines()]
    rr=[x for x in rows if x['signal']=='current_range'];rp=folder/'current_range.u8'
    assert sha(rp)==res['sha256']['current_range']
    packed=np.memmap(rp,mode='r',dtype='u1');rs=rr[0]['sample_id'];offset=0;parts=[]
    for j,r in enumerate(rr):
        assert r['sample_rate']==FS and r['decimate_factor']==1 and r['byte_offset']==offset
        assert r['byte_count']==r['delivered_samples'];offset+=r['byte_count']
        if j+1<len(rr):
            count=rr[j+1]['sample_id']-r['sample_id'];assert 0<=r['byte_count']-count<=1
            parts.append(packed[r['byte_offset']:r['byte_offset']+count])
    assert offset==len(packed)
    rng=np.concatenate(parts)
    checks['current_range']={'sha256':res['sha256']['current_range'],'hash_passed':True,'contiguous':True,'first_sample_id':rs,'samples':len(rng),'last_chunk_excluded_for_unresolved_padding':True,'encoding':'uint4 expanded by official driver binding to one uint8 per sample; raw range codes retained'}
    st,g=signals['gpi0'];ei=np.flatnonzero(g[1:]!=g[:-1])+1;pulses=[]
    for a,b in zip(ei,ei[1:]):
        if g[a]==1 and g[b]==0:
            w=(b-a)/2;ids=[k for k in range(1,11) if abs(w-(2*k+.24))<=.8]
            pulses.append({'start':int(st+a),'end':int(st+b),'width_us':w,'ids':ids})
    candidates=[]
    for k in range(len(pulses)-9):
        t=pulses[k:k+10]
        if all(len(x['ids'])==1 for x in t) and [x['ids'][0] for x in t]==[1,2,4,3,5,6,7,8,9,10]:candidates.append(t)
    assert len(candidates)==1,('marker train',len(candidates))
    train=candidates[0];marks={x['ids'][0]:x['start'] for x in train}
    cs,current=signals['current'];a=marks[1]-FS//2;x=current[a-cs:marks[1]-cs]
    ii=np.flatnonzero(x>=.020);assert len(ii);onset=a+int(ii[0])
    before=current[onset-cs-2000:onset-cs];assert np.all(np.isfinite(before)) and abs(float(np.mean(before)))<.0001
    def win(a,b):
        m=metrics(signals,a,b,onset);rv=rng[a-rs:b-rs];assert len(rv)==b-a
        m['range_value_counts']={str(int(v)):int(n) for v,n in zip(*np.unique(rv,return_counts=True))}
        iv=current[a-cs:b-cs];m['charge_mC']=float(np.sum(iv,dtype=np.float64)/FS*1000)
        m['negative_charge_mC']=float(np.sum(iv[iv<0],dtype=np.float64)/FS*1000)
        return m
    startup=win(onset,onset+10000);raw0=onset-2000;raw1=onset+20000
    rsub=rng[raw0-rs:raw1-rs];changes=np.flatnonzero(rsub[1:]!=rsub[:-1])+1
    transitions=[{'sample_id':int(raw0+i),'time_from_onset_us':(raw0+i-onset)/2,'before':int(rsub[i-1]),'after':int(rsub[i])} for i in changes]
    peakidx=onset+int(np.argmax(current[onset-cs:onset-cs+10000]));vs,voltage=signals['voltage'];ps,power=signals['power']
    peak={'sample_id':peakidx,'time_us':(peakidx-onset)/2,'current_A':float(current[peakidx-cs]),'voltage_V':float(voltage[peakidx-vs]),'power_W':float(power[peakidx-ps]),'raw_range_code':int(rng[peakidx-rs])}
    hundred=[win(onset+j*200,onset+(j+1)*200) for j in range(50)]
    millis=[win(onset+j*2000,onset+(j+1)*2000) for j in range(5)]
    trace=[]
    for j in range(-100,600):
        a=onset+j*20;b=a+20;z=win(a,b)
        trace.append({'time_us':(j+.5)*10,'current_mean_A':z['current_mean'],'voltage_mean_V':z['voltage_mean'],'charge_mC':z['charge_mC'],'range_codes':','.join(z['range_value_counts'])})
    result={'run':folder.name,'recorded_on_range_setting':res['on_range'],'stream_range_codes':{'0':'10A','1':'2A','2':'180mA','3':'18mA','4':'1.8mA','5':'180uA','6':'18uA','7':'OFF'},'range_code_sources':['https://joulescope.readthedocs.io/en/latest/api/stream_buffer.html','https://github.com/jetperch/pyjoulescope/blob/main/joulescope/parameters_v1.py'],'control_setting_distinction':'Control select1=fixed10A,128=auto,0=OFF; streamcode0=10A and7=OFF.','settings_before':res['initial_settings'],'settings_restored':res['restored_settings'],'checks':checks,'marker_ids':[x['ids'][0] for x in train],'marker_events':[{'id':x['ids'][0],'sample_id':x['start'],'time_from_onset_ms':(x['start']-onset)/FS*1000,'width_us':x['width_us']} for x in train],'current_onset_sample_id':onset,'onset_definition':'First >=20mA sample within500ms before phase1, with prior1ms average absolute level<100uA; not independently measured power-good.','first5ms_raw':startup,'first5ms_native_peak_unqualified':peak,'range_transitions_minus1_to_plus10ms':transitions,'first5ms_100us_windows':hundred,'first5ms_1ms_windows':millis,'post5ms_to_preWFI':win(onset+10000,marks[10]),'first5ms_qualified':False,'interpretation_limits':['Native amplitudes, negative current and input-voltage extremes remain observations, not proof of physical DUT inrush or clipping.','Fixed range removes ongoing autoranging but does not independently calibrate startup, insertion effects, clipping or source/target voltage separation.','Current range samples are aligned by native sample_id, not callback order; the current stream starts earlier than range/voltage/power.','Range-code transition proximity does not by itself prove the transient is an instrument artifact.','Whole-session initial NaNs remain; scoped windows are finite. No independent SD readback is claimed by this analyzer.']}
    return result,trace

def main():
    ap=argparse.ArgumentParser();ap.add_argument('runs',nargs='*');args=ap.parse_args();names=args.runs
    if not names:
        for p in BASE.iterdir():
            if p.is_dir() and (p/'current_range.u8').exists() and (p/'result.json').exists():
                events=[json.loads(x) for x in (p/'events.jsonl').read_text().splitlines()]
                if any(x['event']=='power_on' for x in events):names.append(p.name)
    results=[];profiles=[]
    for name in names:
        r,trace=analyze(BASE/name);results.append(r);profiles.extend([{'run':name,**x} for x in trace]);(BASE/(name+'-startup-analysis.json')).write_text(json.dumps(r,indent=2)+'\n')
        print(json.dumps({k:r[k] for k in ['run','recorded_on_range_setting','first5ms_raw','first5ms_native_peak_unqualified','range_transitions_minus1_to_plus10ms']},indent=2))
    (BASE/'startup-range-comparison.json').write_text(json.dumps(results,indent=2)+'\n')
    if profiles:
        with (BASE/'startup-range-profile-10us.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(profiles[0]));w.writeheader();w.writerows(profiles)
if __name__=='__main__':main()


