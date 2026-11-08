"""Root-owned explicit NOR read/write wrappers, no reset or power commands."""
import argparse,hashlib,json,struct,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'firmware/boot-timing'))
import nor_bench
nor_bench.CLI=ROOT/'tmp/bringup/control-smoke-20261107/tools/programmer-2.23.0/bin/STM32_Programmer_CLI.exe'
def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['read','write']);p.add_argument('--out',type=Path,required=True);p.add_argument('--offset',type=lambda x:int(x,0),choices=[0,65536,131072],required=True);p.add_argument('--expect',type=Path);p.add_argument('--build',type=Path);p.add_argument('--current',type=Path);p.add_argument('--desired',type=Path);a=p.parse_args()
 if a.action=='write':
  assert a.offset in (0,65536) and a.build and a.current and a.desired
  m=json.loads((a.build/'manifest.json').read_text());assert m.get('fixed_flash_base',0)==a.offset
  if a.offset==0:assert m['binary_sha256']=='e69f0d0c3c49c2bad1ad5e7e8ff5907fcf3b251cb5b968629c18a9c57247f307'
  else:
   from build_nor_sector1 import transform,SOURCE
   assert (a.build/'source/programmer.c').read_text()==transform((SOURCE/'programmer.c').read_text())
   assert m['physical_write_window']==[65536,131072]
  sys.argv=['nor','write','--build',str(a.build),'--out',str(a.out),'--sequence',str(268000+a.offset),'--current',str(a.current),'--desired',str(a.desired)];nor_bench.main();return
 b=nor_bench.Bench(a.out);build=ROOT/'tmp/bringup/rom-nor-maintenance-readonly-20261017';m=json.loads((build/'manifest.json').read_text());binary=build/'read.bin'
 assert hashlib.sha256(binary.read_bytes()).hexdigest()==m['binary_sha256'];count=65536 if a.offset<131072 else 4096
 nonce=268100+a.offset;c=b.output/'command.bin';c.write_bytes(struct.pack('<5I',0x4E4F5244,nonce,1,count,a.offset))
 b.call('-halt','-w',binary,'0x341B0000','-v','-w',c,'0x341B4000','-v','-coreReg','PC=0x341B0001','XPSR=0x01000000','-run',success='Core run')
 time.sleep(.2)
 w=struct.unpack('<26I',b.upload(0x341B4100,104,'status.bin'));assert w[0]==0x444F4E45 and w[1]==0 and w[3]==count and w[23]==nonce and w[25]==a.offset,w
 b.call('-halt');data=b.upload(0x341D0000,count,'readback.bin');matched=None
 if a.expect:matched=data==a.expect.read_bytes();assert matched
 (b.output/'result.json').write_text(json.dumps(dict(offset=a.offset,bytes=count,sha256=hashlib.sha256(data).hexdigest(),matches=matched),indent=2),encoding='utf-8');print('Independent NOR read complete',a.offset,count,matched)
if __name__=='__main__':main()
