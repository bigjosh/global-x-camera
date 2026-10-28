"""Root-only final output-off after verified normal UART park and SBF read."""
import json,sys,time
from datetime import datetime,timezone
from pathlib import Path
H=Path(__file__).resolve().parent;R=H.parents[2]
sys.path.insert(0,str(R/'tmp/bringup/joulescope-deps'))
from pyjoulescope_driver import Driver
p=H/'final-cold/sbf/result.json';proof=json.loads(p.read_text())
assert proof['passed'] and proof['sbf'] and proof['guard_after']['status']['state']==3
assert 0<=time.time()-p.stat().st_mtime<600
out=H/'final-power-off.json';assert not out.exists()
samples=[]
def stats(topic,value):samples.append(value)
with Driver() as d:
    with d.open('u/js110/000163',mode='restore',timeout=5) as dev:
        prior=dev.query('s/sstats/ctrl',timeout=5)
        dev.subscribe('s/sstats/value','pub',stats)
        try:
            dev.publish('s/sstats/ctrl',1,timeout=5)
            dev.publish('s/i/range/select',0,timeout=5)
            time.sleep(2)
            result=dict(utc=datetime.now(timezone.utc).isoformat(),output_range=dev.query('s/i/range/select',timeout=5),last_statistics=samples[-1] if samples else None,
                preceding_state='Exact normal UART early park, SBF1/PDDS1/STOPF0 read after measured missing-camera shutdown. Normal NOR unchanged.',
                scope='Intentional final JS output-disabled state, not proof of every target rail at zero or absence of debug signal backfeed. Camera and SD remain disconnected.')
        finally:
            dev.publish('s/sstats/ctrl',prior,timeout=5);dev.unsubscribe('s/sstats/value',stats)
        result['statistics_setting_restored']=dev.query('s/sstats/ctrl',timeout=5)==prior
        out.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
