"""Freeze compact, exact PIO/IDMA read evidence; never accesses hardware.

Initial freeze remains unsealed. Addenda occupy a distinct labeled subtree;
captured bytes are never overwritten. seal is an explicit later action.
ELF/object files, full frames and the historical262KiB payload are excluded.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT=next(p for p in Path(__file__).resolve().parents
    if (p/'NOTES.md').is_file() and (p/'firmware/capture-raw').is_dir())
SOURCE=ROOT/'tmp/bringup/sd-read-pio-dma-20261027'
OUT=ROOT/'firmware/capture-raw/evidence/2026-10-27-pio-idma-read'
ATTEMPTS=('reference125','pio25-01','idma25-01','idma25-02','pio25-02','pio25-03','idma25-03')
BUILDS=('ram-pio125','ram-pio25','ram-idma25')
MAX_FILE=4*1024*1024

def require(ok,message):
    if not ok: raise ValueError(message)

def sha(data): return hashlib.sha256(data).hexdigest()
def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def now(): return datetime.now(timezone.utc).isoformat()
def encoded(value): return (json.dumps(value,indent=2,allow_nan=False)+'\n').encode()

def child(base,relative):
    result=(base/relative).resolve()
    result.relative_to(base.resolve())
    return result

class Archive:
    def __init__(self,source,out):
        self.source=source.resolve();self.out=out.resolve()
        self.out.relative_to(ROOT/'firmware/capture-raw/evidence')
        self.out.mkdir(parents=True,exist_ok=True)
        index=self.out/'archive-index.json'
        self.index=read(index) if index.exists() else dict(schema=1,created_utc=now(),
            source=str(self.source),sealed=False,hardware_access=False,files={},addenda=[])
        require(not self.index['sealed'],'Archive is sealed; do not add or rewrite captured evidence')

    def put(self,relative,data,source=None):
        require(len(data)<=MAX_FILE,'Unexpected large file: '+str(relative))
        path=child(self.out,relative)
        require(path.suffix.lower() not in ('.o','.elf','.png','.sal','.jls'),
            'Excluded large/private artifact: '+str(relative))
        key=path.relative_to(self.out).as_posix()
        info=dict(bytes=len(data),sha256=sha(data))
        if source is not None: info['source']=source
        if path.exists():
            require(path.read_bytes()==data,'Captured file already exists with different bytes: '+key)
        else:
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as file: file.write(data)
        if key in self.index['files']:
            require(self.index['files'][key]['sha256']==info['sha256'],'Index identity changed')
        else: self.index['files'][key]=info
        return key

    def copy(self,path,relative):
        path=Path(path).resolve()
        size=path.stat().st_size
        require(size<=MAX_FILE,'Unexpected large source: '+str(path))
        data=path.read_bytes()
        require(len(data)==size and path.stat().st_size==size,'Source changed while reading: '+str(path))
        return self.put(relative,data,str(path))

    def tree(self,path,relative):
        path=Path(path).resolve()
        require(path.is_dir(),'Missing evidence directory: '+str(path))
        for item in sorted(path.rglob('*')):
            if not item.is_file() or '__pycache__' in item.parts: continue
            require(item.suffix.lower() in ('.bin','.json','.jsonl','.log','.txt'),
                'Unexpected evidence extension: '+str(item))
            if item.name in ('sectors.bin','read-buffer.bin','reference-header.bin'):
                require(item.stat().st_size==512,'Only one512-byte pattern sector may be archived')
            require(item.name not in ('frame.bin','slot.bin'),'Private frame/object excluded')
            self.copy(item,Path(relative)/item.relative_to(path))

    def js_prefix(self,label):
        path=self.source/'js-session.jsonl'
        if not path.exists(): return
        data=path.read_bytes()
        data=data[:data.rfind(b'\n')+1]
        require(data,'No complete JS log records')
        for line in data.splitlines(): json.loads(line)
        relative=f'status/{label}-js-session-prefix.jsonl'
        self.put(relative,data,dict(path=str(path),snapshot_utc=now(),
            prefix_bytes=len(data),source_may_still_be_growing=True))

    def save(self):
        self.index['updated_utc']=now()
        self.index['files']=dict(sorted(self.index['files'].items()))
        (self.out/'archive-index.json').write_bytes(encoded(self.index))
        return verify(self.out)

def freeze_builds(archive):
    manifests={name:read(archive.source/name/'manifest.json') for name in BUILDS}
    dependencies={}
    for name,m in manifests.items():
        folder=archive.source/name
        require(sha((folder/'capture.bin').read_bytes())==m['binary_sha256'],
            'Build executable differs: '+name)
        require(m['sd_read_diagnostics'] is True and m['sd_bus_width']==4 and
            m['sd_gpio_speed']==3 and m['sd_clock_negedge'] is True and
            m['sd_clock_negedge_init'] is True and not m['flash'] and not m['standby'],
            'Unexpected build profile: '+name)
        for artifact in ('capture.bin','manifest.json','capture.lst','capture.map','symbols.txt'):
            archive.copy(folder/artifact,f'builds/{name}/{artifact}')
        source_map={}
        for filename,expected in m['source_hashes'].items():
            path=child(folder,filename)
            require(sha(path.read_bytes())==expected,'Frozen source differs: '+str(path))
            relative=f'build-inputs/{expected}/{Path(filename).name}'
            archive.copy(path,relative)
            source_map[filename]=dict(sha256=expected,archive_path=relative)
        archive.put(f'builds/{name}/source-map.json',encoded(source_map))
        # External SDK/include inventory is hashed once, not duplicated per profile.
        for flag in m['flags']:
            if not flag.startswith('-I'): continue
            include=Path(flag[2:]).resolve()
            if include==folder.resolve() or str(include) in dependencies: continue
            require(include.is_dir(),'Missing external include directory: '+str(include))
            files={}
            for path in sorted(include.rglob('*.h')):
                files[path.relative_to(include).as_posix()]=dict(bytes=path.stat().st_size,
                    sha256=sha(path.read_bytes()))
            dependencies[str(include)]=files
    archive.put('builds/external-include-inventory.json',encoded(dict(
        copied=False,reason='External SDK and base include trees remain prerequisites; no full SDK duplication',
        includes=dependencies)))

def freeze_reference(archive):
    folder=ROOT/'tmp/bringup/raw-frontmeta-20261024/bench/preservation/payload-0000'
    proof=read(folder/'verified.json'); payload=(folder/'sectors.bin').read_bytes()
    require(proof['passed'] is True and proof['proof']['read_lba']==0 and
        len(payload)==262144 and sha(payload)==proof['read_sha256'],'Historical complete source differs')
    header=payload[:512]
    archive.put('reference/historical-header.bin',header,str(folder/'sectors.bin')+' bytes[0:512]')
    archive.copy(folder/'verified.json','reference/historical-read-proof.json')
    archive.put('reference/provenance.json',encoded(dict(schema=1,
        historical_header_sha256=sha(header),historical_full_payload=dict(
            path=str(folder/'sectors.bin'),bytes=len(payload),sha256=sha(payload),
            full_hash_verified=True),copied_payload_bytes=512,
        privacy='Sensor-generated pattern header only; no full image or historical262144-byte block copied')))

def freeze_scripts(archive):
    for name in ('run_read.py','test_read.py','analyze_reads.py','archive_results.py'):
        archive.copy(archive.source/name,f'replay/{name}')
    for folder,patterns in (
        ('firmware/capture-raw',('*.py',)),
        ('firmware/capture-timing',('build_raw10.py','late_build.py')),
        ('firmware/capture-timing/recovery_gpio',('check_park.py',)),
        ('firmware/capture-sd',('build.py',)),
        ('firmware/capture-sd/low_power/readback_recovery',('run.py',)),
    ):
        for pattern in patterns:
            for path in sorted((ROOT/folder).glob(pattern)):
                archive.copy(path,'host-source/'+path.relative_to(ROOT).as_posix())
    for relative in ('tmp/bringup/sd125-negedge-20261026/uart_recover.py',
        'tmp/bringup/sd-early-clock-20261026/fresh_idle.py'):
        archive.copy(ROOT/relative,'host-source/'+relative)

def initial(source,out):
    archive=Archive(source,out)
    archive.put('.gitattributes',b'* -text\n')
    for name in ATTEMPTS:
        folder=source/name
        require((folder/'result.json').is_file() or (folder/'failed.json').is_file(),
            'Attempt is not complete: '+name)
        archive.tree(folder,f'attempts/{name}')
    freeze_builds(archive)
    freeze_reference(archive)
    freeze_scripts(archive)
    for path in sorted(source.iterdir()):
        if path.is_file() and (path.suffix=='.log' or path.name in (
            'analysis-complete01.json','analysis-tests.json','build-results.json',
            'default-binary-identity.json','host-profile-admission.json')):
            archive.copy(path,'reports/'+path.name)
        if path.is_dir() and (path.name=='initial-park' or
            path.name.startswith('before-') and not path.name.startswith('before-probe')):
            archive.tree(path,'recovery/'+path.name)
    # The last verified park explicitly precedes the physical probe change.
    park=source/'before-probe-change-park'
    if park.exists(): archive.tree(park,'status/before-probe-change-park')
    archive.js_prefix('initial')
    archive.put('scope.json',encoded(dict(schema=1,hardware_access=False,
        initial_attempts=list(ATTEMPTS),read_lba=0,read_sector_count=1,
        formal25_attempts=6,photo_capture=False,card_writes=False,card_erases=False,
        nor_programming=False,archive_sealed=False,
        initial_condition='User-reported probe-free wiring; CLK series resistor present near card',
        reference='First512 bytes of earlier verified sensor pattern; fresh12.5MHz PIO verifies equality',
        limitations=['Failed retained buffers remain untrusted; failed cleanup never grants idle permission.',
            'Deletion/CRC-prefix model describes retained data and does not prove physical missing edges.',
            'Partial active JS log is context only, not an energy integration or final ownership claim.',
            'Compiler objects/ELF and full SDK are intentionally omitted; include paths/hashes remain explicit.',
            'Probe-connected controls belong in a separately labeled addendum.'])))
    return archive.save()

def addendum(source,out,label,attempts,evidence):
    require(re.fullmatch(r'[a-z0-9][a-z0-9-]*',label) is not None,'Unsafe addendum label')
    archive=Archive(source,out)
    require(label not in archive.index['addenda'],'Addendum already exists')
    require(attempts or evidence,'No addendum inputs requested')
    for relative in attempts:
        folder=child(source,relative)
        require((folder/'result.json').is_file() or (folder/'failed.json').is_file(),
            'Addendum attempt is not complete: '+relative)
        archive.tree(folder,f'addenda/{label}/attempts/{relative}')
    for relative in evidence:
        path=child(source,relative)
        target=f'addenda/{label}/evidence/{relative}'
        if path.is_dir(): archive.tree(path,target)
        else: archive.copy(path,target)
    archive.index['addenda'].append(label)
    archive.put(f'addenda/{label}/selection.json',encoded(dict(label=label,created_utc=now(),
        attempts=attempts,evidence=evidence,separate_from_initial_conditions=True)))
    return archive.save()

def verify(out):
    index=read(out/'archive-index.json')
    total=0
    for relative,expected in index['files'].items():
        data=child(out,relative).read_bytes()
        require(len(data)==expected['bytes'] and sha(data)==expected['sha256'],
            'Archive bytes differ: '+relative)
        total+=len(data)
    return dict(passed=True,sealed=index['sealed'],files=len(index['files']),bytes=total,
        hardware_access=False,out=str(out))

def seal(out):
    verify(out)
    index=read(out/'archive-index.json')
    index['sealed']=True;index['sealed_utc']=now()
    (out/'archive-index.json').write_bytes(encoded(index))
    entries=[]
    for path in sorted(out.rglob('*')):
        if path.is_file() and path.name!='SHA256SUMS':
            entries.append(f'{sha(path.read_bytes())}  {path.relative_to(out).as_posix()}')
    (out/'SHA256SUMS').write_text('\n'.join(entries)+'\n',encoding='ascii')
    return verify(out)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('freeze','addendum','verify','seal'))
    parser.add_argument('--source',type=Path,default=SOURCE)
    parser.add_argument('--out',type=Path,default=OUT)
    parser.add_argument('--label')
    parser.add_argument('--attempt',action='append',default=[])
    parser.add_argument('--evidence',action='append',default=[])
    args=parser.parse_args()
    if args.action=='freeze': result=initial(args.source,args.out)
    elif args.action=='addendum':
        require(args.label,'Addendum needs explicit condition label')
        result=addendum(args.source,args.out,args.label,args.attempt,args.evidence)
    elif args.action=='verify': result=verify(args.out)
    else: result=seal(args.out)
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
