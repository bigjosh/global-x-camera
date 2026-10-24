"""Rebuild the two diagnostic overlays offline in a new directory; no hardware."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
from verify_v66 import verify,sha

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,default=Path(__file__).parent)
    p.add_argument('--toolchain',type=Path,required=True,help='Matching tools root with bin/ and lib/')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--execute',action='store_true')
    a=p.parse_args();root=a.archive.resolve();verify(root)
    plan=json.loads((root/'archive-v66.json').read_text(encoding='utf-8'))
    shared=(root/plan['shared_dependencies']['relative_archive']).resolve()
    tc=a.toolchain.resolve()
    for name,want in plan['toolchain']['files'].items():
        path=(tc/name).resolve()
        if not path.is_relative_to(tc) or sha(path.read_bytes())!=want['sha256']:
            raise ValueError('Toolchain mismatch: '+name)
    if a.out.exists():raise ValueError('Use a new output directory')
    if not a.execute:
        print('Recipe and toolchain verified; no compilation requested');return
    a.out.mkdir(parents=True)
    built={}
    for name,r in plan['recipes'].items():
        d=a.out/name;d.mkdir(parents=True)
        flags=[f.replace('${ARCHIVE}',str(root)).replace('${SHARED}',str(shared)) for f in r['compile_flags']]
        objects=[]
        for i,source in enumerate(r['sources']):
            obj=d/f'{i:02d}_{Path(source).stem}.o'
            subprocess.run([str(tc/'bin/arm-none-eabi-gcc.exe'),*flags,'-c',str(root/source),'-o',str(obj)],check=True)
            objects.append(str(obj))
        elf=d/'payload.elf'
        subprocess.run([str(tc/'bin/arm-none-eabi-gcc.exe'),*flags,*r['runtime_flags'],
                        '-T',str(root/r['linker']),*objects,*r['link_flags'],*r['libraries'],'-o',str(elf)],check=True)
        binary=d/'payload.bin'
        subprocess.run([str(tc/'bin/arm-none-eabi-objcopy.exe'),'-O','binary',str(elf),str(binary)],check=True)
        raw=binary.read_bytes()
        if sha(raw)!=r['binary_sha256']:raise ValueError('Binary rebuild differs: '+name)
        built[name]=raw
    wrapper=root/'support/firmware/boot-timing/add_boot_header.py'
    spec=importlib.util.spec_from_file_location('frozen_wrapper',wrapper)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    results={}
    for variant,identity in plan['build_identities'].items():
        d=root/'build'/variant
        boot=module.make_image(built[variant+'/staged'])
        if boot!=(d/'staged/stage1_boot.bin').read_bytes():raise ValueError('ROM wrapper differs')
        sector=bytearray((d/'staged/capture_sector_0.bin').read_bytes())
        for offset,group in ((0x2000,'receiver'),(0x6000,'module'),(0xE000,'late')):
            if variant+'/'+group in built:
                raw=built[variant+'/'+group];sector[offset:offset+len(raw)]=raw
        sector[:len(boot)]=boot
        if sha(sector)!=identity['sector_sha256']:raise ValueError('Sector rebuild differs')
        (a.out/variant/'capture_sector_0.bin').write_bytes(sector)
        results[variant]=sha(sector)
    result=dict(byte_identical=True,sectors=results,payload_groups=len(built),hardware_accessed=False)
    (a.out/'rebuild-verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
