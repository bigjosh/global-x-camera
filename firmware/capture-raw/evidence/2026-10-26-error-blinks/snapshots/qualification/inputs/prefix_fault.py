"""Root-only exact installed-prefix fault injection; no storage operation."""
import json,sys,struct,hashlib,time
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime,timezone
root=Path.cwd();sys.path.insert(0,str(root/'firmware/capture-raw'))
import bench
action,build,out=sys.argv[1],Path(sys.argv[2]),Path(sys.argv[3])
assert action in ('prepare','launch')
prefix=build/'staged/stage1.bin'
raw=prefix.read_bytes()
assert len(raw)==6500 and hashlib.sha256(raw).hexdigest()=='7f8017fd70bd9b77cfabcf212d072201ec8e134c3a44a0555a2108d7cc454c32'
if action=='prepare':
    out.mkdir(parents=True,exist_ok=False)
    bridge=root/'tmp/bringup/capture-sleep-20261020/recovery-read-bridge-v1'
    _,code=bench.bridge.checked_bridge(bridge)
    bench.bridge.bootstrap(SimpleNamespace(recovery_build=build/'staged',bridge=bridge),out,code)
    b=bench.sd.Bench(out/'prepare')
    assert b.upload(0x34180400,6500,'prefix.bin')==raw
    (b.output/'result.bin').write_bytes(struct.pack('<I',17))
    b.call('-halt','-w',b.output/'result.bin','0x343f3004','-v',success='Download verified successfully')
    assert b.upload(0x343f3004,4,'result-readback.bin')==struct.pack('<I',17)
    bench.sd.context_proof(b,{bench.bridge.BOOT_PARK},'prepared')
    (out/'plan.json').write_text(json.dumps(dict(prefix_sha256=hashlib.sha256(raw).hexdigest(),
        code=2,entry=0x34181821,nominal_ms=11400,sd_write=False,nor_write=False,
        injection='stage1 result17, call exact installed stage1 bridge',prepared_utc=datetime.now(timezone.utc).isoformat()),indent=2))
else:
    p=json.loads((out/'plan.json').read_text());assert p['entry']==0x34181821 and p['code']==2
    b=bench.sd.Bench(out/'launch')
    assert b.upload(0x34180400,6500,'prefix.bin')==raw
    assert b.upload(0x343f3004,4,'result.bin')==struct.pack('<I',17)
    bench.sd.context_proof(b,{bench.bridge.BOOT_PARK},'before')
    event=dict(before_run=datetime.now(timezone.utc).isoformat(),code=2,entry=p['entry'])
    b.call('-halt','-coreReg','PC=0x34181821','XPSR=0x01000000','-run',success='Core run')
    event['after_run']=datetime.now(timezone.utc).isoformat()
    (out/'run-event.json').write_text(json.dumps(event,indent=2));print(json.dumps(event),flush=True)
