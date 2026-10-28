"""Offline exact-byte compact archive; no instruments. Refuses overwrite."""
from pathlib import Path
import gzip,hashlib,json,shutil
S=Path(__file__).resolve().parent;R=S.parents[2]
D=R/'docs/power/evidence/2026-10-28-isolated-nucleo'
D.mkdir(parents=True,exist_ok=False)
files=[];raw=[]
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def copy(p,rel):
    dst=D/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dst)
for p in sorted(S.rglob('*')):
    if not p.is_file() or '__pycache__' in p.parts:continue
    rel=p.relative_to(S)
    if p.suffix in ('.f32','.u1'):
        raw.append(dict(path=rel.as_posix(),bytes=p.stat().st_size,sha256=sha(p)));continue
    if p.suffix in ('.pdf','.o','.obj') or p.name=='schematic-text.txt':continue
    if p.name=='chunks.jsonl':
        dst=D/rel.with_suffix('.jsonl.gz');dst.parent.mkdir(parents=True,exist_ok=True)
        with gzip.GzipFile(filename=str(dst),mode='wb',mtime=0) as f:f.write(p.read_bytes())
    else:copy(p,rel)
for n in ('analyze_warm_ablations.py','analyze_existing_baseline.py'):
    copy(S.parent/'power-ablation-20261028'/n,Path('support/analysis-dependencies')/n)
for src in ('firmware/capture-raw/power_phy.inc','firmware/capture-raw/test_power_phy.py',
            'firmware/capture-sd/low_power/read_standby_flag.py',
            'firmware/capture-timing/recovery_gpio/check_park.py'):
    copy(R/src,Path('support/repository-snapshot')/src)
copy(S.parent/'sd125-negedge-20261026/uart_recover.py',Path('support/uart_recover.py'))
(D/'.gitattributes').write_text('* -text\n')
(D/'raw-recordings.json').write_text(json.dumps(dict(source=str(S),files=raw),indent=2)+'\n')
for p in sorted(D.rglob('*')):
    if p.is_file():files.append(dict(path=p.relative_to(D).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
assert sum(x['bytes'] for x in files)<100*1024**2,'Review archive size'
(D/'manifest.json').write_text(json.dumps(dict(schema=1,source=str(S),scope='Exact compact records, frozen experimental builds, host scripts and analysis. Raw analog/GPI files remain in ignored tmp; hashes in raw-recordings.json. Analysis retains original workspace assumptions and imported helper dependencies. No claim of self-contained toolchain/SDK distribution. chunks.jsonl is losslessly gzip-compressed.',files=files),indent=2)+'\n')
print(json.dumps(dict(archive=str(D),files=len(files),bytes=sum(x['bytes'] for x in files),raw_bytes=sum(x['bytes'] for x in raw)),indent=2))
