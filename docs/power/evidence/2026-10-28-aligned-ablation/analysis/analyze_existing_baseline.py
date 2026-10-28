"""Offline phase-aligned analysis of the sealed direct-5-V baseline. No hardware APIs."""
from pathlib import Path
import csv, hashlib, html, json
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
RAW = ROOT/'tmp/bringup/js-gpi-smoke-20261028'
ARCHIVE = ROOT/'docs/power/evidence/2026-10-28-direct5v-gpi'
FS = 2_000_000
ANALYSIS = ARCHIVE/'baseline-analysis.json'
COLORS = {'startup':'#e5e7eb','boot':'#94a3b8','camera':'#60a5fa','overlap':'#a78bfa','init':'#fbbf24','prepare':'#fb923c','write':'#34d399','cleanup':'#cbd5e1'}

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for x in iter(lambda:f.read(1024*1024),b''):h.update(x)
    return h.hexdigest()

def metrics(signals, a, b, onset):
    d={'start_sample_id':a,'end_sample_id_exclusive':b,'start_ms':(a-onset)/FS*1000,'end_ms':(b-onset)/FS*1000,'duration_ms':(b-a)/FS*1000}
    assert b>a
    for s in ('current','voltage','power'):
        st,arr=signals[s];x=arr[a-st:b-st]
        assert len(x)==b-a and np.all(np.isfinite(x)),(s,a,b)
        d[s+'_mean']=float(np.mean(x,dtype=np.float64))
        d[s+'_min']=float(np.min(x));d[s+'_max']=float(np.max(x))
        if s=='power':d['energy_mJ']=float(np.sum(x,dtype=np.float64)/FS*1000)
    d['current_mean_mA']=d['current_mean']*1000
    d['finite']=True
    return d

def peak_windows(signals,a,b,onset,width_ms,segments):
    n=round(width_ms*FS/1000);step=FS//10000  # overlapping windows sampled every 0.1 ms
    st,v=signals['current'];x=np.asarray(v[a-st:b-st],dtype=np.float64)
    cs=np.r_[0.,np.cumsum(x)]
    starts=np.arange(0,len(x)-n+1,step);means=(cs[starts+n]-cs[starts])/n
    chosen=[]
    for j in np.argsort(means)[::-1]:
        start=a+int(starts[j]);end=start+n
        if any(start<q['end_sample_id_exclusive'] and end>q['start_sample_id'] for q in chosen):continue
        m=metrics(signals,start,end,onset)
        m['overlapping_phases']=[{'name':s['name'],'overlap_ms':(min(end,s['end_sample_id_exclusive'])-max(start,s['start_sample_id']))/FS*1000} for s in segments if start<s['end_sample_id_exclusive'] and end>s['start_sample_id']]
        chosen.append(m)
        if len(chosen)==3:break
    return chosen

