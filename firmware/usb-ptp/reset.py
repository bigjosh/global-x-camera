"""Explicit normal reset through the already qualified ST-LINK BREAK signal.

Bench owner must first establish completed storage/NOR work. This sends no
UART recovery train, so normal FLASH boot resumes. It does not switch power
and must not be described as a cold boot.
"""
import argparse,datetime,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp/bringup/vcp-deps'))
import serial
from serial.tools import list_ports
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
 ports=[x for x in list_ports.comports() if x.vid==0x0483 and x.pid==0x3754 and x.serial_number=='002100203335511035383531']
 if len(ports)!=1:raise RuntimeError('Exact ST-LINK recovery UART is unavailable')
 log=[]
 def record(event):
  log.append(dict(event=event,utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
  (a.out/'events.json').write_text(json.dumps(log,indent=2),encoding='utf-8')
 uart=serial.Serial();uart.port=ports[0].device;uart.baudrate=1000000;uart.timeout=.5;uart.write_timeout=2;uart.rts=False;uart.dtr=False
 try:
  uart.open();uart.reset_output_buffer();record('opened_no_recovery_train')
  uart.break_condition=True;record('break_on');time.sleep(.1)
  uart.break_condition=False;record('break_off_normal_reset_release')
 finally:
  if uart.is_open:uart.break_condition=False;uart.close()
  record('closed')
 print('Normal powered reset released; no power cycle.')
if __name__=='__main__':main()
