"""Bind one completed measured cold boot to the independently installed image.
Offline only; this does not infer image integrity or physical Standby.
"""
from pathlib import Path
import hashlib,json,sys
build,installation,trace,out=[Path(p).resolve() for p in sys.argv[1:5]]
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bound(p):return dict(path=str(p),sha256=sha(p))
m=read(build/'manifest.json');p=read(build/'staged/manifest.json')
i=read(installation/'complete.json');r=read(trace/'result.json')
events=[json.loads(line) for line in (trace/'events.jsonl').read_text().splitlines()]
assert i['passed'] and i['independent_full_readback'] and i['following4096_unchanged']
assert m['flash'] and not m['standby']
assert i['new_sector_sha256']==p['program_sha256']==sha(build/'staged/capture_sector_0.bin')
assert m['binary_sha256']==sha(build/'capture.bin')==p['stage2_full_sha256']
assert r['success'] and not r['errors'] and not r['cleanup_errors']
names=[e['event'] for e in events]
assert all(names.count(n)==1 for n in ('power_off','off_verified','power_on','observation_end','closed'))
off=events[names.index('off_verified')];on=events[names.index('power_on')]
assert off['seconds']>=15 and abs(off['mean_a'])<.0001
assert names.index('power_off')<names.index('off_verified')<names.index('power_on')<names.index('observation_end')
record=dict(schema=1,bench_owner='root',kind='raw-flash-cold-boot',
    cold_boot_confirmed=True,observed_utc=r['utc'],binary_sha256=m['binary_sha256'],
    sector_sha256=p['program_sha256'],source_power_off_seconds=off['seconds'],power_on_utc=on['utc'],
    scope='Verified JS output-off current interval and one normal FLASH boot; individual target rails not probed.',
    evidence=[bound(q) for q in (installation/'complete.json',trace/'result.json',trace/'events.jsonl',
        build/'manifest.json',build/'staged/manifest.json')])
with out.open('x',encoding='utf-8') as f:json.dump(record,f,indent=2);f.write('\n')
print('COLD_BOOT_BOUND',out)