def analyze(r):
    folder=RAW/r['run'];res=json.loads((folder/'result.json').read_text());assert res['success']
    chunks=[json.loads(line) for line in (folder/'chunks.jsonl').read_text().splitlines()]
    signals={};checks={}
    for s in ('current','voltage','power','gpi0','gpi1'):
        digital=s.startswith('gpi');path=folder/(s+('.u1' if digital else '.f32'))
        assert sha(path)==res['sha256'][s]
        rows=[v for v in chunks if v['signal']==s]
        offset=0
        for k,v in enumerate(rows):
            assert v['byte_offset']==offset and v['sample_rate']==FS and v['decimate_factor']==1
            offset+=v['byte_count']
            if k+1<len(rows):
                count=v['byte_count']*(8 if digital else .25)
                delta=rows[k+1]['sample_id']-v['sample_id']
                assert (0<=count-delta<=7) if digital else count==delta
        assert offset==path.stat().st_size
        checks[s]={'sha256':res['sha256'][s],'hash_passed':True,'continuity_passed':True,'first_sample_id':rows[0]['sample_id'],'final_digital_chunk_not_interpreted':digital}
        if not digital:signals[s]=(rows[0]['sample_id'],np.memmap(path,mode='r',dtype='<f4'))
    onset=r['current_onset']['sample_id'];marks={e['id']:e['sample_id'] for e in r['marker_decode']['events']}
    assert r['marker_decode']['ids']==[1,2,4,3,5,6,7,8,9,10]
    assert r['marker_decode']['precedence_pass'] and r['marker_decode']['unique_train']
    plateau=r['low_plateau']['start_sample_id']
    definitions=[
      ('Unqualified initial 5 ms',onset,onset+10000,'startup',False),
      ('Post-5-ms boot to receiver entry',onset+10000,marks[1],'boot',True),
      ('Receiver entry to first strobe IRQ',marks[1],marks[2],'camera',True),
      ('Acquisition before SD init',marks[2],marks[4],'camera',True),
      ('Acquisition overlaps SD init',marks[4],marks[3],'overlap',True),
      ('After frame IRQ, SD init still running',marks[3],marks[5],'init',True),
      ('SCR + slot scan + write preparation',marks[5],marks[6],'prepare',True),
      ('Slot transport: transfer + card waits',marks[6],marks[7],'write',True),
      ('Post-transport validation/commit',marks[7],marks[8],'cleanup',True),
      ('Storage deinitialization',marks[8],marks[9],'cleanup',True),
      ('Final cleanup to pre-WFI marker',marks[9],marks[10],'cleanup',True),
      ('Pre-WFI marker to low-current plateau',marks[10],plateau,'cleanup',True),
    ]
    segments=[]
    for name,a,b,color,qualified in definitions:
        m=metrics(signals,a,b,onset);m.update(name=name,color_group=color,post5ms_window_qualified=qualified)
        segments.append(m)
    total=metrics(signals,onset+10000,plateau,onset)
    assert abs(total['energy_mJ']-sum(x['energy_mJ'] for x in segments[1:]))<1e-7
    assert abs(total['energy_mJ']-r['after_first_5ms_to_low_plateau']['energy_mJ'])<1e-7
    for m in segments:m['share_of_post5ms_energy_percent']=100*m['energy_mJ']/total['energy_mJ'] if m['post5ms_window_qualified'] else None
    coarse=[]
    for name,a,b in [('SD initialization incl. camera overlap',marks[4],marks[5]),('Strobe IRQ to frame IRQ',marks[2],marks[3]),('Before first slot write, excluding 5 ms',onset+10000,marks[6]),('Transport plus final shutdown',marks[6],plateau)]:
        m=metrics(signals,a,b,onset);m['name']=name;coarse.append(m)
    peaks={str(ms)+'ms':peak_windows(signals,onset+10000,plateau,onset,ms,segments) for ms in (1,10)}
    profile=[]
    for a in range(onset+10000,plateau+int(.05*FS)-1999,2000):
        m=metrics(signals,a,a+2000,onset)
        profile.append({'time_ms':(a+1000-onset)/FS*1000,'current_mean_mA':m['current_mean_mA'],'voltage_mean_V':m['voltage_mean'],'energy_mJ':m['energy_mJ']})
    return {'run':r['run'],'checks':checks,'marker_source_sha256':sha(ANALYSIS),'current_onset_sample_id':onset,'segments':segments,'coarse_intervals_overlapping_not_additive':coarse,'post5ms_total':total,'idle_100ms':r['low_plateau'],'peaks':peaks,'profile':profile,'whole_session_initial_current_nans':r['checks']['current']['nonfinite_samples'],'unclassified_gpi0_edges':r['checks']['gpi0']['edge_count']-20,'marker_events':r['marker_decode']['events']}

def graph(rs):
    W,H=1440,1010;left,right=95,1380;plotw=right-left;maxms=700;maxma=260
    def x(t):return left+t/maxms*plotw
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">','<rect width="100%" height="100%" fill="#fff"/>','<style>text{font-family:Arial,sans-serif;fill:#1e293b} .small{font-size:13px} .axis{font-size:14px} .title{font-size:25px;font-weight:700} .sub{font-size:15px}</style>', '<text class="title" x="65" y="40">Direct 5 V baseline: measured current aligned to firmware phases</text>', '<text class="sub" x="65" y="67">Three cold cycles · 1 ms means · board + camera + SD together · first 5 ms deliberately excluded</text>']
    legend=[('boot','Boot'),('camera','Acquisition'),('overlap','Acquisition + SD init'),('init','SD init after frame'),('prepare','SCR / scan / preparation'),('write','Slot transport'),('cleanup','Cleanup / settle')]
    lx=65
    for color,label in legend:
        svg +=[f'<rect x="{lx}" y="88" width="13" height="13" fill="{COLORS[color]}"/>',f'<text class="small" x="{lx+19}" y="99">{label}</text>'];lx+=len(label)*6.4+40
    for i,r in enumerate(rs):
        top=145+i*245;bottom=top+172
        def y(ma):return bottom-ma/maxma*172
        svg.append(f'<text class="sub" x="65" y="{top-13}">{r["run"]}  ·  post-5-ms energy {r["post5ms_total"]["energy_mJ"]:.1f} mJ  ·  low plateau at {r["post5ms_total"]["end_ms"]:.1f} ms</text>')
        for s in r['segments']:
            if not s['post5ms_window_qualified']:continue
            svg.append(f'<rect x="{x(s["start_ms"]):.2f}" y="{top}" width="{max(.1,x(s["end_ms"])-x(s["start_ms"])):.2f}" height="172" fill="{COLORS[s["color_group"]]}" opacity=".20"><title>{html.escape(s["name"])}: {s["duration_ms"]:.4f} ms, {s["energy_mJ"]:.4f} mJ</title></rect>')
        for ma in (0,50,100,150,200,250):
            yy=y(ma);svg+=[f'<path d="M{left},{yy:.2f} H{right}" stroke="#dce2e8"/>',f'<text class="axis" text-anchor="end" x="{left-10}" y="{yy+5:.2f}">{ma}</text>']
        for ms in range(0,701,100):
            xx=x(ms);svg+=[f'<path d="M{xx:.2f},{top} V{bottom}" stroke="#e2e8f0"/>',f'<text class="axis" text-anchor="middle" x="{xx:.2f}" y="{bottom+22}">{ms}</text>']
        pts=' '.join(f'{x(p["time_ms"]):.2f},{y(p["current_mean_mA"]):.2f}' for p in r['profile'])
        svg.append(f'<polyline points="{pts}" fill="none" stroke="#0f172a" stroke-width="1.5"/>')
        for e in r['marker_events']:
            if e['id'] not in (1,2,3,4,5,6,10):continue
            xx=x(e['time_since_current_onset_ms']);svg.append(f'<path d="M{xx:.2f},{top} V{bottom}" stroke="#475569" stroke-width=".7" stroke-dasharray="3 3"/>')
        svg.append(f'<text class="axis" x="26" y="{top+80}" transform="rotate(-90 26 {top+80})">Current (mA)</text>')
    svg += ['<text class="axis" x="740" y="893" text-anchor="middle">Milliseconds from measured current onset (not reset release)</text>', '<text class="sub" x="65" y="929">Color identifies the firmware interval, not the component consuming that current. Acquisition and SD init overlap.</text>', '<text class="sub" x="65" y="953">Transport includes MCU work, SD bus transfer and card waits; these traces do not separate the repeated block loops.</text>', '<text class="small" x="65" y="980">JS voltage is measured at its input. Current onset ≥20 mA; plateau boundary uses 1 ms bins. Image bytes were not reread in these runs.</text>', '</svg>']
    (OUT/'baseline-phase-current.svg').write_text('\n'.join(svg),encoding='utf-8')

