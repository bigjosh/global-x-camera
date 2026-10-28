"""Copy compact evidence only; never touch instruments or source recordings."""
from pathlib import Path
import hashlib,json,shutil,gzip,zipfile
ROOT=Path(__file__).resolve().parents[3];SRC=Path(__file__).parent
DST=ROOT/'docs/power/evidence/2026-10-28-aligned-ablation'
DST.mkdir(parents=True,exist_ok=True)
def copy(p,rel=None):
    dest=DST/(rel or p.relative_to(SRC));dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(p,dest)
for p in SRC.iterdir():
    if p.is_file() and p.suffix in ('.py','.json','.csv','.svg','.png','.txt','.log'):
        copy(p,Path('analysis')/p.name if p.name.startswith(('analy','baseline-','warm-','startup-','sleep01-')) or '-aligned-analysis' in p.name or '-startup-analysis' in p.name else Path('support')/p.name)
for folder in SRC.iterdir():
    if not folder.is_dir() or folder.name.startswith('ram-'):continue
    for p in folder.rglob('*'):
        if not p.is_file():continue
        if p.name=='chunks.jsonl':
            dest=DST/p.relative_to(SRC);dest=dest.with_suffix('.jsonl.gz');dest.parent.mkdir(parents=True,exist_ok=True)
            with gzip.GzipFile(filename=str(dest),mode='wb',mtime=0) as f:f.write(p.read_bytes())
        elif p.suffix in ('.json','.jsonl','.md','.log') or p.name in ('cycle-trace.bin','producer.bin','chunks.bin'):
            copy(p)
        elif folder.name in ('sleep-probe','mdio','sdk-sources') and p.suffix in ('.py','.c','.h','.ld','.bin','.elf','.lst','.txt'):
            copy(p)
with zipfile.ZipFile(DST/'build-snapshots.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for folder in sorted(SRC.glob('ram-*')):
        if not folder.is_dir():continue
        for p in sorted(folder.rglob('*')):
            if p.is_file() and p.suffix in ('.c','.h','.inc','.ld','.S','.s','.bin','.elf','.json','.map'):
                z.write(p,p.relative_to(SRC).as_posix())
(DST/'.gitattributes').write_text('* -text\n')
files=[]
for p in sorted(DST.rglob('*')):
    if p.is_file() and p.name!='manifest.json':
        data=p.read_bytes();files.append({'path':p.relative_to(DST).as_posix(),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
(DST/'manifest.json').write_text(json.dumps({'schema':1,'raw_sample_location':str(SRC),
  'scope':'Compact evidence. Full raw analog/GPIO/range recordings and private image bytes remain in ignored tmp; per-run hashes bind them. Original build source/binaries frozen in ZIP. Analysis scripts retain original working-path assumptions.',
  'files':files},indent=2)+'\n')
print('Archived',len(files),'files;',sum(x['bytes'] for x in files),'bytes')
