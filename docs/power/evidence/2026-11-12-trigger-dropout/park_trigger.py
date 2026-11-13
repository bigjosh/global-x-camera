"""Send the established UART pulse train during one user-triggered boot; no BREAK/reset."""
from pathlib import Path
import datetime,json,runpy,sys,threading,time
ROOT=Path.cwd();HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tmp/bringup/vcp-deps'))
import serial
from serial.tools import list_ports
outname=sys.argv[1];events=[];stop=threading.Event();errors=[]
def event(name,**kw):
    events.append(dict(event=name,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),**kw))
ports=[p for p in list_ports.comports() if p.vid==0x0483 and p.pid==0x3754 and p.serial_number=='002100203335511035383531']
assert len(ports)==1,ports
s=serial.Serial();s.port=ports[0].device;s.baudrate=1000000;s.timeout=.1;s.write_timeout=1;s.rts=False;s.dtr=False
def transmit():
    try:
        while not stop.is_set():
            n=s.write(bytes([0xC0])*4096)
            assert n==4096,n
    except Exception as e:
        if not stop.is_set():errors.append(repr(e))
t=None
try:
    s.open();event('opened',port=s.port,baud=1000000,pattern='0xC0',break_asserted=False)
    t=threading.Thread(target=transmit,daemon=True);t.start()
    sys.argv=[str(HERE/'watch_trigger.py'),outname,'park']
    runpy.run_path(str(HERE/'watch_trigger.py'),run_name='__main__')
finally:
    stop.set()
    if s.is_open:
        s.cancel_write()
        if t:t.join(2)
        s.break_condition=False;s.reset_output_buffer();s.close()
    event('closed',errors=errors,break_asserted=False)
    target=HERE/outname
    if target.exists():(target/'uart-events.json').write_text(json.dumps(events,indent=2)+'\n')
    print('UART closed; no reset/BREAK or target writes were issued.',flush=True)
