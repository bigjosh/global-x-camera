"""One root-owned no-sensor cold power cycle, with stats and optional IN0 HOLD.
No NOR/SD writes. Requires a fresh exact PA2 UART park; snapshots do not halt.
OFF remains OFF on cleanup if a failure occurs before power is restored.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,queue,struct,sys,threading,time
from datetime import datetime,timezone
ROOT=Path.cwd();sys.path.insert(0,str(ROOT/'tmp/bringup/joulescope-deps'))
sys.path.insert(0,str(ROOT/'firmware/boot-timing'))
import numpy as np
from pyjoulescope_driver import Driver
import nor_bench
nor_bench.CLI=ROOT/'tmp/bringup/control-smoke-20261107/tools/programmer-2.23.0/bin/STM32_Programmer_CLI.exe'
PREFIX='852bc7724a9fc0267fb37e3f93ba52f22137c65c55f2cece47d17dd352093084'
DEVICE='u/js110/000163';RANGE='s/i/range/select'
SETTINGS={'h/fs':2000000,'s/extio/voltage':3300,'s/i/lsb_src':2,'s/v/lsb_src':3,
          's/i/ctrl':1,'s/v/ctrl':1,'s/gpi/0/ctrl':1,'s/sstats/ctrl':1}
def clean(x):
 if isinstance(x,np.generic):return x.item()
 if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
 if isinstance(x,(list,tuple)):return [clean(v) for v in x]
 return x
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--park-proof',type=Path,required=True);p.add_argument('--hold-probe',action='store_true');a=p.parse_args()
 proof=json.loads(a.park_proof.read_text());assert proof['passed'] and proof['prefix_sha256']==PREFIX and proof['context']['PC']==0x3418078C
 assert 0<=time.time()-a.park_proof.stat().st_mtime<600
 out=a.out.resolve();out.mkdir(parents=True,exist_ok=False);b=nor_bench.Bench(out/'snapshots')
 ref=ROOT/'firmware/usb-ptp/evidence/2026-11-09-a3-hold/package-pa2/stage1.bin'
 assert hashlib.sha256(ref.read_bytes()).hexdigest()==PREFIX
 assert b.upload(0x34180400,7160,'pre-prefix.bin')==ref.read_bytes()
 spec=importlib.util.spec_from_file_location('park_guard',ROOT/'firmware/capture-timing/recovery_gpio/check_park.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
 r=guard.registers(b.call('-coreReg'))
 assert r['PC']==0x3418078C and r['CONTROL']==0 and (r['XPSR']&0x1FF)==0 and r['PRIMASK']==1 and r['FAULTMASK']==0
 pa=struct.unpack('<6I',b.upload(0x56020000,24,'pre-gpioa.bin'));assert (pa[0]>>4)&3==1 and pa[4]&4
 q=queue.Queue(2048);errors=[];stats=[];last_gpio={};events=[];changed=[];initial={};final={};success=False
 def event(name,**kw):
  e=dict(event=name,utc=datetime.now(timezone.utc).isoformat(),monotonic=time.monotonic(),**kw);events.append(e);(out/'events.json').write_text(json.dumps(events,indent=2));print(json.dumps(e),flush=True)
 def callback(topic,value):
  try:
   v=dict(value)
   if 'data' in v:v['data']=np.array(v['data'],copy=True)
   q.put_nowait((topic,v,time.monotonic()))
  except Exception as ex:errors.append(repr(ex))
 def writer():
  offset=0
  try:
   with (out/'gpi0.u1').open('xb') as data,(out/'chunks.jsonl').open('x') as chunks,(out/'stats.jsonl').open('x') as sf:
    while True:
     item=q.get()
     if item is None:break
     topic,v,when=item
     if topic.endswith('s/sstats/value'):
      row=dict(received_monotonic=when,**clean(v));stats.append(row);sf.write(json.dumps(row)+'\n');continue
     arr=v.pop('data');assert arr.dtype==np.uint8
     payload=arr.tobytes();assert offset+len(payload)<32*1024**2
     data.write(payload);row=dict(byte_offset=offset,byte_count=len(payload),received_monotonic=when,**clean(v));offset+=len(payload)
     chunks.write(json.dumps(row)+'\n');last_gpio.update(received=when,high_fraction=float(np.unpackbits(arr,bitorder='little').mean()))
  except Exception as ex:errors.append(repr(ex))
 thread=threading.Thread(target=writer,daemon=True);thread.start()
 def latest():
  assert not errors,errors
  assert stats and time.monotonic()-stats[-1]['received_monotonic']<1
  s=stats[-1]['signals'];i=s['current']['avg']['value'];v=s['voltage']['avg']['value'];assert 4.5<v<5.5
  return i,v
 try:
  with Driver() as d:
   with d.open(DEVICE,mode='restore',timeout=5) as dev:
    initial={k:dev.query(k,timeout=5) for k in (RANGE,*SETTINGS)};assert initial[RANGE]==128
    topics=[DEVICE+'/s/gpi/0/!data',DEVICE+'/s/sstats/value']
    try:
     for t in topics:d.subscribe(t,'pub',callback)
     for k,v in SETTINGS.items():
      if initial[k]!=v:changed.append(k);dev.publish(k,v,timeout=5);assert dev.query(k,timeout=5)==v
     time.sleep(1.5);i,v=latest();assert .02<i<.25
     if a.hold_probe:assert time.monotonic()-last_gpio['received']<1 and last_gpio['high_fraction']>.999,last_gpio
     event('initial',current_A=i,source_V=v,hold_probe=a.hold_probe,gpi0=dict(last_gpio))
     dev.publish(RANGE,0,timeout=5);assert dev.query(RANGE,timeout=5)==0;off=time.monotonic();event('power_off')
     while time.monotonic()-off<15:time.sleep(.1);latest()
     i,v=latest();assert abs(i)<.0001
     if a.hold_probe:assert time.monotonic()-last_gpio['received']<1 and last_gpio['high_fraction']<.001,last_gpio
     event('off_current_verified',current_A=i,seconds=time.monotonic()-off,all_target_rails_verified=False)
     dev.publish(RANGE,128,timeout=5);assert dev.query(RANGE,timeout=5)==128;on=time.monotonic();event('power_on')
     time.sleep(1.5)
     # The disconnected sensor should be in its bounded two-blink error path.
     e=struct.unpack('<53I',b.upload(0x343F3000,212,'stage1-error.bin'))
     s=struct.unpack('<32I',b.upload(0x343F4000,128,'sensor-status.bin'))
     pa=struct.unpack('<6I',b.upload(0x56020000,24,'error-gpioa.bin'))
     (out/'error-snapshot.json').write_text(json.dumps(dict(stage1_error=e,sensor=s,gpioa=pa),indent=2))
     assert e[0]==0x53314552 and e[1]==17,e[:5]
     assert s[0]==0x53454E31 and s[1]==2 and s[2]&0x80000000,s[:5]
     assert (pa[0]>>4)&3==1 and (pa[3]>>4)&3==0 and pa[4]&4 and pa[5]&4
     event('camera_error_hold_high',elapsed=time.monotonic()-on,error17=e[1])
     while time.monotonic()-on<15:time.sleep(.1);latest()
     i,v=latest();event('final_observation',current_A=i,source_V=v,gpi0=dict(last_gpio),elapsed=time.monotonic()-on)
     # This early failure never runs the normal Ethernet power-down step;
     # a different idle current is not by itself a shutdown failure.
     if a.hold_probe:assert time.monotonic()-last_gpio['received']<1 and last_gpio['high_fraction']<.001,last_gpio
     success=True
    finally:
     for k in reversed(changed):dev.publish(k,initial[k],timeout=5)
     for t in topics:d.unsubscribe(t,callback)
     final={k:dev.query(k,timeout=5) for k in (RANGE,*SETTINGS)}
     assert all(final[k]==initial[k] for k in SETTINGS)
     event('closed_settings_restored',final_range=final[RANGE])
 finally:
  try:q.put(None,timeout=2)
  except queue.Full:errors.append('Writer queue did not drain during bounded cleanup')
  thread.join(5)
  if thread.is_alive():errors.append('Writer did not stop during bounded cleanup')
  result=dict(success=success,errors=errors,initial=initial,final=final,hold_probe=a.hold_probe,stats_count=len(stats),all_target_rails_verified=False,sd_writes=False,nor_writes=False)
  (out/'result.json').write_text(json.dumps(result,indent=2));assert not errors,errors
if __name__=='__main__':main()
