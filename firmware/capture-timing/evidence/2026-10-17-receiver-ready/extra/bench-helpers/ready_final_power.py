"""Read-only verification of a completed short Saleae capture after JS release."""
import argparse,hashlib,json,statistics,sys
from pathlib import Path
sys.path.insert(0,str(Path('firmware/boot-timing').resolve()))
from inspect_cycle import read_csv
p=argparse.ArgumentParser();p.add_argument('--capture',type=Path,required=True);p.add_argument('--release',type=Path,required=True)
a=p.parse_args();t,v=read_csv(a.capture/'analog.csv');dt,dv=read_csv(a.capture/'digital.csv',digital=True)
stop=json.loads(a.release.read_text());r={str(i):dict(min_v=min(v[i]),max_v=max(v[i]),mean_v=statistics.mean(v[i])) for i in (3,4,5)}
g=stop.get('recovery_output',{})
checks=dict(released_successfully=stop.get('event')=='stopped' and stop.get('ok') and stop.get('range')==128,
 recovery_normal=g.get('extio_voltage_mv')==3300 and g.get('gpo0')==1 and g.get('gpo1')==0,
 target_5v_stable=4.5<=r['4']['min_v']<=r['4']['max_v']<=5.5,
 main_vddio_stable=2.97<=r['5']['min_v']<=r['5']['max_v']<=3.6,
 aux_3v3_stable=2.97<=r['3']['min_v']<=r['3']['max_v']<=3.6,
 reset_released_and_boot_marker_high=all(min(dv[i])==1 for i in (0,1)),
 no_gpio_marker_transitions=all(len(set(dv[i]))==1 for i in (0,1,2)),observation_at_least_2s=t[-1]-t[0]>=2)
out=dict(passed=all(checks.values()),checks=checks,duration_s=t[-1]-t[0],rails=r,marker_levels={str(i):sorted(set(dv[i])) for i in (0,1,2)},session_release=stop,no_power_or_debug_stimulus_in_verification=True,
 files={n:dict(sha256=hashlib.sha256((a.capture/n).read_bytes()).hexdigest(),bytes=(a.capture/n).stat().st_size) for n in ('analog.csv','digital.csv','boot.sal','capture-config.json')})
(a.capture/'powered-state.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2));assert out['passed']
