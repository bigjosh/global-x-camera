"""Root-owned synthetic error test. No NOR or SD writes; explicit error test build only."""
import sys,json,struct,time,hashlib
from pathlib import Path
from datetime import datetime,timezone
from types import SimpleNamespace
root=Path.cwd();sys.path.insert(0,str(root/'firmware/capture-raw'))
import bench
folder,recovery,out=map(Path,sys.argv[1:4]);which=int(sys.argv[4]);assert 1<=which<=8
m,code=bench.checked_build(folder,json.loads((folder/'manifest.json').read_text())['binary_sha256'])
assert not m['flash'] and not m['standby'] and m['error_blinks'] and m['error_test_code']==9
out.mkdir(parents=True,exist_ok=False)
boot=root/'tmp/bringup/capture-sleep-20261020/recovery-read-bridge-v1'
_,boot_code=bench.bridge.checked_bridge(boot)
b=bench.bridge.bootstrap(SimpleNamespace(recovery_build=recovery,bridge=boot),out,boot_code)
b=bench.sd.Bench(out/'operation')
b.call('-halt','-w',folder/'capture.bin',hex(bench.LOAD),'-v',success='Download verified successfully')
assert b.upload(bench.LOAD,len(code),'code-readback.bin')==code
req=bytearray(bench.request(1,261026,magic_format=True));struct.pack_into('<I',req,24,which)
(b.output/'request.bin').write_bytes(req);(b.output/'clear.bin').write_bytes(bytes(384))
b.call('-halt','-w',b.output/'request.bin',hex(bench.REQUEST),'-v','-w',b.output/'clear.bin',hex(bench.PROOF),'-v',success='Download verified successfully')
assert b.upload(bench.REQUEST,64,'request-readback.bin')==req
plan=dict(code=which,binary_sha256=hashlib.sha256(code).hexdigest(),nor_write=False,sd_write=False,expected_ms=2500*which+6400,request_words=list(struct.unpack('<16I',req)),start=datetime.now(timezone.utc).isoformat())
(out/'launch.json').write_text(json.dumps(plan,indent=2));print('PREPARED',flush=True)
if len(sys.argv)>5 and sys.argv[5]=='prepare': sys.exit(0)
print('START',flush=True)
b.call('-halt','-coreReg',f"PC={hex(m['entry'])}",'XPSR=0x01000000','-run',success='Core run')
time.sleep(1)
try:
 proof=b.upload(bench.PROOF,384,'active-error.bin');p=bench.decode(proof,bench.fields(folder))
 (out/'active-error.json').write_text(json.dumps(p,indent=2))
 gpio=b.upload(0x56021814,4,'gpio-odr.bin')
except Exception as ex:
 (out/'active-read-error.txt').write_text(repr(ex))
print('LAUNCHED',flush=True)



