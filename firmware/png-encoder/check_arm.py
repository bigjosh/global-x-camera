"""Compile/link an offline Cortex-M55 size/stack probe. Never execute it.

The ELF is a link-size probe without a vector table or board initialization,
not deployable firmware. Its local memory routines avoid pulling in libc.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
DEFAULT_TOOLS = Path(
    "D:/ST/STM32CubeIDE_1.15.1/STM32CubeIDE/plugins/"
    "com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32."
    "12.3.rel1.win32_1.0.200.202406191623/tools/bin")


def run(args):
    result = subprocess.run([str(x) for x in args], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stdout+result.stderr)
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tools", type=Path, default=DEFAULT_TOOLS)
    a = parser.parse_args()
    output = a.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    memory = output / "memory.c"
    memory.write_text(
        "#include <stddef.h>\n"
        "void *memset(void*d,int c,size_t n){volatile unsigned char*p=d;"
        "while(n--)*p++=(unsigned char)c;return d;}\n"
        "void *memcpy(void*d,const void*s,size_t n){volatile unsigned char*p=d;"
        "const volatile unsigned char*q=s;while(n--)*p++=*q++;return d;}\n")
    elf = output / "png16-size-probe.elf"
    command = [
        a.tools/"arm-none-eabi-gcc.exe", "-mcpu=cortex-m55", "-mthumb",
        "-mfloat-abi=soft", "-Os", "-std=c11", "-ffreestanding", "-fno-builtin",
        "-ffunction-sections", "-fdata-sections", "-fstack-usage", "-nostdlib",
        "-Wall", "-Wextra", "-Werror", HERE/"png16.c", HERE/"png16_miniz.c",
        memory, "-Wl,--gc-sections", "-Wl,-e,png16_encode",
        "-Wl,-Ttext=0x34320000", "-o", elf,
    ]
    run(command)
    size = run([a.tools/"arm-none-eabi-size.exe", elf])
    undefined = run([a.tools/"arm-none-eabi-nm.exe", "-u", elf])
    assert not undefined.strip(), undefined
    stack = []
    for path in output.glob("*.su"):
        for line in path.read_text().splitlines():
            source, amount, kind = line.split("\t")
            stack.append(dict(function=source.rsplit(":", 1)[-1],
                              bytes=int(amount), kind=kind))
    stack.sort(key=lambda v: v["bytes"], reverse=True)
    report = dict(
        hardware_access=False, deployable=False, size=size,
        elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),
        largest_function_stack=stack[:12],
        required_integration_stack="Reserve >=16KiB; measure stack high-water including the output callback",
        command=[str(x) for x in command])
    (output/"report.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
