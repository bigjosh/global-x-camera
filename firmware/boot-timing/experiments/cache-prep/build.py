"""Build and inspect the RAM-only cache-preparation diagnostic; no device access.

Uses the same pinned vendor checkout as the first-GPIO experiments. The output
contains no STM32 boot header and must never be programmed as a flash image.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

REPO = Path(__file__).resolve().parents[4]
SOURCE = Path(__file__).resolve().parent
PIN = "e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a"
DEFAULT_TOOLS = Path("D:/ST/STM32CubeIDE_1.15.1/STM32CubeIDE/plugins/"
    "com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.12.3.rel1.win32_"
    "1.0.200.202406191623/tools/bin")


def run(args):
    return subprocess.run([str(arg) for arg in args], check=True,
                          capture_output=True, text=True).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path, default=DEFAULT_TOOLS)
    parser.add_argument("--vendor", type=Path,
                        default=REPO / "tmp/bringup/x-cube-n6-camera-capture")
    parser.add_argument("--out", type=Path,
                        default=REPO / "tmp/bringup/cache-prep-20261017")
    args = parser.parse_args()
    revision = run(["git", "-C", args.vendor, "rev-parse", "HEAD"]).strip()
    if revision != PIN:
        raise SystemExit(f"Expected vendor {PIN}; found {revision}")
    cmsis = args.vendor / "STM32Cube_FW_N6/Drivers/CMSIS"
    args.out.mkdir(parents=True, exist_ok=True)
    elf = args.out / "cache_prep.elf"
    binary = args.out / "cache_prep.bin"
    command = [args.toolchain / "arm-none-eabi-gcc.exe", "-mcpu=cortex-m55",
               "-mthumb", "-mcmse", "-mfloat-abi=soft", "-Os", "-ffreestanding",
               "-fno-builtin", "-fno-unwind-tables", "-fno-asynchronous-unwind-tables",
               "-nostdlib", "-nostartfiles", "-DSTM32N657xx",
               "-I", cmsis / "Include", "-I", cmsis / "Device/ST/STM32N6xx/Include",
               "-T", SOURCE / "cache_prep.ld", SOURCE / "cache_prep.S",
               SOURCE / "cache_prep.c", "-Wl,--build-id=none",
               f"-Wl,-Map={args.out / 'cache_prep.map'}", "-o", elf]
    run(command)
    run([args.toolchain / "arm-none-eabi-objcopy.exe", "-O", "binary", elf, binary])
    listing = run([args.toolchain / "arm-none-eabi-objdump.exe", "-d", elf])
    symbols = run([args.toolchain / "arm-none-eabi-nm.exe", "--numeric-sort", elf])
    (args.out / "cache_prep.lst").write_text(listing)
    (args.out / "cache_prep.symbols.txt").write_text(symbols)
    data = binary.read_bytes()
    assert len(data) <= 0x400, "Code would overlap the status record"
    assert "34190000 T Cache_Prep" in symbols
    assert "cache_prep_ready" in symbols and "MSPLIM" in listing
    assert "bkpt" not in listing, "Final loop must survive debugger disconnect"
    # No runtime initialization or unresolved library call is permitted.
    unresolved = run([args.toolchain / "arm-none-eabi-nm.exe", "-u", elf]).strip()
    assert not unresolved, unresolved
    record = {
        "revision": 2,
        "vendor_commit": revision,
        "cmsis_function": "SCB_DisableICache",
        "cmsis_header": "STM32Cube_FW_N6/Drivers/CMSIS/Include/m-profile/armv7m_cachel1.h",
        "load_address": "0x34190000", "thumb_entry": "0x34190001",
        "status_address": "0x34190400", "status_words": 5,
        "completion": "awake loop at cache_prep_ready; debugger must halt it",
        "start_command": "-coreReg PC=0x34190001 XPSR=0x01000000 -run",
        "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        "command": [str(arg) for arg in command],
        "hardware_access": False,
    }
    (args.out / "build.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
