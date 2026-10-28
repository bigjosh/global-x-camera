"""One hardware NRST pulse with bounded UART guard stimulus; preserve SRAM."""
import sys,time,json,threading,subprocess
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tmp/bringup/vcp-deps'))
import serial
from serial.tools import list_ports
out=Path(__file__).parent/'hardware-ap0-recovery-after-sleep';out.mkdir(exist_ok=False)
ports=[p for p in list_ports.comports() if p.vid==0x0483 and p.pid==0x3754 and p.serial_number=='002100203335511035383531']
assert len(ports)==1,ports
s=serial.Serial();s.port=ports[0].device;s.baudrate=1000000;s.write_timeout=2;s.timeout=.2;s.rts=False;s.dtr=False
stop=threading.Event();events=[];txstate={'bytes':0}
def event(name,**kw):
    events.append(dict(event=name,utc=datetime.now(timezone.utc).isoformat(),**kw))
    (out/'events.json').write_text(json.dumps(events,indent=2))
def tx():
    try:
        deadline=time.monotonic()+8
        while not stop.is_set() and time.monotonic()<deadline:
            txstate['bytes']+=s.write(bytes([0xc0])*32768)
    except Exception as ex:txstate['error']=repr(ex)
t=None
try:
    s.open();event('uart_opened',port=s.port);t=threading.Thread(target=tx);t.start();time.sleep(.05)
    argv=['C:/Users/joshd/AppData/Local/stm32cube/bundles/programmer/2.23.0/bin/STM32_Programmer_CLI.exe',
          '-c','port=SWD','mode=HWRSTPULSE','freq=1000','ap=0','sn=002100203335511035383531','-hardRst']
    event('hardware_reset_requested',argv=argv,reason='Completed no-storage WFI diagnostic masked UART recovery IRQ. Warm hardware reset retains proof SRAM; no power cycle or flash/SD operation.')
    p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20,creationflags=subprocess.CREATE_NO_WINDOW)
    (out/'reset.log').write_bytes(p.stdout);event('reset_cli_returned',returncode=p.returncode)
    time.sleep(.5)
finally:
    stop.set()
    if t:t.join(3)
    if s.is_open:s.cancel_write();s.break_condition=False;s.reset_output_buffer();s.close()
    event('closed',tx=txstate)
print(json.dumps(events[-2:]))
