"""Stats-only JS110 snapshot; never changes target power."""
from pathlib import Path
import sys,time,json
from datetime import datetime,timezone
H=Path(__file__).resolve().parent; R=Path.cwd()
sys.path.insert(0,str(R/'tmp/bringup/joulescope-deps'))
from pyjoulescope_driver import Driver
out=H/(sys.argv[1]+'.json');assert not out.exists()
samples=[]
def cb(topic,value):samples.append(value)
with Driver() as d:
    with d.open('u/js110/000163',mode='restore',timeout=5) as v:
        old={k:v.query(k,timeout=5) for k in ('s/i/range/select','s/sstats/ctrl')}
        v.subscribe('s/sstats/value','pub',cb)
        try:
            v.publish('s/sstats/ctrl',1,timeout=5);time.sleep(2)
            assert samples
        finally:
            v.publish('s/sstats/ctrl',old['s/sstats/ctrl'],timeout=5)
            v.unsubscribe('s/sstats/value',cb)
        final={k:v.query(k,timeout=5) for k in old};assert final==old
result=dict(utc=datetime.now(timezone.utc).isoformat(),initial=old,final=final,
            statistics=samples[-1],power_changed=False)
with out.open('x') as f: json.dump(result,f,indent=2)
s=samples[-1]['signals'];print(json.dumps(dict(file=str(out),range=old['s/i/range/select'],
    current_mA=1000*s['current']['avg']['value'],voltage_V=s['voltage']['avg']['value'])))
