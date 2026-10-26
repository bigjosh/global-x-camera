import sys,json,struct,time
from pathlib import Path
from datetime import datetime,timezone
root=Path.cwd();sys.path.insert(0,str(root/'firmware/capture-raw'))
import bench
folder,prepared=map(Path,sys.argv[1:3]);m=json.loads((folder/'manifest.json').read_text());plan=json.loads((prepared/'launch.json').read_text())
assert m['error_test_code']==9 and m['binary_sha256']==plan['binary_sha256']
b=bench.sd.Bench(prepared/'launch-operation')
assert b.upload(bench.LOAD,len((folder/'capture.bin').read_bytes()),'code.bin')==(folder/'capture.bin').read_bytes()
assert list(struct.unpack('<16I',b.upload(bench.REQUEST,64,'request.bin')))==plan['request_words']
e=dict(before_run=datetime.now(timezone.utc).isoformat(),code=plan['code'])
b.call('-halt','-coreReg',f"PC={hex(m['entry'])}",'XPSR=0x01000000','-run',success='Core run')
e['after_run']=datetime.now(timezone.utc).isoformat();(prepared/'run-event.json').write_text(json.dumps(e,indent=2));print(json.dumps(e),flush=True)
