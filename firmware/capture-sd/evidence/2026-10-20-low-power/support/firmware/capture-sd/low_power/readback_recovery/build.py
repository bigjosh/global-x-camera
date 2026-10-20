"""Offline build of the RAM-only recovery memory bridge."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/"firmware/sd-smoke"))
from build import TOOLS, PIN, run


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--recovery-build",type=Path,required=True)
    a=p.parse_args()
    # Reuse the normal-prefix initializer; the complete source is frozen here.
    source=a.recovery_build/"raw10_memory.c"
    canonical=ROOT/"firmware/capture-timing/raw10_memory.c"
    if source.read_bytes()!=canonical.read_bytes():
        raise ValueError("Initializer differs from the reviewed unchanged source")
    vendor=ROOT/"tmp/bringup/x-cube-n6-camera-capture"
    cmsis=vendor/"STM32Cube_FW_N6/Drivers/CMSIS"
    if run(["git","-C",vendor,"rev-parse","HEAD"]).strip()!=PIN:
        raise ValueError("Unexpected vendor revision")
    if run(["git","-C",vendor,"status","--porcelain","--",
            "STM32Cube_FW_N6/Drivers/CMSIS"]).strip():
        raise ValueError("Modified CMSIS tree")
    out=a.out.resolve(); out.mkdir(parents=True,exist_ok=False)
    for src in (HERE/"boot.c",HERE/"entry.S",HERE/"boot.ld",source):
        shutil.copyfile(src,out/src.name)
    flags=["-mcpu=cortex-m55","-mthumb","-mcmse","-mfloat-abi=soft",
           "-mgeneral-regs-only","-Os","-ffreestanding","-fno-builtin",
           "-fno-stack-protector","-fno-unwind-tables","-fno-asynchronous-unwind-tables",
           "-Wall","-Wextra","-Werror","-nostdlib","-nostartfiles","-DSTM32N657xx"]
    command=[TOOLS/"arm-none-eabi-gcc.exe",*flags,"-I",cmsis/"Include","-I",
        cmsis/"Device/ST/STM32N6xx/Include","-T",out/"boot.ld",out/"entry.S",
        out/"boot.c",out/"raw10_memory.c","-Wl,--build-id=none",
        f"-Wl,-Map={out/'boot.map'}","-o",out/"boot.elf"]
    run(command)
    run([TOOLS/"arm-none-eabi-objcopy.exe","-O","binary",out/"boot.elf",out/"boot.bin"])
    symbols=run([TOOLS/"arm-none-eabi-nm.exe","--numeric-sort",out/"boot.elf"])
    (out/"symbols.txt").write_text(symbols)
    (out/"boot.lst").write_text(run([TOOLS/"arm-none-eabi-objdump.exe","-d",out/"boot.elf"]))
    park=int(re.search(r"^([0-9a-f]+) T readback_boot_park$",symbols,re.M)[1],16)
    code=(out/"boot.bin").read_bytes()
    assert code[park-0x341E0000:park-0x341E0000+2]==b"\xfe\xe7"
    assert not run([TOOLS/"arm-none-eabi-nm.exe","-u",out/"boot.elf"]).strip()
    m=dict(schema=1,load=0x341E0000,entry=0x341E0001,park=park,
        stack_floor=0x341B6000,stack_top=0x341B8000,request=0x341B4000,
        proof=0x341B4100,proof_words=23,binary_bytes=len(code),
        binary_sha256=sha(code),source_hashes={n:sha((out/n).read_bytes())
            for n in ("boot.c","entry.S","boot.ld","raw10_memory.c")},
        vendor_commit=PIN,flags=flags,sd_commands=False,nor_commands=False,
        reset=False,power_switch=False,initialization="expanded SRAM and DWT only")
    (out/"manifest.json").write_text(json.dumps(m,indent=2)+"\n")
    print(json.dumps(m,indent=2))


if __name__=="__main__":
    main()
