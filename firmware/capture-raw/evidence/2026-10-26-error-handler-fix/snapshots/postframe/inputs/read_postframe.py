"""Capture post-frame error evidence during blinking, without halt or reset."""
import sys,json,time,struct,hashlib,re
from pathlib import Path
from datetime import datetime,timezone
root=Path.cwd()
sys.path.insert(0,str(root/'firmware/boot-timing'))
from nor_bench import Bench
build,signal,out=map(Path,sys.argv[1:4])
m=json.loads((build/'manifest.json').read_text())
assert m['flash'] and m['error_after_frame_test'] and m['error_blinks']
limit=time.monotonic()+40
while not signal.exists():
    if time.monotonic()>limit:raise TimeoutError('No verified cold-power-on event')
    time.sleep(.05)
launch=json.loads(signal.read_text())
age=(datetime.now(timezone.utc)-datetime.fromisoformat(launch['utc'])).total_seconds()
assert 0<=age<5,age
time.sleep(max(0,1.2-age))
b=Bench(out)
test=struct.unpack('<16I',b.upload(m['error_after_frame_proof'],64,'post-frame.bin'))
assert test[0]==0x45504631 and test[15]==0x4550444E,test
assert test[4:10]==(1,1,m['frame_bytes'],m['frame_bytes'],1,0),test
assert test[12:15]==(0,0,4),test
engine=m['error_runtime_copy']
copy=b.upload(engine['destination'],engine['bytes'],'runtime-engine.bin')
assert hashlib.sha256(copy).hexdigest()==engine['sha256']
copy_proof=struct.unpack('<3I',b.upload(engine['copy_proof'],12,'copy-proof.bin'))
assert copy_proof==(0x45435031,engine['destination'],engine['bytes']),copy_proof
old=b.upload(engine['source'],engine['bytes'],'overwritten-prefix-private.bin')
assert old!=copy
proof=b.upload(0x343FD100,384,'raw-proof.bin')
scb=b.upload(0xE000ED00,64,'scb.bin')
words=struct.unpack('<16I',scb)
assert words[10:12]==(0,0),words
enum=(build/'runtime.h').read_text().split(' RP_MAGIC,',1)[1].split('};',1)[0]
names=['RP_MAGIC']+re.findall(r'\bRP_[A-Z0-9_]+\b',enum)
decoded=dict(zip(names,struct.unpack('<96I',proof)))
assert decoded['RP_RESULT']==0x20E and decoded['RP_STATE']==15,decoded
assert decoded['RP_WRITTEN_SECTORS']==0
report=dict(passed=True,observed_utc=datetime.now(timezone.utc).isoformat(),
    launch=launch,binary_sha256=m['binary_sha256'],post_frame_words=list(test),
    copy_proof=list(copy_proof),runtime_engine_sha256=hashlib.sha256(copy).hexdigest(),
    prefix_overwritten=True,overwritten_prefix_private_sha256=hashlib.sha256(old).hexdigest(),
    raw_proof=decoded,cfsr=words[10],hfsr=words[11],
    reset=False,halt=False,target_writes=False,
    limitation='Read-only ST-LINK accesses occurred during this current trace; no optical or GPIO LED probe.')
(out/'verified.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ('passed','observed_utc','post_frame_words','runtime_engine_sha256','prefix_overwritten','cfsr','hfsr')},indent=2))
