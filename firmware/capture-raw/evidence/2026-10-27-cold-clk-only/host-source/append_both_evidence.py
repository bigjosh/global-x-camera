"""Offline final comparison archive assembly; no instrument access."""
import gzip,hashlib,json
from pathlib import Path
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'NOTES.md').is_file() and (p/'firmware').is_dir())
S=ROOT/'tmp/bringup/sd-cold-cmd-probe-20261027'
D=ROOT/'firmware/capture-raw/evidence/2026-10-27-cold-clk-only'
sha=lambda b:hashlib.sha256(b).hexdigest()
origins=json.loads((D/'source-origins.json').read_text())
def copy(src,dst):
    raw=src.read_bytes();target=D/dst;target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():assert target.read_bytes()==raw
    else:target.write_bytes(raw)
    origins[target.relative_to(D).as_posix()]={'source':src.relative_to(ROOT).as_posix(),'bytes':len(raw),'sha256':sha(raw)}
for name,target in [('both01-observation','attempts/both01/observation'),('both-warm-pio25-01','attempts/both-warm-pio25-01')]:
    for path in sorted((S/name).rglob('*')):
        if path.is_file():copy(path,Path(target)/path.relative_to(S/name))
for source,target in [('both01-ready.json','attempts/both01/ready.json'),
    ('both01-current.power-on.json','attempts/both01/power-on.json'),
    ('both-warm-pio25-01-console.log','attempts/both-warm-pio25-01/console.log'),
    ('both01-current-summary.json','reports/both01-current-summary.json'),
    ('both01-current-signature.json','reports/both01-current-signature.json'),
    ('summarize_signature.py','host-source/summarize_signature.py')]:copy(S/source,target)
raw=(S/'both01-current.jsonl').read_bytes();assert json.loads(raw.splitlines()[-1])['event']=='stopped'
blob=gzip.compress(raw,compresslevel=9,mtime=0);assert gzip.decompress(blob)==raw
target=D/'traces/both01-current.jsonl.gz';target.write_bytes(blob)
record=json.loads((D/'compression.json').read_text())
assert not any(r['path']==target.relative_to(D).as_posix() for r in record['traces'])
record['traces'].append(dict(path=target.relative_to(D).as_posix(),
    original_path=(S/'both01-current.jsonl').relative_to(ROOT).as_posix(),
    original_bytes=len(raw),original_sha256=sha(raw),compressed_bytes=len(blob),compressed_sha256=sha(blob)))
for name,value in [('compression.json',record),('source-origins.json',origins)]:
    (D/name).write_text(json.dumps(value,indent=2)+'\n')
print('Both-probe records added; no hardware access.')
