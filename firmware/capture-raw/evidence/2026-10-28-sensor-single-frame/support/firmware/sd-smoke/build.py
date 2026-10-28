"""Build the read-only SDMMC2 RAM smoke helper. No instrument access."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PIN = "e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a"
TOOLS = Path(
    "D:/ST/STM32CubeIDE_1.15.1/STM32CubeIDE/plugins/"
    "com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32."
    "12.3.rel1.win32_1.0.200.202406191623/tools/bin"
)


def run(args):
    completed = subprocess.run([str(a) for a in args], text=True, capture_output=True)
    if completed.returncode:
        raise RuntimeError(completed.stdout + completed.stderr)
    return completed.stdout


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-hz", type=int, choices=(100000, 12500000, 25000000),
                        default=100000)
    parser.add_argument("--toolchain", type=Path, default=TOOLS)
    parser.add_argument("--vendor", type=Path,
                        default=REPO / "tmp/bringup/x-cube-n6-camera-capture")
    args = parser.parse_args()
    cmsis_rel = "STM32Cube_FW_N6/Drivers/CMSIS"
    if run(["git", "-C", args.vendor, "rev-parse", "HEAD"]).strip() != PIN:
        parser.error("Unexpected vendor revision")
    if run(["git", "-C", args.vendor, "status", "--porcelain", "--", cmsis_rel]).strip():
        parser.error("Expected an unmodified pinned CMSIS tree")
    cmsis = args.vendor / cmsis_rel
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    elf, binary = out / "sd-smoke.elf", out / "sd-smoke.bin"
    flags = [
        "-mcpu=cortex-m55", "-mthumb", "-mcmse", "-mfloat-abi=soft", "-Os",
        "-ffreestanding", "-fno-builtin", "-fno-stack-protector",
        "-fno-unwind-tables", "-fno-asynchronous-unwind-tables", "-fstack-usage",
        "-Wall", "-Wextra", "-Werror", "-nostdlib", "-nostartfiles",
        "-DSTM32N657xx",
    ]
    command = [
        args.toolchain / "arm-none-eabi-gcc.exe", *flags,
        "-I", cmsis / "Include", "-I", cmsis / "Device/ST/STM32N6xx/Include",
        "-T", HERE / "smoke.ld", HERE / "entry.S", HERE / "smoke.c",
        "-Wl,--build-id=none", f"-Wl,-Map={out / 'sd-smoke.map'}", "-o", elf,
    ]
    run(command)
    run([args.toolchain / "arm-none-eabi-objcopy.exe", "-O", "binary", elf, binary])
    listing = run([args.toolchain / "arm-none-eabi-objdump.exe", "-d", elf])
    symbols = run([args.toolchain / "arm-none-eabi-nm.exe", "--numeric-sort", elf])
    (out / "sd-smoke.lst").write_text(listing)
    (out / "sd-smoke.symbols.txt").write_text(symbols)
    assert not run([args.toolchain / "arm-none-eabi-nm.exe", "-u", elf]).strip()
    assert "341e0000 T SD_Read_Smoke" in symbols
    assert len(binary.read_bytes()) < 65536 and "bkpt" not in listing
    park = next(line.split()[0] for line in symbols.splitlines()
                if line.endswith(" T sd_smoke_park"))
    park_offset = int(park, 16) - 0x341E0000
    assert binary.read_bytes()[park_offset:park_offset+2] == bytes.fromhex("fee7")
    source = (HERE / "smoke.c").read_text()
    fields = re.search(r"enum \{ (MAGIC,.*?)STATUS_WORDS \};", source, re.S).group(1)
    fields = [f.strip().lower() for f in fields.split(",") if f.strip()]
    assert len(fields) * 4 < 0x300
    (out / "request.bin").write_bytes(struct.pack("<4I", 0x53445244, args.max_hz, 0, 0))
    manifest = {
        "vendor_commit": PIN,
        "source_sha256": {name: sha(HERE / name) for name in
                          ("entry.S", "smoke.c", "smoke.ld", "build.py")},
        "binary_sha256": sha(binary), "binary_bytes": binary.stat().st_size,
        "load": "0x341E0000", "thumb_entry": "0x341E0001",
        "park": "0x" + park, "park_bytes": "fee7",
        "stack_top": "0x341B8000", "request": "0x341B4000",
        "request_words": ["magic=0x53445244", "max_hz", "reserved=0", "reserved=0"],
        "max_hz": args.max_hz,
        "status": "0x341B4100", "status_words": len(fields),
        "status_fields": fields, "records": "0x341B4400",
        "record_count": 64, "record_words": 12,
        "record_fields": ["stage", "command", "argument", "sta", "respcmd", "resp1",
                          "resp2", "resp3", "resp4", "cycles", "gpioc_idr", "gpioe_idr"],
        "sector_buffers": "0x341C0000", "sector_buffer_count": 6, "sector_bytes": 512,
        "buffer_order": ["100k_lba0", "100k_lba1", "12m5_lba0", "12m5_lba1",
                         "25m_lba0", "25m_lba1"],
        "command_whitelist": [0, 2, 3, 7, 8, 9, 13, 16, 17, 41, 55],
        "writes_card": False, "writes_nor": False, "executes_from_ram": True,
        "hardware_access": False,
        "required_preflight": "Verified awake uncached early recovery park; idle storage",
        "nominal_cpu_hz": 400000000, "nominal_hclk_hz": 150000000,
        "instruction": [str(a) for a in command],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({key: manifest[key] for key in
                      ("load", "thumb_entry", "park", "binary_bytes",
                       "binary_sha256", "status_words", "max_hz")}, indent=2))


if __name__ == "__main__":
    main()
