import sys,json,hashlib,statistics
from pathlib import Path
sys.path.insert(0,str(Path('firmware/boot-timing').resolve()))
from inspect_cycle import read_csv
p=Path('tmp/bringup/opt-final-powered-state'); t,v=read_csv(p/'analog.csv'); dt,dv=read_csv(p/'digital.csv',digital=True)
r={str(i):{'min_v':min(v[i]),'max_v':max(v[i]),'mean_v':statistics.mean(v[i])} for i in range(6)}
stop=json.loads(Path('tmp/bringup/opt-nor-response.json').read_text())
assert stop['event']=='stopped' and stop['ok'] and stop['range']==128
checks={'target_5v_stable':r['4']['min_v']>=4.5 and r['4']['max_v']<=5.5,'main_vddio_stable':r['5']['min_v']>=2.97 and r['5']['max_v']<=3.6,'aux_3v3_stable':r['3']['min_v']>=2.97 and r['3']['max_v']<=3.6,'reset_and_markers_high':all(min(dv[i])==1 for i in (0,1,2))}
out={'passed':all(checks.values()),'checks':checks,'duration_s':t[-1]-t[0],'channel_statistics':r,'session_release':stop,'no_power_or_debug_stimulus_in_verification':True,'files':{n:{'sha256':hashlib.sha256((p/n).read_bytes()).hexdigest(),'bytes':(p/n).stat().st_size} for n in ('analog.csv','digital.csv','boot.sal','capture-config.json')}}
(p/'powered-state.json').write_text(json.dumps(out,indent=2)+'\n'); print(json.dumps({'passed':out['passed'],'rails':r,'released_utc':stop['utc']},indent=2)); assert out['passed']
