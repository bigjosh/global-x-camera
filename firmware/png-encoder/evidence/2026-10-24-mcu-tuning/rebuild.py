"""Rebuild archived RAM benchmark binaries offline, without importing bench tools."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import replay

HERE=Path(__file__).resolve().parent

def rebuild(trial,out,toolchain=None):
    replay.trial(trial)
    archive=replay.read(trial/'archive.json'); manifest=replay.read(trial/'build/manifest.json')
    tc=Path(toolchain or archive['toolchain']['original_path'])
    for name,item in archive['toolchain']['files'].items():
        raw=(tc/name).read_bytes()
        assert len(raw)==item['bytes'] and replay.sha(raw)==item['sha256'],name
    gcc=tc/'bin/arm-none-eabi-gcc.exe'
    assert subprocess.check_output([str(gcc),'--version'],text=True)==archive['toolchain']['version']
    out.mkdir(parents=True,exist_ok=False)
    src=out/'source';shutil.copytree(trial/'build',src)
    shared=(trial/archive['shared_dependencies']['relative_archive']).resolve()
    cmsis=shared/'dependencies/st/STM32Cube_FW_N6/Drivers/CMSIS'
    def flags(old):
        return [f for f in old if not f.startswith('-I')]+[
            '-I'+str(src),'-I'+str(cmsis/'Include'),'-I'+str(cmsis/'Device/ST/STM32N6xx/Include')]
    common=flags(manifest['compile_flags'])
    units=['entry.S','bench_main.c','bench_sink.c','png16.c','png16_miniz.c']
    if manifest.get('mve_conversion'):units.append('row_convert.c')
    objects=[]
    for i,name in enumerate(units):
        obj=out/f'{i:02d}_{Path(name).stem}.o'
        chosen=flags(manifest.get('unit_flags',{}).get(name,manifest['compile_flags']))
        subprocess.run([str(gcc),*chosen,'-c',str(src/name),'-o',str(obj)],check=True)
        objects.append(str(obj))
    elf=out/'bench.elf'; binary=out/'bench.bin'
    subprocess.run([str(gcc),*common,'-nostartfiles','--specs=nano.specs','--specs=nosys.specs',
        '-T',str(src/'bench.ld'),*objects,'-Wl,--gc-sections,--build-id=none,--no-warn-rwx-segments',
        '-Wl,-Map='+str(out/'bench.map'),'-lc','-lm','-lnosys','-o',str(elf)],check=True)
    subprocess.run([str(tc/'bin/arm-none-eabi-objcopy.exe'),'-O','binary',str(elf),str(binary)],check=True)
    raw=binary.read_bytes();assert raw==(trial/'build/bench.bin').read_bytes()
    return dict(trial=archive['name'],binary_bytes=len(raw),binary_sha256=replay.sha(raw),
                byte_identical=True,hardware_access=False,toolchain_verified=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--trial',action='append')
    p.add_argument('--toolchain',type=Path)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    names=a.trial or sorted(p.parent.name for p in (HERE/'trials').glob('*/archive.json'))
    result=dict(passed=True,builds=[rebuild(HERE/'trials'/name,a.out/name,a.toolchain) for name in names])
    (a.out/'rebuild.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
