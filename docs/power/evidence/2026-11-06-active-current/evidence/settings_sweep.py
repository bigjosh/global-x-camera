"""Compare JS settings at the same exact idle recovery park; no DUT reset/write.
Only auto/fixed10A current ranges are admitted. All settings restored on exit.
"""
from pathlib import Path
import json,sys,time,subprocess
from datetime import datetime,timezone
H=Path(__file__).resolve().parent;R=H.parents[2];out=H/sys.argv[1]
out.mkdir(exist_ok=False)
with (out/'park.log').open('xb') as log:
    subprocess.run([sys.executable,str(R/'firmware/capture-timing/recovery_gpio/check_park.py'),
        '--build',str(R/'tmp/bringup/sensor-autostop-promote-20261028/flash-standby-v1/staged'),
        '--out',str(out/'park')],check=True,stdout=log,stderr=subprocess.STDOUT,
        timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
sys.path.insert(0,str(R/'tmp/bringup/joulescope-deps'))
from pyjoulescope_driver import Driver
samples=[];windows=[]
def cb(topic,value):samples.append(value)
keys=('s/i/range/select','s/extio/voltage','s/sstats/ctrl')
result=dict(passed=False,reset_requested=False,target_RAM_writes=False,windows=windows)
with Driver() as d:
    with d.open('u/js110/000163',mode='restore',timeout=5) as v:
        old={k:v.query(k,timeout=5) for k in keys};result['initial']=old
        assert old['s/i/range/select']==128
        v.subscribe('s/sstats/value','pub',cb)
        try:
            v.publish('s/sstats/ctrl',1,timeout=5)
            for name,ext,irange in [('initial',old['s/extio/voltage'],128),
                  ('extio3300_auto',3300,128),('extio_restore_auto',old['s/extio/voltage'],128),
                  ('extio_restore_fixed10A',old['s/extio/voltage'],1),
                  ('extio_restore_auto_repeat',old['s/extio/voltage'],128)]:
                v.publish('s/extio/voltage',ext,timeout=5)
                v.publish('s/i/range/select',irange,timeout=5)
                assert v.query('s/i/range/select',timeout=5)==irange
                assert v.query('s/extio/voltage',timeout=5)==ext
                first=len(samples);time.sleep(2.2)
                assert len(samples)>=first+3
                accepted=samples[-2:]
                assert all(4.5<s['signals']['voltage']['avg']['value']<5.5 for s in accepted)
                entry=dict(name=name,utc=datetime.now(timezone.utc).isoformat(),extio=ext,range=irange,
                     statistics=accepted,current_mA=sum(s['signals']['current']['avg']['value'] for s in accepted)*500)
                windows.append(entry);print(json.dumps({k:entry[k] for k in ('name','current_mA','extio','range')}),flush=True)
                assert abs(entry['current_mA'])<500,'Unexpected draw; restore settings and inspect'
            result['passed']=True
        finally:
            for k in keys:v.publish(k,old[k],timeout=5)
            v.unsubscribe('s/sstats/value',cb)
            result['final']={k:v.query(k,timeout=5) for k in keys}
            assert result['final']==old
            result['closed_utc']=datetime.now(timezone.utc).isoformat()
            with (out/'result.json').open('x') as f:json.dump(result,f,indent=2)
