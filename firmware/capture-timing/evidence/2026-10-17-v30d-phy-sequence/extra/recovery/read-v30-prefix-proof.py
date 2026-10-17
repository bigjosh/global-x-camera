import sys,struct,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path('firmware/boot-timing').resolve()))
from nor_bench import Bench
b=Bench(Path('tmp/bringup/phy-v30-prefix-recovery-proof'))
code=b.upload(0x34180400,4332,'live-prefix.bin')
assert hashlib.sha256(code).hexdigest()=='36f13702f0343eb3e1ff4578a3a590ee6ec8d4de1bae158fbcdf03efbdca8170'
trace=struct.unpack('<64I',b.upload(0x343F0000,256,'trace.bin'))
status=struct.unpack('<53I',b.upload(0x343F3000,212,'prefix-status.bin'))
sensor=struct.unpack('<40I',b.upload(0x343F4000,160,'sensor-status.bin'))
assert trace[0]==0x43545031 and trace[1]==0xE1000011 and trace[3]==17
assert status[0]==0x53314552 and status[1]==17 and status[3]==0 and status[24]==0
regs={}
for name,address,length in [('apb5rstr',0x5602823c,4),('rcc_cfgr',0x56028020,8),('rcc_pll1',0x56028080,12),('xspi',0x58025000,36),('xspi_ccr',0x58025100,20),('xspim',0x5802b400,4),('cpu_ccr',0xe000ed14,4)]:
 regs[name]=list(struct.unpack('<'+'I'*(length//4),b.upload(address,length,name+'.bin')))
assert not regs['xspi'][8]&0x3f24
assert not regs['cpu_ccr'][0]&0x10000
print(json.dumps({'trace':trace[:6],'prefix_status':status,'sensor':sensor,'registers':{k:[hex(x) for x in v] for k,v in regs.items()}},indent=2))
