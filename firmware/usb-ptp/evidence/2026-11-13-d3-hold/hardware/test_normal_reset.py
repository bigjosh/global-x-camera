"""Root-owned powered-reset smoke test. No JS/cold-power or storage commands.

Requires fresh exact D3 UART park, then uses the established normal reset.
The missing-sensor path is expected but measured, not assumed. Debug reads
do not halt while normal firmware runs; after the window the root separately
recovers and inspects retained shutdown flags.
"""
from pathlib import Path
import argparse, hashlib, importlib.util, json, struct, subprocess, sys, time
from datetime import datetime, timezone

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/'firmware/boot-timing'))
import nor_bench
nor_bench.CLI=ROOT/'tmp/bringup/control-smoke-20261107/tools/programmer-2.23.0/bin/STM32_Programmer_CLI.exe'

def main():
 p=argparse.ArgumentParser();p.add_argument('--package',type=Path,required=True)
 p.add_argument('--park-proof',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 m=json.loads((a.package/'manifest.json').read_text());proof=json.loads(a.park_proof.read_text())
 assert proof['passed'] and proof['prefix_sha256']==m['prefix_sha256']
 assert proof['context']['PC']==0x3418078C and 0<=time.time()-a.park_proof.stat().st_mtime<300
 out=a.out.resolve();out.mkdir(parents=True,exist_ok=False);b=nor_bench.Bench(out/'reads')
 code=(a.package/'stage1.bin').read_bytes();assert hashlib.sha256(code).hexdigest()==m['prefix_sha256']
 assert b.upload(0x34180400,len(code),'pre-prefix.bin')==code
 spec=importlib.util.spec_from_file_location('guard',ROOT/'firmware/capture-timing/recovery_gpio/check_park.py')
 guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
 r=guard.registers(b.call('-coreReg'));assert r['PC']==0x3418078C
 pre=struct.unpack('<6I',b.upload(0x56021000,24,'pre-gpioe.bin'))
 assert (pre[0]>>18)&3==1 and pre[4]&512 and pre[5]&512
 events=[]
 def event(name,**kw):
  x=dict(event=name,utc=datetime.now(timezone.utc).isoformat(),monotonic=time.monotonic(),**kw)
  events.append(x);(out/'events.json').write_text(json.dumps(events,indent=2)+'\n');print(json.dumps(x),flush=True)
 subprocess.run([sys.executable,'-X','utf8',str(ROOT/'firmware/usb-ptp/reset.py'),'--out',str(out/'reset')],check=True)
 begin=time.monotonic();event('powered_reset_completed',cold_boot=False)
 for n,at in enumerate((1.0,6.0)):
  time.sleep(max(0,at-(time.monotonic()-begin)))
  e=struct.unpack('<53I',b.upload(0x343F3000,212,f'error{n}.bin'))
  s=struct.unpack('<32I',b.upload(0x343F4000,128,f'sensor{n}.bin'))
  clocks=struct.unpack('<I',b.upload(0x5602825C,4,f'ahb4enr{n}.bin'))[0]
  assert clocks&16,('GPIOE clock unavailable',clocks)
  pe=struct.unpack('<6I',b.upload(0x56021000,24,f'gpioe{n}.bin'))
  pa=struct.unpack('<6I',b.upload(0x56020000,24,f'gpioa{n}.bin')) if clocks&1 else None
  sel=struct.unpack('<16I',b.upload(0x343F9000,64,f'selector{n}.bin'))
  result=dict(stage1=e,sensor=s,gpioe=pe,gpioa=pa,selector=sel,ahb4enr=clocks)
  (out/f'snapshot{n}.json').write_text(json.dumps(result,indent=2)+'\n')
  assert e[0]==0x53314552 and e[1]==17,('unexpected camera status',e[:4])
  assert s[0]==0x53454E31 and s[1]==2 and s[2]&0x80000000,s[:4]
  assert sel[5]==0,('not capture mode',sel)
  assert (pe[0]>>18)&3==1 and not (pe[1]&512) and not ((pe[3]>>18)&3) and pe[4]&512 and pe[5]&512,pe
  if pa is not None:assert ((pa[0]>>4)&3)!=1,('retired PA2 still output',pa)
  event('missing_camera_hold_high',elapsed_s=time.monotonic()-begin,external_voltage_measured=False)
 time.sleep(max(0,15-(time.monotonic()-begin)))
 event('shutdown_window_elapsed',elapsed_s=time.monotonic()-begin,standby_not_yet_independently_verified=True)
 (out/'result.json').write_text(json.dumps(dict(passed=True,normal_reset=True,cold_boot=False,
   missing_sensor_error=17,hold='PE9 output HIGH during error',pa2_driven=False,
   physical_hold_voltage_verified=False,sd_commands_by_helper=False),indent=2)+'\n')

if __name__=='__main__':main()
