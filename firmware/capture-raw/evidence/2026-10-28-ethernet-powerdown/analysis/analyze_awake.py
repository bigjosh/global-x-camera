"""Offline matched awake evidence; separate from normal cold-cycle totals."""
import json, struct
from pathlib import Path
import numpy as np
from analyze_cycles import HERE, CAMPAIGN, FS, load, metrics, sha, edges, EVENTS

ANCHORS={3:'frame_done',4:'sd_begin',5:'sd_ready',6:'first_write',8:'commit_done',9:'deinit_done'}
def analyze(name,verification):
    run=CAMPAIGN/name;v=json.loads(verification.read_text());assert v['passed']
    p=v['proof'];original=json.loads((run/'capture/proof.json').read_text());assert original==p
    assert p['result']==p['sd_error']==p['cleanup_error']==p['errors']==0
    assert p['media_idle']==1 and p['initialized']==p['controller_owned']==0
    assert p['frames']==1 and p['written_sectors']==3730 and p['camera_ready']==1909600
    plan=json.loads((run/'capture/plan.json').read_text());assert plan['binary_sha256']==v['binary_sha256']
    build=Path(plan['build']);m=json.loads((build/'manifest.json').read_text())
    assert sha(run/'capture/bootstrap/executable-readback.bin')==v['binary_sha256']
    signals,checks=load(run/'trace');es=edges(signals,'gpi0');pulses=[]
    for a,b in zip(es,es[1:]):
        if a['level']==1 and b['level']==0:
            width=(b['sample_id']-a['sample_id'])/FS*1e6
            ids=[i for i in range(1,10) if abs(width-(2*i+.24))<=.80]
            pulses.append(dict(sample_id=a['sample_id'],end_sample_id=b['sample_id'],width_us=width,ids=ids))
    good=[q for q in pulses if len(q['ids'])==1];trains=[]
    for i,q in enumerate(good):
        t=good[i:i+9]
        if q['ids']==[1] and len(t)==9 and sorted(x['ids'][0] for x in t)==list(range(1,10)):trains.append(t)
    assert len(trains)==1
    train=trains[0];marker={q['ids'][0]:q['sample_id'] for q in train}
    cycles={i:(p[field]-p['begin'])&0xffffffff for i,field in ANCHORS.items()}
    slopes=[(marker[b]-marker[a])/(cycles[b]-cycles[a]) for a in ANCHORS for b in ANCHORS if cycles[b]-cycles[a]>1000000]
    slope=float(np.median(slopes));assert all(abs(z/(FS/400000000)-1)<.02 for z in slopes)
    origin=float(np.median([marker[i]-cycles[i]*slope for i in ANCHORS]));residuals={i:(marker[i]-(origin+cycles[i]*slope))/FS*1e6 for i in ANCHORS}
    assert max(abs(z) for z in residuals.values())<100
    def sample(t):return round(origin+((t-p['begin'])&0xffffffff)*slope)
    def measure(a,b):return metrics(signals,a,b,round(origin))
    windows={}
    for title,a,b in [('receiver_to_strobe',1,2),('strobe_to_frame',2,3),('sd_init',4,5),('slot_transport',6,7)]:windows[title]=measure(marker[a],marker[b])
    end=sample(p['end']);windows['terminal_awake_100ms']=measure(end+FS//100,end+FS*11//100)
    ethernet=v.get('board_eth');eth=None
    if ethernet:
        raw=run/'capture/bootstrap/completed-board-eth.bin';w=list(struct.unpack('<64I',raw.read_bytes()))
        assert w==ethernet['words'] and ethernet['qualified_powerdown']
        assert w[:6]==[0x31485445,1,6,0,0,123] and w[8:17]==[7,0xc131,0x3000,0x3000,0x3800,0x3800,0x3800,1,6]
        assert w[17]==w[18] and w[32:38]==w[44:50] and w[38:44]==w[50:56]
        assert 0<((w[6]-p['arm'])&0xffffffff)<400000000 and 0<((p['sd_begin']-w[7])&0xffffffff)<4000000
        a,b=sample(w[6]),sample(w[7]);eth=dict(raw_sha256=sha(raw),start_ms=(a-origin)/FS*1000,end_ms=(b-origin)/FS*1000,duration_ms=(b-a)/FS*1000,proof=ethernet,
            immediately_before_1ms=measure(a-FS//1000,a),immediately_after_1ms=measure(b,b+FS//1000),temporal_limit='Adjacent windows straddle changing capture/SD work; their difference is not an isolated PHY current measurement.')
    profile=[]
    for a in range(round(origin),end+int(.15*FS)-1999,2000):
        q=measure(a,a+2000);profile.append(dict(time_ms=(a+1000-origin)/FS*1000,current_mA=q['current_mean_mA'],power_mW=q['power_mean']*1000))
    out=dict(run=name,binary_sha256=v['binary_sha256'],proof_path=str(verification),proof_sha256=sha(verification),manifest_sha256=sha(build/'manifest.json'),checks=checks,
      all_gpi0_edges=es,unclassified_edges=len(es)-18,markers=[dict(id=q['ids'][0],name=EVENTS[q['ids'][0]],time_ms=(q['sample_id']-origin)/FS*1000,**q) for q in train],
      alignment=dict(sample_origin=origin,JS_samples_per_DWT_tick=slope,anchor_residual_us=residuals),windows=windows,ethernet=eth,
      scope='Awake RAM capture, no cold boot or Standby. Successful image save proof retained; independent card readback qualification is separate. Warm card history differs from cold cycles.',
      limitation='Compare same workload phase, not whole duration: card init/write latency varies. Post-terminal awake windows are temporal observations of the completed firmware state; no PHY restore is performed by candidate.')
    (HERE/(name+'-aligned-analysis.json')).write_text(json.dumps(out,indent=2)+'\n')
    (HERE/(name+'-aligned-profile.json')).write_text(json.dumps(profile,indent=2)+'\n')
    return out

if __name__=='__main__':
    a=analyze('baseline-awake',CAMPAIGN/'baseline-awake/capture/verified.json')
    b=analyze('candidate-awake',CAMPAIGN/'candidate-reobserved/verified.json')
    comparison={}
    for k in a['windows']:
        aa=a['windows'][k];bb=b['windows'][k]
        comparison[k]=dict(baseline_mA=aa['current_mean_mA'],candidate_mA=bb['current_mean_mA'],difference_mA=aa['current_mean_mA']-bb['current_mean_mA'],baseline_mW=aa['power_mean']*1000,candidate_mW=bb['power_mean']*1000,difference_mW=(aa['power_mean']-bb['power_mean'])*1000,baseline_ms=aa['duration_ms'],candidate_ms=bb['duration_ms'])
    (HERE/'awake-comparison.json').write_text(json.dumps(dict(comparison=comparison,ethernet=b['ethernet'],qualification='Warm RAM phase and terminal-state observations only; no cold-cycle energy inference.'),indent=2)+'\n')
    print(json.dumps(comparison,indent=2))
