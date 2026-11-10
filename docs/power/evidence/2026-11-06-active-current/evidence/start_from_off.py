"""One bounded cold UART-recovery entry from a freshly observed OFF output.
No FLASH/SD writes or reset commands; failed recovery never causes an auto retry.
"""
from pathlib import Path
import sys,time,json,importlib.util,subprocess
from datetime import datetime,timezone
H=Path(__file__).resolve().parent;R=H.parents[2]
out=H/'initial-cold-recovery';out.mkdir(exist_ok=False)
spec=importlib.util.spec_from_file_location('startup_uart',R/'tmp/bringup/inrush-20261105/record_startup.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
sys.path.insert(0,str(R/'tmp/bringup/joulescope-deps'))
from pyjoulescope_driver import Driver
events=[];samples=[]
def event(name,**kw):
    events.append(dict(event=name,utc=datetime.now(timezone.utc).isoformat(),**kw))
    (out/'events.json').write_text(json.dumps(events,indent=2)+'\n')
def stats(topic,value):samples.append(value)
uart=None
with Driver() as driver:
    with driver.open('u/js110/000163',mode='restore',timeout=5) as dev:
        old={k:dev.query(k,timeout=5) for k in ('s/i/range/select','s/sstats/ctrl')}
        assert old['s/i/range/select']==0,'Expected intentional output OFF'
        event('opened_off',initial=old)
        dev.subscribe('s/sstats/value','pub',stats)
        try:
            dev.publish('s/sstats/ctrl',1,timeout=5);time.sleep(15)
            assert len(samples)>=2
            for value in samples[-2:]:
                assert abs(value['signals']['current']['avg']['value'])<.0001
                assert 4.5<value['signals']['voltage']['avg']['value']<5.5
            event('off_verified',sample=samples[-1],seconds=15,
                  limitation='Near-zero input current only; DUT rail discharge not probed')
            uart=helper.UART(event);uart.start_train();time.sleep(.06);uart.check()
            assert uart.state['bytes']>0
            dev.publish('s/i/range/select',128,timeout=5)
            assert dev.query('s/i/range/select',timeout=5)==128
            event('power_on_with_C0')
            time.sleep(3);uart.check()
            event('powered_observation',sample=samples[-1])
        finally:
            if uart:uart.close()
            dev.publish('s/sstats/ctrl',old['s/sstats/ctrl'],timeout=5)
            dev.unsubscribe('s/sstats/value',stats)
            event('closed',final={k:dev.query(k,timeout=5) for k in old},
                  no_automatic_power_change_during_cleanup=True)
(out/'statistics.json').write_text(json.dumps(samples,indent=2)+'\n')
cmd=[sys.executable,str(R/'firmware/capture-timing/recovery_gpio/check_park.py'),
     '--build',str(R/'tmp/bringup/sensor-autostop-promote-20261028/flash-standby-v1/staged'),
     '--out',str(out/'park')]
with (out/'park.log').open('xb') as log:
    subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True,
                   timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
proof=json.loads((out/'park/result.json').read_text());assert proof['passed']
print(json.dumps(dict(passed=True,park=str(out/'park/result.json'),
    current_mA=samples[-1]['signals']['current']['avg']['value']*1000)))
