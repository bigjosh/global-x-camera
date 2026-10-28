"""Independent offline exact-pair acceptance/rejection; no instrument clients."""
from pathlib import Path
import hashlib, importlib.util, json, shutil, tempfile
ROOT=Path(__file__).resolve().parents[4]
BASE=ROOT/'tmp/bringup/error-relocate-20261026'
OUT=BASE/'independent-review'
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def forbidden(*a,**kw): raise AssertionError('Offline audit must never construct a hardware client')
g=module('independent_recovery_gate',ROOT/'firmware/capture-timing/recovery_gpio/check_park.py'); g.Bench=forbidden
r=module('independent_readback_gate',ROOT/'firmware/capture-sd/low_power/readback_recovery/run.py');r.sd.Bench=forbidden
pairs={name:BASE/name/'staged' for name in ('flash-normal-v2','flash-postframe-v3')}
results=[]
for name,p in pairs.items():
    g.checked_build(p);r.checked_recovery(p);results.append(dict(case=name,expected='accept',both_gates_passed=True))
normal=pairs['flash-normal-v2']; diag=pairs['flash-postframe-v3']
with tempfile.TemporaryDirectory(prefix='error-recovery-review-',dir=OUT) as td:
    root=Path(td)
    cases=('prefix-truncated','prefix-guard-mutated','prefix-crc-mutated','sector-truncated','sector-mutated','normal-prefix-diag-sector','diag-prefix-normal-sector')
    for name in cases:
        p=root/name;p.mkdir()
        prefix=bytearray((normal/'stage1.bin').read_bytes());sector=bytearray((normal/'capture_sector_0.bin').read_bytes());man=json.loads((normal/'manifest.json').read_text())
        if name=='prefix-truncated':prefix=prefix[:-1]
        if name=='prefix-guard-mutated':prefix[0x390]^=1
        if name=='prefix-crc-mutated':prefix[0xC9C]^=1
        if name=='sector-truncated':sector=sector[:-1]
        if name=='sector-mutated':sector[0x3000]^=1
        if name=='normal-prefix-diag-sector':sector=bytearray((diag/'capture_sector_0.bin').read_bytes())
        if name=='diag-prefix-normal-sector':prefix=bytearray((diag/'stage1.bin').read_bytes())
        man['stage1_raw_sha256']=hashlib.sha256(prefix).hexdigest();man['program_sha256']=hashlib.sha256(sector).hexdigest()
        (p/'stage1.bin').write_bytes(prefix);(p/'capture_sector_0.bin').write_bytes(sector);(p/'manifest.json').write_text(json.dumps(man))
        failures={}
        for label,gate in (('park',g.checked_build),('readback',r.checked_recovery)):
            try:gate(p)
            except ValueError as exc:failures[label]=str(exc)
            else:raise AssertionError(name+' unexpectedly admitted by '+label)
        results.append(dict(case=name,expected='reject',both_gates_passed=True,reasons=failures))
report=dict(passed=True,offline=True,hardware_clients_constructed=False,positive_pairs=2,negative_pairs=7,gate_checks=18,results=results)
(OUT/'recovery-gate-review.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
