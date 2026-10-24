"""Verify the frozen phase-build/probe inventory offline, allowing later addenda."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib

def sha(raw): return hashlib.sha256(raw).hexdigest()
def require(ok,message):
    if not ok: raise ValueError(message)

def verify(root):
    root=root.resolve()
    plan=json.loads((root/'archive-build.json').read_text(encoding='utf-8'))
    require(plan['schema']==1,'Unexpected archive schema')
    origins={}
    for e in plan['source_index']:
        p=(root/e['archived_path']).resolve()
        require(p.is_relative_to(root),'Inventory path escapes archive')
        raw=p.read_bytes()
        require(len(raw)==e['bytes'] and sha(raw)==e['sha256'],'Inventory mismatch: '+str(p))
        if 'original_path' in e:origins.setdefault(e['original_path'].replace('\\','/'),[]).append(e)
    shared=(root/plan['shared_dependencies']['relative_archive']).resolve()
    require(shared.parent==root.parent and shared.name=='2026-10-20-low-power','Unexpected shared dependency root')
    require(sha((shared/'archive-plan.json').read_bytes())==plan['shared_dependencies']['original_plan_sha256'],'Shared archive identity changed')
    for e in plan['shared_dependencies']['files']:
        p=(shared/e['path']).resolve();require(p.is_relative_to(shared),'Shared path escape')
        raw=p.read_bytes();require(len(raw)==e['bytes'] and sha(raw)==e['sha256'],'Shared dependency changed: '+str(p))
    for name,recipe in plan['recipes'].items():
        for flag in recipe['compile_flags']:
            require(not re.search(r'[A-Za-z]:[\\/]|tmp[\\/]',flag),'Nonportable flag: '+flag)
        raw=(root/recipe['binary']).read_bytes()
        require(sha(raw)==recipe['binary_sha256'],'Payload mismatch: '+name)
        manifest=json.loads((root/recipe['binary']).with_name('manifest.json').read_text(encoding='utf-8'))
        for source,want in manifest['sources'].items():
            require(any(x['sha256']==want for x in origins.get(source.replace('\\','/'),[])),
                    'Frozen source not preserved: '+source)
        for source in recipe['sources']:
            require((root/source).is_file(),'Missing translation unit: '+source)
    for variant,identity in plan['build_identities'].items():
        d=root/'build'/variant
        sector=(d/'staged/capture_sector_0.bin').read_bytes()
        require(len(sector)==65536 and sha(sector)==identity['sector_sha256'],'Sector mismatch')
        payloads={g:(root/r['binary']).read_bytes() for n,r in plan['recipes'].items()
                  for v,g in [n.split('/')] if v==variant}
        require(sha(payloads['staged'])==identity['prefix_sha256'],'Prefix identity mismatch')
        base=shared/'build/prefix/stage1.bin'
        prior=base.read_bytes();prefix=payloads['staged']
        require(prefix[:0xAFE]==prior[:0xAFE],'Recovery prefix bytes changed')
        for offset in identity['recovery_literals_verified']:
            require(prefix[offset:offset+4]==prior[offset:offset+4],'Recovery literal changed')
        require(prefix[0x38C:0x38E]==bytes.fromhex('fee7'),'Recovery park changed')
        boot=(d/'staged/stage1_boot.bin').read_bytes()
        for offset,raw in ((0,boot),(0x2000,payloads['receiver']),(0x6000,payloads['module'])):
            require(sector[offset:offset+len(raw)]==raw,'Sector payload mismatch')
        if 'late' in payloads:require(sector[0xE000:0xE000+len(payloads['late'])]==payloads['late'],'Late payload mismatch')
        require(len(payloads['receiver'])<=0x4000 and len(payloads['module'])<=0x8000,'Flash payload overlap')
        require(payloads['receiver'][-4:]==struct.pack('<I',64000000),'Clock initializer changed')
        md=json.loads((d/'module/manifest.json').read_text(encoding='utf-8'))
        require(int(md['load_address'],0)==0x34320000 and int(md['bss_end'],0)<=0x343A0000,'Storage layout changed')
        require(md['binary_sha256']==identity['module_sha256'],'Module identity mismatch')
    return dict(verified=True,status=plan['status'],payload_groups=len(plan['recipes']),
                inventory_files=len(plan['source_index']),hardware_accessed=False)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,default=Path(__file__).parent)
    print(json.dumps(verify(parser.parse_args().archive),indent=2))
