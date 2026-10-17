import sys,struct,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path('firmware/boot-timing').resolve()))
from nor_bench import Bench
b=Bench(Path(sys.argv[1])); build=Path('tmp/bringup/rom-nor-maintenance-readonly-20261017')
m=json.loads((build/'manifest.json').read_text()); binary=build/'read.bin'
assert hashlib.sha256(binary.read_bytes()).hexdigest()==m['binary_sha256']
c=b.output/'command.bin'; c.write_bytes(struct.pack('<5I',0x4E4F5244,201,1,4096,65536))
b.call('-halt','-w',binary.resolve(),'0x341B0000','-v','-w',c,'0x341B4000','-v','-coreReg','PC=0x341B0001','XPSR=0x01000000','-run',success='Core run')
w=struct.unpack('<26I',b.upload(0x341B4100,104,'status.bin'))
s=dict(zip(m['status_fields_in_word_order'],w)); (b.output/'status.json').write_text(json.dumps(s,indent=2))
assert w[0]==0x444F4E45 and w[1]==0 and w[3]==4096 and w[23]==201 and w[25]==65536,s
b.call('-halt'); data=b.upload(0x341D0000,4096,'following-sector.bin')
ref=(build/'following-sector-before.bin').read_bytes(); assert data==ref
print(json.dumps({'guard_matches':True,'sha256':hashlib.sha256(data).hexdigest()}))
