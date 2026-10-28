"""Root-only isolated normal-flash missing-camera shutdown measurement.

No storage/camera attached. Fresh standalone completion before one cold cycle.
Records statistics, does not access the debugger during the powered interval.
"""
import importlib.util,json,sys,time
from datetime import datetime,timezone
from pathlib import Path
H=Path(__file__).resolve().parent;ROOT=H.parents[2]
sys.path.insert(0,str(ROOT/'tmp/bringup/joulescope-deps'))
from pyjoulescope_driver import Driver
spec=importlib.util.spec_from_file_location('probe',H/'run_v6.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
out=H/'final-cold';out.mkdir(exist_ok=False)
s=json.loads((H/'cachecontrol03/operation/verified.json').read_text())['session']
b=p.raw.sd.Bench(out/'before');r=p.observe(b,s)
assert r['passed'] and r['proof']['FLAGS']==0
events=[];samples=[]
def event(name,**kw):
    events.append(dict(event=name,utc=datetime.now(timezone.utc).isoformat(),monotonic=time.monotonic(),**kw))
    (out/'events.json').write_text(json.dumps(events,indent=2));print(name,flush=True)
def stats(topic,value):
    samples.append(dict(received_monotonic=time.monotonic(),value=value))
with Driver() as d:
    with d.open('u/js110/000163',mode='restore',timeout=5) as dev:
        keys=('s/i/range/select','s/sstats/ctrl')
        initial={k:dev.query(k,timeout=5) for k in keys};assert initial[keys[0]]==128
        event('opened',initial=initial,scope='Camera/SD removed. One unchanged normal-flash boot should detect missing camera, signal code2, then shutdown. No successful photo or capture-cycle energy claim.')
        dev.subscribe('s/sstats/value','pub',stats)
        try:
            dev.publish('s/sstats/ctrl',1,timeout=5);time.sleep(1.2)
            event('before_off',sample=samples[-1] if samples else None)
            dev.publish('s/i/range/select',0,timeout=5);event('output_off');time.sleep(15)
            assert samples and abs(samples[-1]['value']['signals']['current']['avg']['value'])<.0003
            event('off_current_verified',sample=samples[-1])
            dev.publish('s/i/range/select',128,timeout=5);event('normal_power_on')
            time.sleep(23)
            event('after_normal_boot',sample=samples[-1])
            assert len(samples)>3 and all(0<z['value']['signals']['current']['avg']['value']<.02 for z in samples[-3:]),'No final low-current plateau; preserve state'
        finally:
            (out/'statistics.json').write_text(json.dumps(samples,indent=2))
            for k,v in initial.items():dev.publish(k,v,timeout=5)
            dev.unsubscribe('s/sstats/value',stats)
            event('closed',final={k:dev.query(k,timeout=5) for k in keys})