def main():
    source=json.loads(ANALYSIS.read_text());rs=[analyze(r) for r in source]
    # Each interval is disjoint; unlike the summary's enclosing intervals, shares can be summed.
    aggregates=[]
    for idx in range(len(rs[0]['segments'])):
        ss=[r['segments'][idx] for r in rs]
        aggregates.append({'name':ss[0]['name'],'qualified':ss[0]['post5ms_window_qualified'],**{f'{key}_{stat}':float(fn([s[key] for s in ss])) for key in ('duration_ms','energy_mJ','current_mean_mA') for stat,fn in [('mean',np.mean),('min',np.min),('max',np.max)]}})
    report={'analysis':'Existing baseline only; no new hardware operation or component attribution','source':str(ANALYSIS),'source_sha256':sha(ANALYSIS),'scope':'Power delivered through JS from regulated 5 V, including populated Nucleo overhead; D2/R23 removed, U24 fitted. Not battery/LTC energy.','window_qualification':'First 5 ms and whole-cycle raw integrals remain unqualified. All separately bounded post-5-ms analog samples finite and contiguous; original 71 startup NaNs remain in the whole-session evidence.','marker_semantics':'For the installed magic-slot path, legacy phase 7 padded_payload_ready is emitted after successful whole-slot transport return, not the first available image buffer. Frame IRQ is not sensor power-off.','peak_definition':'Mean current in 1 ms or 10 ms windows, searched every 0.1 ms after the excluded first 5 ms. Three highest nonoverlapping windows per width. Native extrema are not qualified physical peaks.','causal_limit':'A phase change is correlation. All components remain on the shared measured rail; compare controlled ablations to determine incremental loads.','aggregates':aggregates,'runs':[{k:v for k,v in r.items() if k!='profile'} for r in rs]}
    (OUT/'baseline-phase-partition.json').write_text(json.dumps(report,indent=2)+'\n')
    fields=['run','name','start_ms','end_ms','duration_ms','energy_mJ','current_mean_mA','share_of_post5ms_energy_percent','post5ms_window_qualified']
    with (OUT/'baseline-phase-partition.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fields,extrasaction='ignore');w.writeheader()
        for r in rs:
            for s in r['segments']:w.writerow({'run':r['run'],**s})
    with (OUT/'baseline-current-1ms.csv').open('w',newline='') as f:
        fields=['run','time_ms','current_mean_mA','voltage_mean_V','energy_mJ'];w=csv.DictWriter(f,fields);w.writeheader()
        for r in rs:
            for p in r['profile']:w.writerow({'run':r['run'],**p})
    graph(rs)
    print(json.dumps({'aggregate':aggregates,'peaks':{r['run']:{key:v[0] for key,v in r['peaks'].items()} for r in rs}},indent=2))
if __name__=='__main__':main()

