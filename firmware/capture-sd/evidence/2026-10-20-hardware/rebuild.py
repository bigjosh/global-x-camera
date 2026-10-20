"""Rebuild archived firmware offline in a new folder; never accesses hardware."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).parent))
from verify import verify


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive",type=Path,default=Path(__file__).parent)
    ap.add_argument("--toolchain",type=Path,required=True,
                    help="Matching toolchain tools directory containing bin/ and lib/")
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--execute",action="store_true",
                    help="Run compiler/objcopy offline; default only validates recipe")
    a=ap.parse_args()
    root=a.archive.resolve()
    verify(root)
    plan=json.loads((root/"archive-plan.json").read_text())
    tc=a.toolchain.resolve()
    for name,expected in plan["toolchain"]["files"].items():
        path=(tc/name).resolve()
        if not path.is_relative_to(tc):
            raise ValueError("External toolchain dependency escapes root")
        if sha(path.read_bytes()) != expected["sha256"]:
            raise ValueError(f"Toolchain mismatch: {name}")
    if a.out.exists():
        raise ValueError("Use a new output directory")
    if not a.execute:
        print(json.dumps(dict(status="Recipe and toolchain validated; no build executed",
                              groups=list(plan["recipe"])),indent=2))
        return
    a.out.mkdir(parents=True)
    built={}
    for name,recipe in plan["recipe"].items():
        out=a.out/name
        out.mkdir()
        flags=[f.replace("${ARCHIVE}",str(root)) for f in recipe["compile_flags"]]
        objects=[]
        for i,source in enumerate(recipe["sources"]):
            obj=out/f"{i:02d}_{Path(source).stem}.o"
            subprocess.run([str(tc/"bin/arm-none-eabi-gcc.exe"),*flags,"-c",
                            str(root/source),"-o",str(obj)],check=True)
            objects.append(str(obj))
        elf=out/(name+".elf")
        subprocess.run([str(tc/"bin/arm-none-eabi-gcc.exe"),*flags,
                        *recipe["runtime_flags"],"-T",str(root/recipe["linker"]),
                        *objects,*recipe["link_flags"],*recipe["libraries"],
                        "-o",str(elf)],check=True)
        binary=out/(name+".bin")
        subprocess.run([str(tc/"bin/arm-none-eabi-objcopy.exe"),"-O","binary",
                        str(elf),str(binary)],check=True)
        built[name]=binary.read_bytes()
        if sha(built[name]) != recipe["binary_sha256"]:
            raise ValueError(f"{name} differs; do not claim byte-identical rebuild")
    wrapper=root/"support/firmware/boot-timing/add_boot_header.py"
    spec=importlib.util.spec_from_file_location("frozen_boot_header",wrapper)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    boot=mod.make_image(built["prefix"])
    if boot != (root/"build/prefix/stage1_boot.bin").read_bytes():
        raise ValueError("ROM header reconstruction differs")
    # Retain verified non-payload padding from the archived sector. It is
    # immutable source data, not regenerated application code.
    sector=bytearray((root/"build/prefix/capture_sector_0.bin").read_bytes())
    for offset,data in ((0,boot),(0x2000,built["receiver"]),(0x6000,built["module"])):
        sector[offset:offset+len(data)]=data
    if sha(sector) != plan["build_identity"]["sector"]:
        raise ValueError("Sector reconstruction differs")
    (a.out/"capture_sector_0.bin").write_bytes(sector)
    result=dict(byte_identical=True,identity=plan["build_identity"],
                hardware_accessed=False)
    (a.out/"rebuild-verification.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
