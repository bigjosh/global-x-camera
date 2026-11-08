"""Explicit RAM USB launcher/status reader. Only the bench owner uses this."""
import argparse,contextlib,hashlib,importlib.util,io,json,secrets,struct,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'firmware/boot-timing'))
import nor_bench
nor_bench.CLI=ROOT/'tmp/bringup/control-smoke-20261107/tools/programmer-2.23.0/bin/STM32_Programmer_CLI.exe'
def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def save(path,x):path.write_text(json.dumps(x,indent=2)+'\n',encoding='utf-8')
def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['launch','status','stop','replace']);p.add_argument('--out',type=Path,required=True);p.add_argument('--build',type=Path);p.add_argument('--session',type=Path);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
 b=nor_bench.Bench(a.out/'operations')
 bridge=module('usb_bridge',ROOT/'firmware/capture-sd/low_power/readback_recovery/run.py')
 if a.action in ('launch','replace'):
  m=json.loads((a.build/'manifest.json').read_text(encoding='utf-8'));code=(a.build/'usb.bin').read_bytes();assert hashlib.sha256(code).hexdigest()==m['sha256']
  assert m['load']==0x34300000 and m['proof']==0x343F8000 and m['request']==0x343F7F00 and m['bss_end']<0x343E0000
  assert code[m['park']-m['load']:m['park']-m['load']+2]==b'\xfe\xe7'
  if a.action=='launch':
   guard=module('usb_guard',ROOT/'firmware/capture-timing/recovery_gpio/check_park.py');recovery=ROOT/'tmp/bringup/sensor-autostop-promote-20261028/flash-standby-v1/staged'
   identity=bridge.checked_recovery(recovery);saved_argv=sys.argv;output=io.StringIO()
   try:
    sys.argv=['guard','--build',str(recovery),'--out',str(a.out/'early-guard')]
    with contextlib.redirect_stdout(output):guard.main()
   finally:sys.argv=saved_argv;(a.out/'guard.log').write_text(output.getvalue(),encoding='utf-8')
   bridge.checked_recovery_result(json.loads((a.out/'early-guard/result.json').read_text()),identity)
   bp=ROOT/'tmp/bringup/capture-sleep-20261020/recovery-read-bridge-v1';_,bc=bridge.checked_bridge(bp)
   nonce=secrets.randbelow(0xFFFFFFFF)+1;request=struct.pack('<4I',0x52425231,nonce,0,0)
   (b.output/'bridge-request.bin').write_bytes(request);(b.output/'bridge-clear.bin').write_bytes(bytes(92))
   b.call('-halt','-w',bp/'boot.bin',hex(bridge.LOAD),'-v',success='Download verified successfully')
   assert b.upload(bridge.LOAD,len(bc),'bridge-readback.bin')==bc
   b.call('-halt','-w',b.output/'bridge-clear.bin',hex(bridge.BOOT_PROOF),'-v','-w',b.output/'bridge-request.bin',hex(bridge.BOOT_REQUEST),'-v',success='Download verified successfully')
   assert b.upload(bridge.BOOT_REQUEST,16,'bridge-request-readback.bin')==request
   b.call('-halt','-coreReg','PC=0x341E0001','XPSR=0x01000000','-run',success='Core run')
   save(a.out/'bridge-proof.json',bridge.wait_boot(b,nonce));bridge.sd.context_proof(b,{bridge.BOOT_PARK},'bridge-final')
   assert struct.unpack_from('<2I',b.upload(0x341F5000,128,'memory-proof.bin'))==(0x5231304D,0)
  else:
   old=json.loads(a.session.read_text());om=old['manifest'];oc=(Path(old['build'])/'usb.bin').read_bytes()
   assert b.upload(om['load'],len(oc),'prior-code.bin')==oc
   vals=struct.unpack('<64I',b.upload(om['proof'],256,'prior-status.bin'))
   assert vals[0]==0x31505450 and vals[2]==8 and vals[3]==old['nonce'] and vals[14]==1
   bridge.sd.context_proof(b,{om['park']},'prior-context')
  b.call('-halt','-w',a.build/'usb.bin',hex(m['load']),'-v',success='Download verified successfully')
  assert b.upload(m['load'],len(code),'code-readback.bin')==code
  nonce=secrets.randbelow(0xFFFFFFFF)+1;request=struct.pack('<8I',0x31505450,nonce,0,0,0,0,0,0)
  (b.output/'request.bin').write_bytes(request);(b.output/'clear.bin').write_bytes(bytes(256))
  b.call('-halt','-w',b.output/'request.bin',hex(m['request']),'-v','-w',b.output/'clear.bin',hex(m['proof']),'-v',success='Download verified successfully')
  assert b.upload(m['request'],32,'request-readback.bin')==request
  save(a.out/'session.json',dict(build=str(a.build.resolve()),manifest=m,nonce=nonce))
  b.call('-halt','-coreReg','PC='+hex(m['entry']),'XPSR=0x01000000','-run',success='Core run')
  print('USB RAM candidate launched; no NOR writes.');return
 session=json.loads(a.session.read_text());m=session['manifest']
 values=struct.unpack('<64I',b.upload(m['proof'],256,'status.bin'));assert values[0]==0x31505450 and values[3]==session['nonce']
 if a.action=='stop':
  if values[2]!=4:raise ValueError('USB application not in normal service state')
  # Cooperative flag; no reset/halt and no interruption of the current SD call.
  stop=b.output/'stop.bin';stop.write_bytes(struct.pack('<I',0x504F5453));b.call('-w',stop,hex(m['request']+28),'-v',success='Download verified successfully');time.sleep(.5)
  values=struct.unpack('<64I',b.upload(m['proof'],256,'stopped.bin'));assert values[2]==8
 result={'status':values}
 for key,index,words in [('ptp',4,32),('usb',5,32),('log',6,1024),('card',7,60),('vbus',30,16)]:
  if 0x34300000<=values[index]<0x343E0000:result[key]=struct.unpack('<'+'I'*words,b.upload(values[index],words*4,key+'.bin'))
 save(a.out/'status.json',result);print(json.dumps({k:v for k,v in result.items() if k not in ('log','card')}))
if __name__=='__main__':main()
