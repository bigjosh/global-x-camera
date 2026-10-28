"""Read live JS statistics only; restore measurement settings and power."""
from pathlib import Path
import sys,time,json
from datetime import datetime,timezone
H=Path(__file__).resolve().parent;R=H.parents[2]
sys.path.insert(0,str(R/'tmp/bringup/joulescope-deps'))
from pyjoulescope_driver import Driver
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
(H/'preflight.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
