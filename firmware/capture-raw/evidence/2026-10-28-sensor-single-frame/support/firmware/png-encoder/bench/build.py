"""Build an immutable compute-only Cortex-M55 RAM experiment; no hardware access."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'firmware/capture-timing'))
from build_raw10 import compile_sources, TC, VENDOR

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--source-dir',type=Path,default=HERE.parent)
    p.add_argument('--optimization',choices=('Os','O2'),default='Os')
    a=p.parse_args()
    out=a.out.resolve(); src=a.source_dir.resolve()
    out.relative_to((ROOT/'tmp').resolve())
    out.mkdir(parents=True,exist_ok=False)
    files=[]
    for name in ('bench_main.c','bench_protocol.h','bench_sink.c','bench_sink.h','entry.S','bench.ld'):
        dest=out/name; shutil.copyfile(HERE/name,dest); files.append(dest)
    for name in ('png16.c','png16.h','png16_miniz.c','miniz_config.h'):
        dest=out/name; shutil.copyfile(src/name,dest); files.append(dest)
    for origin in sorted((src/'vendor/miniz').iterdir()):
        if origin.suffix not in ('.c','.h'): continue
        dest=out/'vendor/miniz'/origin.name; dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(origin,dest); files.append(dest)
    cmsis=VENDOR/'STM32Cube_FW_N6/Drivers/CMSIS'
    flags=['-mcpu=cortex-m55','-mthumb','-mcmse','-mfloat-abi=soft','-mgeneral-regs-only',
           '-mno-unaligned-access',f'-{a.optimization}','-g3','-ffunction-sections',
           '-fdata-sections','-fstack-usage','-DSTM32N657xx','-DNDEBUG',
           '-Wall','-Wextra','-Werror',f'-I{out}',f'-I{cmsis/"Include"}',
           f'-I{cmsis/"Device/ST/STM32N6xx/Include"}']
    units=[out/n for n in ('entry.S','bench_main.c','bench_sink.c','png16.c','png16_miniz.c')]
    raw,size=compile_sources(out,units,flags,out/'bench.ld','bench',libc=True)
    symbols={m[2]:int(m[1],16) for m in re.finditer(r'^([0-9a-fA-F]+)\s+\w\s+(\S+)$',
                (out/'symbols.txt').read_text(),re.M)}
    assert symbols['png_bench_prepare']==0x34320000
    for name in ('png_bench_ready_park','png_bench_done_park'):
        offset=symbols[name]-0x34320000
        assert raw[offset:offset+2]==b'\xfe\xe7',name
    assert len(raw)<=0x20000 and symbols['_ebss']<=0x343A0000
    assert not any(re.search(r'(^|_)(sd_|SDMMC|photo_fs|ff_|HAL_|BSP_|malloc|calloc|realloc|sbrk)',s)
                   for s in symbols),'Unexpected storage/allocator symbol'
    undefined=subprocess.check_output([str(TC/'arm-none-eabi-nm.exe'),'-u',str(out/'bench.elf')],text=True)
    assert not undefined.strip(),undefined
    # Scalar-only is deliberate: O2 must not silently reactivate FP context.
    listing=(out/'bench.lst').read_text()
    fp_lines=[line for line in listing.splitlines()
              if re.search(r'^\s*[0-9a-f]+:\s+(?:[0-9a-f]{2,8}\s+)+v[a-z][a-z0-9.]*\s',line)]
    assert not fp_lines,fp_lines[:5]
    m=dict(schema=1,hardware_status='unqualified_offline_build',compute_only=True,
        sd_commands=False,nor_commands=False,sensor_commands=False,reset=False,power_switch=False,
        scalar_only=True,optimization=a.optimization,compile_flags=flags,
        binary_bytes=len(raw),binary_sha256=sha(raw),load_address='0x34320000',
        prepare_entry=hex(symbols['png_bench_prepare']|1),ready_park=hex(symbols['png_bench_ready_park']),
        run_entry=hex(symbols['png_bench_run']|1),done_park=hex(symbols['png_bench_done_park']),
        bss_start=hex(symbols['_sbss']),bss_end=hex(symbols['_ebss']),
        stack_floor='0x343a0000',stack_top='0x343b0000',
        frame_address='0x34000000',frame_bytes=3055360,frame_guard_bytes=32,
        report_address='0x343e0000',report_bytes=512,request_address='0x343e0800',request_bytes=64,
        chunks_address='0x343e1000',chunk_bytes=32,chunk_capacity=100,
        max_output_bytes=3200000,output_interval_bytes=32768,cpu_hz=400000000,
        callback_deadline_cycles=4000000000,
        deadline_scope='Cooperative checks at sink callbacks; not an interrupt watchdog',
        input_guard='Exact host fixture FNV before/after, no claimed camera capture proof',
        output_guard='Expected complete output byte count and FNV supplied in request',
        timing_scope='Instrumented scalar CPU at ROM 400 MHz; sink digest excluded from cpu_cycles; not integrated production timing',
        source_directory=str(src),source_hashes={f.relative_to(out).as_posix():sha(f.read_bytes()) for f in files},size=size)
    (out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:m[k] for k in ('binary_bytes','binary_sha256','prepare_entry','ready_park','run_entry','done_park','bss_end')},indent=2))

if __name__=='__main__':
    main()
