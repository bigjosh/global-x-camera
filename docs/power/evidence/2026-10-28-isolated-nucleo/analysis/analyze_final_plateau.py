"""Offline analysis of final missing-camera shutdown plateau; no hardware imports."""
import json, struct
import numpy as np
from analyze_isolated import HERE, CAMPAIGN, load, metrics, sha, FS

run=CAMPAIGN/'final-cold'
signals,checks=load(run/'plateau')
# Fixed middle two seconds, chosen without optimizing the measured value.
origin=max(start for start,arr in signals.values())
a=origin+FS//2;b=origin+5*FS//2
assert all(start<=a<b<=start+len(arr) for start,arr in signals.values())
m=metrics(signals,a,b,origin)
sbfpath=run/'sbf/result.json';sbf=json.loads(sbfpath.read_text())
assert sbf['passed'] and sbf['sbf'] and sbf['pdds'] and not sbf['stopf']
assert not sbf['trial_entry_proven'] and not sbf['cpucr_written'] and not sbf['reset_or_power_changed']
cpucr=struct.unpack('<I',(run/'sbf/registers/pwr-cpucr.bin').read_bytes())[0]
assert cpucr==sbf['cpucr']
park=json.loads((run/'park/result.json').read_text());assert park['passed']
assert park['vcp_status']['good_pulses']==9 and park['vcp_status']['bad_pulses']==0
events=json.loads((run/'events.json').read_text());by={x['event']:x for x in events}
assert by['off_current_verified']['monotonic']-by['output_off']['monotonic']>=15
assert by['off_current_verified']['sample']['value']['signals']['current']['avg']['value']==0
block=[]
for begin in range(a,b,FS//10):
    block.append(metrics(signals,begin,min(b,begin+FS//10),origin)['current_mean_mA'])
gpi={}
for s in ('gpi0','gpi1'):
    st,v=signals[s];v=v[a-st:b-st]
    gpi[s]=dict(initial=int(v[0]),transitions=int(np.count_nonzero(v[1:]!=v[:-1])))
report=dict(scope='Final cold normal-flash missing-camera error shutdown, camera and SD physically absent. Not a successful capture/save cycle.',
    boundary='Fixed middle interval: 0.5 s through 2.5 s after latest common native stream start. No current-based selection.',
    metrics=m,checks=checks,gpi=gpi,current_100ms_mean_range_mA=[min(block),max(block)],
    qualification='Stable low plateau followed by first-attempt warm UART recovery and retained SBF=1/PDDS=1/STOPF=0. Reader retains trial_entry_proven=false; this is observed Standby history, not direct entry-time proof.',
    sbf=dict(cpucr=cpucr,sbf=True,pdds=True,stopf=False,trial_entry_proven=False,sha256=sha(sbfpath)),
    events_sha256=sha(run/'events.json'),park_sha256=sha(run/'park/result.json'),
    caveats=['Whole trace startup nonfinite samples remain invalid; bounded middle window is finite and contiguous.',
      'Voltage is sensed at Joulescope input; recorded native power uses that voltage.',
      'Do not compare this shutdown plateau as a matched PHY-on/off or CPU-only measurement.'])
(HERE/'final-plateau-analysis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(current_mA=m['current_mean_mA'],power_mW=m['power_mean']*1000,voltage_V=m['voltage_mean'],duration_ms=m['duration_ms'],energy_mJ=m['energy_mJ'],current_100ms_mean_range_mA=report['current_100ms_mean_range_mA']),indent=2))
