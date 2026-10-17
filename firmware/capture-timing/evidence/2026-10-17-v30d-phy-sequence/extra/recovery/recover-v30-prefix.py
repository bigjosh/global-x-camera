import sys,struct,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path('firmware/capture-timing').resolve()))
from prepare_maintenance import Bench,registers,validate_context,sha
b=Bench(Path('tmp/bringup/phy-v30-prefix-maintenance'))
code=b.upload(0x34180400,4332,'live-prefix.bin')
assert sha(code)=='36f13702f0343eb3e1ff4578a3a590ee6ec8d4de1bae158fbcdf03efbdca8170'
trace=struct.unpack('<64I',b.upload(0x343f0000,256,'trace.bin'))
s=struct.unpack('<53I',b.upload(0x343f3000,212,'prefix-status.bin'))
assert trace[0]==0x43545031 and trace[1]==0xe1000011 and trace[3]==17
assert s[0]==0x53314552 and s[1]==17 and s[3]==0 and s[24]==0
ctx=registers(b.call('-halt','-coreReg'));validate_context(ctx)
assert ctx['PC'] in [0x341804e6,0x341804e8] and ctx['PRIMASK']==1 and ctx['CONTROL']==0
fp,=struct.unpack('<I',b.upload(0xe000ef34,4,'fpccr.bin'));assert not fp&1
cache=Path('tmp/bringup/capture-maintenance-cache-raw10-20261017/cache_prep.bin').resolve()
raw=cache.read_bytes();assert sha(raw)=='59427aa1c107a24378a35c3f85eb7f7d4fc1209115a319f05d3322646f62943d'
present=b.upload(0x343c0000,len(raw),'cache-before.bin');assert present==raw or not any(present)
clear=b.output/'clear.bin';clear.write_bytes(bytes(20))
b.call('-halt','-w',clear,'0x343c0400','-v','-w',cache,'0x343c0000','-v','-coreReg','PRIMASK=1','PC=0x343c0001','XPSR=0x01000000','-run',success='Core run')
after=struct.unpack('<5I',b.upload(0x343c0400,20,'cache-after.bin'))
assert after[0]==0x43414348 and after[3]==0 and not after[4]&0x30000
park=registers(b.call('-halt','-coreReg'));assert park['PC'] in [0x343c0072,0x343c0074] and park['PRIMASK']==1
b.call('-coreReg','CONTROL=0','PRIMASK=1');final=registers(b.call('-coreReg'));validate_context(final)
assert final['CONTROL']==0 and final['PRIMASK']==1
result={'initial':ctx,'prefix_sha256':sha(code),'prefix_failure':17,'no_receiver_or_nor_start':True,'fpccr':fp,'cache_status':after,'final':final,'flash_commands_sent':False}
(b.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
