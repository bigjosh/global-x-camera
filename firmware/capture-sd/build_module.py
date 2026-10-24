"""Build the high-SRAM PNG/FAT32 module offline; never access hardware."""
import argparse
import json
from pathlib import Path
import re
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE.parent/"capture-timing"))
from build_raw10 import compile_sources,sha,VENDOR

def resolved_path(path):
    """Keep Windows extended-length aliases consistent in source identities."""
    value=str(Path(path).resolve())
    if value.startswith("\\\\?\\UNC\\"):
        value="\\\\"+value[8:]
    elif value.startswith("\\\\?\\"):
        value=value[4:]
    return Path(value)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--default-mode",type=int,choices=(0,1,2),default=1)
    p.add_argument("--diagnostics-profile",choices=("normal","diagnostic"),default="normal",
                   help="Normal omits full-frame hashes/statistics and stack watermark")
    p.add_argument("--data-cache",action="store_true",
                   help="Experimental CPU D-cache; requires inherited MPU disabled")
    p.add_argument("--optimization",choices=("Os","O2","O3"),default="Os",
                   help="Explicit compiler optimization; default preserves -Os")
    p.add_argument("--led-header",type=Path,default=ROOT/"tmp/bringup/capture-vcp-recovery-v45b-20261020/receiver/status_leds.h")
    a=p.parse_args()
    out=resolved_path(a.out); out.mkdir(parents=True,exist_ok=False)
    origins=[HERE/n for n in ("save_main.c","save_entry.S","save_protocol.h","capture_profile.h","save.ld",
                             "photo_fs.c","photo_fs.h")]
    origins+=[HERE/"fs"/n for n in ("ff.c","ff.h","ffconf.h","diskio.h","sd_diskio.c","sd_diskio.h")]
    origins+=[HERE.parent/"sd-storage"/n for n in ("sd_card.c","sd_card.h")]
    origins+=[HERE.parent/"png-encoder"/n for n in ("png16.c","png16.h","png16_miniz.c",
        "miniz_config.h")]
    origins+=list((HERE.parent/"png-encoder/vendor/miniz").glob("*.h"))
    origins+=list((HERE.parent/"png-encoder/vendor/miniz").glob("*.c"))
    origins+=[a.led_header.resolve()]
    sources=[]
    for src in origins:
        # Preserve relative include paths, including vendor/miniz and fs/.
        if src.is_relative_to(HERE): relative=src.relative_to(HERE)
        elif src.is_relative_to(HERE.parent/"png-encoder"): relative=src.relative_to(HERE.parent/"png-encoder")
        else: relative=Path(src.name)
        dst=out/relative
        dst.parent.mkdir(parents=True,exist_ok=True)
        dst.write_bytes(src.read_bytes()); sources.append(dst)
    drivers=VENDOR/"STM32Cube_FW_N6/Drivers"
    flags=["-mcpu=cortex-m55","-mthumb","-mcmse","-mfpu=fpv5-d16","-mfloat-abi=hard",
           f"-{a.optimization}","-g3","-ffunction-sections","-fdata-sections","-fstack-usage",
           "-DSTM32N657xx","-DNDEBUG",f"-DSAVE_DATA_CACHE={int(a.data_cache)}",
           f"-DCAPTURE_DIAGNOSTICS={int(a.diagnostics_profile=='diagnostic')}",
           "-Wall","-Wextra","-Werror",
           f"-I{out}",f"-I{out/'fs'}",f"-I{drivers/'CMSIS/Include'}",
           f"-I{drivers/'CMSIS/Device/ST/STM32N6xx/Include'}"]
    # The fast compressor uses bytewise LE reads. Preserve this code-generation
    # constraint so no caller UNALIGN_TRP setting can change their safety.
    flags.append("-mno-unaligned-access")
    units=[s for s in sources if s.suffix in (".c",".S") and "vendor" not in s.parts]
    raw,size=compile_sources(out,units,flags,out/"save.ld","save",libc=True)
    symbols={}
    for line in (out/"symbols.txt").read_text().splitlines():
        m=re.match(r"^([0-9a-f]+)\s+\w\s+(\S+)$",line)
        if m: symbols[m[2]]=int(m[1],16)
    assert symbols["save_entry"]==0x34320000 and len(raw)%4==0
    assert len(raw)<=40960 and symbols["_ebss"]<=0x343A0000
    assert not any(s in symbols for s in ("malloc","calloc","realloc","_sbrk"))
    manifest=dict(schema=1,hardware_status="untested",default_mode=a.default_mode,
        report_schema=2,diagnostics_profile=a.diagnostics_profile,
        expensive_checks=a.diagnostics_profile=="diagnostic",fine_timing_extension=1,
        data_cache_enabled=a.data_cache,cache_report_extension=1,
        optimization=a.optimization,
        binary_bytes=len(raw),binary_sha256=sha(raw),load_address="0x34320000",
        entry_address=hex(symbols["save_entry"]|1),
        bench_entry_address=hex(symbols["save_bench_entry"]|1),
        park_address=hex(symbols["save_park"]),
        bss_start=hex(symbols["_sbss"]),bss_end=hex(symbols["_ebss"]),
        stack_floor="0x343a0000",stack_top="0x343b0000",
        request_address="0x343f9f00",report_address="0x343fa000",
        buffer_address=hex(symbols["output_buffer"]),buffer_bytes=32768,
        read_buffer_address=hex(symbols["scratch"]),read_buffer_bytes=262144,
        compile_flags=flags,size=size,
        sources={str(s.relative_to(ROOT)):sha(s.read_bytes()) for s in sources})
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print(json.dumps(manifest,indent=2))

if __name__=="__main__": main()
