import sys,time,json,threading
from pathlib import Path
from datetime import datetime,timezone
root=Path.cwd();sys.path.insert(0,str(root/'tmp/bringup/vcp-deps'))
import serial
from serial.tools import list_ports
out=Path(sys.argv[1]);out.mkdir()
ports=[p for p in list_ports.comports() if p.vid==0x0483 and p.pid==0x3754 and p.serial_number=='002100203335511035383531']
assert len(ports)==1,ports
log=[]
def e(name,**kw):
 log.append(dict(event=name,utc=datetime.now(timezone.utc).isoformat(),**kw));(out/'uart-events.json').write_text(json.dumps(log,indent=2));print(name,flush=True)
s=serial.Serial();s.port=ports[0].device;s.baudrate=1000000;s.timeout=.5;s.write_timeout=2;s.rts=False;s.dtr=False
status={}
def tx():
 try: status['written']=s.write(bytes([0xc0])*32768)
 except Exception as ex: status['error']=repr(ex)
try:
 s.open();e('opened',port=s.port);time.sleep(.3)
 t=threading.Thread(target=tx);t.start();time.sleep(.023)
 s.break_condition=True;e('break_on');time.sleep(.1);s.break_condition=False;e('break_off')
 t.join(3);assert not t.is_alive();assert status.get('written')==32768,status
 time.sleep(.75);e('stimulus_complete',**status)
finally:
 if s.is_open:
  s.cancel_write();s.break_condition=False;s.reset_output_buffer();s.close()
 e('closed')
