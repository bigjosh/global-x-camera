"""Leave the test target OFF from freshly verified exact idle recovery.

Root-owned final action, not a reusable unattended runner. No RAM/NOR/SD writes.
Range zero is intentionally retained; all other measurement settings restored.
"""
from pathlib import Path
import json, sys, time, subprocess, hashlib
from datetime import datetime, timezone
H=Path(__file__).resolve().parent
R=H.parents[3]
out=H/'final-off'
out.mkdir(exist_ok=False)
recovery=R/'tmp/bringup/sensor-autostop-promote-20261028/flash-standby-v1/staged'
command=[sys.executable,str(R/'firmware/capture-timing/recovery_gpio/check_park.py'),
         '--build',str(recovery),'--out',str(out/'park')]
with (out/'park.log').open('xb') as log:
    subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT,
                   timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
park=json.loads((out/'park/result.json').read_text())
assert park['passed'] and park['context']['PC']==0x3418078C
assert park['prefix_sha256']=='6378483a91b560ffc6b31d74a9dd1205996a14c8030447ffddf7deddc9d23874'
sys.path.insert(0,str(R/'tmp/bringup/joulescope-deps'))
from pyjoulescope_driver import Driver
samples=[]
def callback(topic,value): samples.append(value)
report=dict(passed=False,began_utc=datetime.now(timezone.utc).isoformat(),
    source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    park_proof_sha256=hashlib.sha256((out/'park/result.json').read_bytes()).hexdigest(),
    intent='Leave target OFF; retain all other settings; no automatic re-enable')
try:
    with Driver() as driver:
        with driver.open('u/js110/000163',mode='restore',timeout=5) as dev:
            initial={k:dev.query(k,timeout=5) for k in ('s/i/range/select','s/sstats/ctrl')}
            report['initial']=initial
            assert initial['s/i/range/select']==128
            dev.subscribe('s/sstats/value','pub',callback)
            try:
                dev.publish('s/sstats/ctrl',1,timeout=5)
                time.sleep(1.1)
                assert samples
                before=samples[-1]
                assert 4.5<before['signals']['voltage']['avg']['value']<5.5
                report['before_statistics']=before
                report['off_command_utc']=datetime.now(timezone.utc).isoformat()
                dev.publish('s/i/range/select',0,timeout=5)
                assert dev.query('s/i/range/select',timeout=5)==0
                time.sleep(1.5)
                after=samples[-1]
                report['after_statistics']=after
                assert abs(after['signals']['current']['avg']['value'])<0.0001
                report['passed']=True
            finally:
                dev.publish('s/sstats/ctrl',initial['s/sstats/ctrl'],timeout=5)
                dev.unsubscribe('s/sstats/value',callback)
                report['final']={k:dev.query(k,timeout=5) for k in initial}
                assert report['final']['s/sstats/ctrl']==initial['s/sstats/ctrl']
                report['target_rail_zero_proven']=False
finally:
    report['closed_utc']=datetime.now(timezone.utc).isoformat()
    with (out/'result.json').open('x') as f: json.dump(report,f,indent=2)
print(json.dumps(report))
