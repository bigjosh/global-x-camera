"""Offline explicit-selection archive packer; dry-run until root marks complete.

No hardware modules. Source photos are hash-only. Completed evidence is packed
only with --execute --recorders-stopped and spec.status == complete. The pinned
previous archiver is used only for its generic content-addressed functions.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'firmware/capture-raw').is_dir())
DEFAULT=ROOT/'firmware/capture-raw/evidence/2026-10-24-preerase'
PRIOR=ROOT/'firmware/capture-raw/evidence/2026-10-24-raw-slots'
PINS={'archive.py':'c35290287dd9489c851296749abeebec54c44cdc179de83ffba6699a73bf3774',
      'replay.py':'f76221c82f3295526d131b3c371e3bb44538ca99c2fade92d17b34d86d649470'}

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()
def load(path,name):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def resolve(value):
    p=Path(value);p=(p if p.is_absolute() else ROOT/p).resolve();p.relative_to(ROOT);return p

def preflight(spec):
    if spec.get('schema')!=1:raise ValueError('Expected schema1')
    selection=spec['selection'];missing=[];sources=[]
    bench=resolve(selection['bench'])
    for r in selection['records']:
        sources.append(resolve(r.get('source',str(bench/r['id']))))
        sources.extend(resolve(v) for v in r.get('attachments',{}).values())
    sources.extend(resolve(v) for v in selection.get('extra_builds',[]))
    sources.extend(resolve(v) for v in selection['tools'].values())
    for p in sources:
        if not p.exists():missing.append(str(p.relative_to(ROOT)))
    for name,expected in PINS.items():
        if sha(PRIOR/name)!=expected:raise ValueError('Pinned archive support changed: '+name)
    return dict(plan_only=True,status=spec.get('status'),selected_records=len(selection['records']),
        selected_sources=len(sources),missing_sources=missing,destination=str(DEFAULT),
        hardware_access=False,can_execute=spec.get('status')=='complete' and not missing)

def write_same(path,raw):
    if path.exists() and path.read_bytes()!=raw:raise ValueError('Existing support changed: '+str(path))
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():path.write_bytes(raw)

def pack(spec,out):
    pre=preflight(spec)
    if not pre['can_execute']:raise ValueError('Incomplete selection: '+json.dumps(pre))
    if out.resolve()!=DEFAULT.resolve():raise ValueError('Unreviewed archive destination')
    # Vendor toolchains stay external. Preserve all emitted listings/map/ELF
    # files in addition to the exact generated source, manifests and binaries.
    core=load(PRIOR/'archive.py','preerase_archive_core');core.HERE=out;core.ROOT=ROOT
    original=core.collect_build
    def collect_build(folder):
        item=original(folder)
        for p in sorted(folder.rglob('*')):
            if p.is_file() and p.suffix.lower() in ('.lst','.map','.elf'):
                item['files'][p.relative_to(folder).as_posix()]=core.preserve(p)
        return item
    core.collect_build=collect_build
    index=core.collect(spec['selection'])
    index['experiment']=spec['experiment']
    index['completed_selection_sha256']=hashlib.sha256(core.json_bytes(spec)).hexdigest()
    core.save_index(index)
    (out/'selection.json').write_bytes(core.json_bytes(spec))
    for name in PINS:write_same(out/'support'/('core_'+name),(PRIOR/name).read_bytes())
    replay_source=HERE/'replay_preerase.py'
    if not replay_source.is_file():replay_source=HERE/'replay.py'
    write_same(out/'replay.py',replay_source.read_bytes())
    write_same(out/'archive.py',Path(__file__).read_bytes())
    write_same(out/'materialize.py',(PRIOR/'materialize.py').read_bytes())
    write_same(out/'.gitattributes',b'objects/** binary\nindexes/** -text\nindex.json -text\n')
    return dict(records=len(index['records']),builds=list(index['builds']),destination=str(out),
                next='Run replay.py --out qualification.json; inspect privacy and test results before committing')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--spec',type=Path,required=True)
    p.add_argument('--out',type=Path,default=DEFAULT);p.add_argument('--execute',action='store_true')
    p.add_argument('--recorders-stopped',action='store_true');a=p.parse_args();spec=json.loads(a.spec.read_bytes())
    if a.execute:
        if not a.recorders_stopped:p.error('All recorders must be stopped before hashing')
        result=pack(spec,a.out.resolve())
    else:result=preflight(spec)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
