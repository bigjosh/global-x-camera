"""Root-owned cold boot after verified NOR maintenance, without logic probes."""
import hashlib,json,sys,time
from datetime import datetime,timezone
from pathlib import Path
base=Path(__file__).resolve().parent
build,installation,out=map(Path,sys.argv[1:4]);out.mkdir(parents=True,exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
m=read(build/'manifest.json');sector=build/'staged/capture_sector_0.bin'
n=read(installation/'nor-after/verified.json');f=read(installation/'following-after/verified.json')
assert m['flash'] and sha(build/'capture.bin')==m['binary_sha256']
assert n['matches'] and n['bytes']==65536 and n['offset']==0 and n['sha256']==sha(sector)
assert f['matches'] and f['bytes']==4096 and f['offset']==65536
assert f['sha256']=='01cc465d3a7581d9d003b09e5db684eb7bec8e8512e12ce3565154c3aced816f'
assert time.time()-(installation/'following-after/verified.json').stat().st_mtime<600
sys.path.insert(0,str(Path.cwd()/'firmware/capture-raw'))
import bench
ram=Path('tmp/bringup/sd25-stress-20261026/ram25-scene')
prior=read(base/'pre-headers/slot-52/verified.json')
rm,code=bench.checked_build(ram,prior['binary_sha256'])
bench.terminal_gate(bench.sd.Bench(out/'idle-check'),ram,rm,code,prior,'before')
events=[]
def event(name,**kw):
    events.append(dict(name=name,utc=datetime.now(timezone.utc).isoformat(),**kw))
    (out/'events.json').write_text(json.dumps(events,indent=2));print(name,flush=True)
def js(state):
    ident=state+'-'+str(time.monotonic_ns())
    (base/'js-control.json').write_text(json.dumps(dict(id=ident,state=state)))
    until=time.monotonic()+8
    while time.monotonic()<until:
        r=read(base/'js-response.json')
        if r.get('id')==ident:
            assert r['ok'],r
            return r
        time.sleep(.05)
    raise TimeoutError('No acknowledgement; no retry')
r=js('query');assert r['range']==128 and 4.5<r['statistics']['voltage']['avg']<5.5
event('before',response=r)
event('off',response=js('off'));began=time.monotonic();time.sleep(2)
r=js('query');assert r['range']==0 and abs(r['statistics']['current']['avg'])<.0001
event('measured_off',response=r)
time.sleep(max(0,15-(time.monotonic()-began)))
r=js('query');assert r['range']==0 and abs(r['statistics']['current']['avg'])<.0001
event('off_15s',response=r)
event('on',response=js('auto'));time.sleep(10)
r=js('query');current=r['statistics']['current']['avg']
assert r['range']==128 and ((.006<current<.012) if m['standby'] else (.03<current<.25)),r
event('completion_signature',response=r,standby_expected=m['standby'],qualification='Current signature only; separate image/context/flag verification required')
proof=dict(schema=1,bench_owner='root',kind='raw-flash-cold-boot',cold_boot_confirmed=True,
    binary_sha256=m['binary_sha256'],sector_sha256=sha(sector),observed_utc=datetime.now(timezone.utc).isoformat(),
    no_debugger_or_uart_during_boot=True,rail_probe_available=False,logic_capture_available=False,
    power_off_basis='JS110 range0 and near-zero input current sustained for15s; individual target rails not probed',
    evidence=[dict(path=str(p.resolve()),sha256=sha(p)) for p in (out/'events.json',installation/'nor-after/verified.json',installation/'following-after/verified.json')])
(out/'boot-proof.json').write_text(json.dumps(proof,indent=2))
