"""Single measured cold recovery after completed idle-only sleep diagnostic."""
import sys,time,json,threading
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'tmp/bringup/vcp-deps'),str(ROOT/'tmp/bringup/joulescope-deps')]
import serial
from serial.tools import list_ports
from pyjoulescope_driver import Driver
out=Path(__file__).parent/sys.argv[1];out.mkdir(exist_ok=False)
events=[];samples=[];stop=threading.Event();txstate={'bytes':0}
def event(name,**kw):
    events.append(dict(event=name,utc=datetime.now(timezone.utc).isoformat(),**kw))
    (out/'events.json').write_text(json.dumps(events,indent=2))
ports=[p for p in list_ports.comports() if p.vid==0x0483 and p.pid==0x3754 and p.serial_number=='002100203335511035383531']
assert len(ports)==1
s=serial.Serial();s.port=ports[0].device;s.baudrate=1000000;s.write_timeout=2;s.timeout=.2;s.rts=False;s.dtr=False
def tx():
    try:
        deadline=time.monotonic()+8
        while not stop.is_set() and time.monotonic()<deadline:txstate['bytes']+=s.write(bytes([0xc0])*32768)
    except Exception as ex:txstate['error']=repr(ex)
def stats(topic,value):samples.append(value)
with Driver() as driver:
    with driver.open('u/js110/000163',mode='restore',timeout=5) as dev:
        prior={k:dev.query(k,timeout=5) for k in ('s/i/range/select','s/sstats/ctrl')}
        assert prior['s/i/range/select']==128
        event('opened',initial=prior,qualification='Camera and SD physically disconnected by user. Read-only PHY test failed before execution while loading unavailable high SRAM; debugger access subsequently failed. Restore exact UART early park via known measured cold recovery. No persistent storage commands.')
        dev.subscribe('s/sstats/value','pub',stats);t=None
        try:
            dev.publish('s/sstats/ctrl',1,timeout=5);time.sleep(1.2)
            event('before_off',sample=samples[-1] if samples else None)
            dev.publish('s/i/range/select',0,timeout=5);event('off');time.sleep(15)
            assert samples and abs(samples[-1]['signals']['current']['avg']['value'])<.0003
            event('off_verified',sample=samples[-1])
            s.open();t=threading.Thread(target=tx);t.start();time.sleep(.05)
            dev.publish('s/i/range/select',128,timeout=5);event('power_on_with_uart')
            time.sleep(3);event('after_on',sample=samples[-1])
        finally:
            stop.set()
            if t:t.join(3)
            if s.is_open:s.cancel_write();s.break_condition=False;s.reset_output_buffer();s.close()
            dev.publish('s/i/range/select',prior['s/i/range/select'],timeout=5)
            dev.publish('s/sstats/ctrl',prior['s/sstats/ctrl'],timeout=5)
            dev.unsubscribe('s/sstats/value',stats)
            event('closed',tx=txstate,final={k:dev.query(k,timeout=5) for k in prior})
print(json.dumps(events[-1]))
