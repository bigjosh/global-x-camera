"""Offline capture-control07 evidence. Never operates an instrument."""
from pathlib import Path
import importlib.util
import json
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
CAMPAIGN=Path(__file__).resolve().parent
SOURCE=ROOT/'docs/power/evidence/2026-11-05-inrush/support/analyze_inrush.py'
spec=importlib.util.spec_from_file_location('saved_js_analysis',SOURCE)
analysis=importlib.util.module_from_spec(spec);spec.loader.exec_module(analysis)
folder=CAMPAIGN/'capture-control07-aligned'
signals,checks,result=analysis.load_trace(folder)
logical=dict(signals)
logical['gpi0'],logical['gpi1']=signals['gpi1'],signals['gpi0']
markers=analysis.decode_markers(logical,0,'11')
digital={}
for name in ('gpi0','gpi1'):
    origin,values=signals[name]
    digital[name]=dict(physical_input=name.replace('gpi','IN'),
        intended_role='PD0 exposure mirror' if name=='gpi0' else 'PD12 phase markers',
        first_sample_id=origin,end_sample_id_exclusive=origin+len(values),
        samples=len(values),low_samples=int(np.count_nonzero(values==0)),
        high_samples=int(np.count_nonzero(values==1)),edge_count=len(analysis.edges(signals,name)))

start=max(signals[k][0] for k in ('current','voltage','power'))
end=min(signals[k][0]+len(signals[k][1]) for k in ('current','voltage','power'))
origin,current=signals['current']
bin_start=((start+1999)//2000)*2000
bins=(end-bin_start)//2000
means=current[bin_start-origin:bin_start-origin+bins*2000].reshape(bins,2000).mean(axis=1,dtype=np.float64)
good=np.isfinite(means)&(means>=.002)&(means<=.006)
runs=np.flatnonzero(np.convolve(good.astype(int),np.ones(50,dtype=int),'valid')==50)
plateau=None
if len(runs):
    point=bin_start+int(runs[0])*2000
    plateau=dict(first_sample_id=point,time_from_recording_sample_zero_ms=point/analysis.FS*1000,
        definition='First 50 consecutive 1 ms bin means in 2..6 mA; not a CPU-state measurement',
        first_100ms=analysis.metrics(signals,point,point+analysis.FS//10,0))
tail=analysis.metrics(signals,end-analysis.FS//2,end,0)
events=[json.loads(line) for line in (folder/'events.jsonl').read_text().splitlines()]
report=dict(schema=1,source_folder=str(folder.relative_to(ROOT)),
    excluded_recording=dict(name='capture-control07-record',reason='Root reports recording ended before reset; excluded completely'),
    analyzer=dict(path=str(SOURCE.relative_to(ROOT)),sha256=analysis.sha(SOURCE)),
    source_files={name:{k:v for k,v in check.items() if k!='path'} for name,check in checks.items()},
    corrected_mapping=dict(phase='physical IN1 / raw gpi1',exposure='physical IN0 / raw gpi0',
        original_metadata_roles_incorrect=True,raw_files_changed=False,
        provenance='Root supplied physical role correction; this trace has no transitions to independently verify wiring'),
    digital=digital,marker_decode=markers,
    completion_markers_observed=False,exposure_count_verified=False,
    phase_timing_available=False,image_integrity_verified=False,
    actual_standby_verified=False,
    analog=dict(common_start_sample_id=start,common_end_sample_id_exclusive=end,
        low_current_plateau=plateau,final_500ms=tail,
        sleep_like_signature=bool(plateau and tail['valid'] and .002<=tail['current_mean']<=.006),
        reset_reference='No NRST/marker edge exists in these streams; BREAK timestamps are host events only',
        reset_host_events=[e for e in events if e['event'] in ('break_asserted','break_released')]),
    conclusion='Both GPIO inputs stayed LOW for the complete usable record. Analog load falls to a stable low-current plateau consistent with prior sleep-level observations, but no capture, commit, deinit, pre-WFI or exposure event can be decoded.',
    limitations=['Pre-WFI intent would not itself prove Standby, even if a marker were present.',
        'The source was already powered: this is a warm reset recording, not a cold inrush measurement.',
        'Analog stream sample IDs align current/voltage/power. Callback/host timestamps are not a measured NRST boundary.',
        'The first current chunk has 71 nonfinite samples. All reported tail/plateau windows are independently finite.',
        'No complete capture-cycle energy or image completion claim is made.',
        'Final digital chunk is excluded because packed-bit endpoint padding is unresolved.'])
dest=CAMPAIGN/'capture-control07-aligned-analysis.json'
with dest.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2,allow_nan=False);f.write('\n')
print(json.dumps(dict(output=str(dest),digital=digital,
    tail_current_mA=tail.get('current_mean_mA'),tail_voltage_V=tail.get('voltage_mean'),
    tail_power_mW=tail.get('power_mean',0)*1000,
    plateau_ms=plateau['time_from_recording_sample_zero_ms'] if plateau else None,
    phase_timing_available=False,actual_standby_verified=False),indent=2))
