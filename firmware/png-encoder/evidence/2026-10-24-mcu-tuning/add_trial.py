"""Archive a CLOSED compute trial without pixels or large instrument streams."""
import argparse
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def dump(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--name',required=True)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--runner',type=Path,default=ROOT/'firmware/png-encoder/bench/run.py')
    p.add_argument('--support',type=Path,action='append',default=[])
    a=p.parse_args()
    if not a.name.replace('-','').replace('_','').isalnum():raise ValueError('Simple trial label required')
    source=a.source.resolve();source.relative_to((ROOT/'tmp').resolve())
    completed=read(source/'verified.json');plan=read(source/'plan.json')
    assert completed['runs']==len(completed['results'])>0
    assert completed['compute_only'] and not completed['sd_commands_sent']
    build=Path(plan['build']).resolve();manifest=read(build/'manifest.json')
    assert sha((build/'bench.bin').read_bytes())==completed['module_sha256']==plan['module_sha256']==manifest['binary_sha256']
    out=HERE/'trials'/a.name;out.mkdir(parents=True,exist_ok=False)
    files=[];omitted=[]
    def copy(origin,rel):
        raw=origin.read_bytes();dest=out/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        files.append(dict(original_path=origin.relative_to(ROOT).as_posix(),archived_path=rel.as_posix(),
                          bytes=len(raw),sha256=sha(raw)))
    for rel,digest in manifest['source_hashes'].items():
        path=(build/rel).resolve();path.relative_to(build)
        assert sha(path.read_bytes())==digest
        copy(path,Path('build')/rel)
    for name in ('manifest.json','bench.bin','symbols.txt','bench.lst'):
        copy(build/name,Path('build')/name)
    # Snapshot the exact host policy, not merely an import of mutable current code.
    support=[a.runner.resolve(),ROOT/'firmware/png-encoder/bench/protocol.py',
             ROOT/'firmware/png-encoder/bench/build.py',
             ROOT/'firmware/capture-sd/low_power/readback_recovery/run.py',
             ROOT/'firmware/capture-sd/bench.py',ROOT/'firmware/boot-timing/nor_bench.py',
             ROOT/'firmware/capture-timing/recovery_gpio/check_park.py',
             ROOT/'firmware/png-encoder/test_png16.py',*a.support]
    for index,path in enumerate(support):copy(path.resolve(),Path('support')/f'{index:02d}-{path.name}')
    for path in sorted(source.rglob('*')):
        if not path.is_file():continue
        rel=path.relative_to(source);size=path.stat().st_size
        pixel=(path.name in ('raw.bin','raw-readback.bin','data.bin') or path.suffix.lower()=='.png')
        redundant=(path.name.endswith('-code.bin') or path.name in ('benchmark-readback.bin','bridge-readback.bin'))
        large=(path.suffix.lower() in ('.sal','.f32','.csv') or size>1024*1024)
        if pixel or redundant or large:
            omitted.append(dict(original_path=path.relative_to(ROOT).as_posix(),bytes=size,
                reason='Pixel payload' if pixel else 'Redundant exact code readback' if redundant else 'Large recording'))
            continue
        copy(path,Path('records')/rel)
    # Reuse already archived, hash-pinned CMSIS. No vendor/runtime download.
    previous=read(ROOT/'firmware/capture-sd/evidence/2026-10-24-normal-profile/archive-v66.json')
    shared=ROOT/'firmware/capture-sd/evidence/2026-10-20-low-power'
    dependencies=[x for x in previous['shared_dependencies']['files'] if '/CMSIS/' in x['path']]
    for item in dependencies:assert sha((shared/item['path']).read_bytes())==item['sha256']
    toolchain=previous['toolchain']
    if manifest.get('mve_conversion'):
        for name in ('arm_mve.h','arm_mve_types.h','stdbool.h'):
            relative='lib/gcc/arm-none-eabi/12.3.1/include/'+name
            raw=(Path(toolchain['original_path'])/relative).read_bytes()
            toolchain['files'][relative]=dict(bytes=len(raw),sha256=sha(raw))
    dump(out/'archive.json',dict(schema=1,name=a.name,status='Closed compute trial, hardware qualification scoped to this executable',
        module_sha256=completed['module_sha256'],source_frame_sha256=completed['source_frame_sha256'],
        files=files,omitted=omitted,pixels_archived=False,hardware_accessed_by_archiver=False,
        shared_dependencies=dict(relative_archive='../../../../../capture-sd/evidence/2026-10-20-low-power',files=dependencies),
        toolchain=toolchain,runner_archive_path='support/00-'+a.runner.name,
        protocol_archive_path='support/01-protocol.py',
        replay_scope='Report/request/chunk/build identity validation; original host PNG decode metadata retained, no pixels to rerun it'))
    print(json.dumps(dict(trial=a.name,files=len(files),bytes=sum(x['bytes'] for x in files),omitted=len(omitted)),indent=2))

if __name__=='__main__':main()
