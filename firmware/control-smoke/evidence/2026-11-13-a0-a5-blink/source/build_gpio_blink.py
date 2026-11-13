"""Offline A0-A5 GPIO-only FLASH diagnostic with the exact existing UART guard.

The normal-only path is redirected before memory, sensor, USB or SD setup.
Only the existing boot prefix and first NOR sector are emitted. This script
never imports an instrument client or changes hardware or recovery admissions.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import re
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'firmware/capture-timing'))
from build_raw10 import TC
sys.path.insert(0, str(ROOT / 'firmware/boot-timing'))
from add_boot_header import make_image, inspect_image

REFERENCE = ROOT / 'firmware/usb-ptp/evidence/2026-11-09-a3-hold/package-pa2'
REFERENCE_PREFIX = '852bc7724a9fc0267fb37e3f93ba52f22137c65c55f2cece47d17dd352093084'
REFERENCE_SECTOR = 'c822d2333ce265ded2ea420fd4c78e2a20e01c4b392b1decb99b80d9a040516d'
REFERENCE_SECTOR1 = '347aa3c1db62cb95bd6b66d421c0d9c3db5a706e493baf2f515ac13cb9f4670f'
BASE = 0x34180400
PATCH = 0x34180B8C
ENTRY = 0x34181840
LIMIT = 0x34181DF0  # First byte of the retained early PA2 HOLD hook.
PREFIX_BYTES = 7160
PARK = 0x3418078C
ORIGINAL_INSTRUCTION = bytes.fromhex('4ff0200e')  # MOV.W lr,#32.


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def branch_target(data, address):
    require(len(data) == 4, 'Redirect must be four bytes')
    hi, lo = struct.unpack('<HH', data)
    require(hi & 0xF800 == 0xF000 and lo & 0xD000 == 0x9000,
            'Redirect must be unconditional Thumb B.W, not BL/BLX')
    sign = (hi >> 10) & 1
    i1 = 1 ^ ((lo >> 13) & 1) ^ sign
    i2 = 1 ^ ((lo >> 11) & 1) ^ sign
    offset = (sign << 24) | (i1 << 23) | (i2 << 22) | ((hi & 1023) << 12) | ((lo & 2047) << 1)
    if sign:
        offset -= 1 << 25
    return address + 4 + offset


def compose(blink, patch):
    original = (REFERENCE / 'stage1.bin').read_bytes()
    sector = (REFERENCE / 'sector0.bin').read_bytes()
    require(sha(original) == REFERENCE_PREFIX and len(original) == PREFIX_BYTES,
            'Pinned original prefix differs')
    require(sha(sector) == REFERENCE_SECTOR and len(sector) == 65536,
            'Pinned original sector differs')
    require(sha((REFERENCE / 'sector1.bin').read_bytes()) == REFERENCE_SECTOR1,
            'Pinned preserved USB sector differs')
    at = PATCH - BASE
    start = ENTRY - BASE
    end = LIMIT - BASE
    require(original[at:at + 4] == ORIGINAL_INSTRUCTION, 'Normal-only instruction differs')
    require(0 < len(blink) <= LIMIT - ENTRY, 'Blink executable exceeds reserved space')
    require(branch_target(patch, PATCH) == ENTRY, 'Redirect target differs')
    prefix = bytearray(original)
    prefix[at:at + 4] = patch
    # Fill the unreachable remainder deterministically without moving HOLD.
    prefix[start:end] = blink + bytes(end - start - len(blink))
    require(prefix[:at] == original[:at], 'Startup, fault handler or UART guard changed')
    require(prefix[at + 4:start] == original[at + 4:start], 'Unexpected middle-prefix change')
    require(prefix[end:] == original[end:], 'Early HOLD hook or final prefix changed')
    require(prefix[PARK - BASE:PARK - BASE + 2] == bytes.fromhex('fee7'), 'Recovery park changed')
    require(struct.unpack_from('<I', prefix, 4)[0] == LIMIT | 1, 'Early HOLD reset vector changed')
    # All 14 original exception vectors and both fault helpers remain intact.
    require(all(x == 0x34180785 for x in struct.unpack_from('<14I', prefix, 8)),
            'Unexpected original exception vectors')
    require(prefix[0x3418075C - BASE:0x3418078C - BASE] ==
            original[0x3418075C - BASE:0x3418078C - BASE], 'Fault park helper changed')
    boot = make_image(bytes(prefix))
    require(len(boot) == 0x2000, 'Boot image geometry changed')
    desired = boot + sector[len(boot):]
    require(desired[0x2000:] == sector[0x2000:], 'Later sector contents changed')
    return bytes(prefix), boot, desired


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, default=HERE / 'gpio_blink.c')
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'gpio_blink.c').write_bytes(args.source.read_bytes())
    (out / 'build_gpio_blink.py').write_bytes(Path(__file__).read_bytes())
    sdk = ROOT / 'tmp/bringup/x-cube-n6-camera-capture/STM32Cube_FW_N6/Drivers/CMSIS'
    flags = ['-mcpu=cortex-m55', '-mthumb', '-mcmse', '-mfloat-abi=soft',
             '-mgeneral-regs-only', '-Os', '-ffreestanding', '-fno-builtin',
             '-fno-stack-protector', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
             '-ffunction-sections', '-fdata-sections', '-Wall', '-Wextra', '-Werror',
             '-nostdlib', '-nostartfiles', '-DSTM32N657xx',
             '-I' + str(sdk / 'Include'), '-I' + str(sdk / 'Device/ST/STM32N6xx/Include')]
    linker = f'''ENTRY(blink_main)
SECTIONS {{
 . = {hex(ENTRY)};
 .text : {{ KEEP(*(.text.entry)) KEEP(*(.text.blink_main)) *(.text*) *(.rodata*) }}
 .data : {{ *(.data*) }}
 .bss (NOLOAD) : {{ *(.bss*) *(COMMON) }}
 /DISCARD/ : {{ *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }}
 ASSERT(blink_main == {hex(ENTRY)}, "Blink entry moved")
 ASSERT(SIZEOF(.data) == 0 && SIZEOF(.bss) == 0, "No initialized/uninitialized globals allowed")
 ASSERT(. <= {hex(LIMIT)}, "Blink code overlaps early HOLD hook")
}}
'''
    (out / 'blink.ld').write_text(linker)
    subprocess.run([str(TC / 'arm-none-eabi-gcc.exe'), *flags,
                    str(out / 'gpio_blink.c'), '-T' + str(out / 'blink.ld'),
                    '-Wl,--build-id=none,--gc-sections', '-o', str(out / 'blink.elf')], check=True)
    subprocess.run([str(TC / 'arm-none-eabi-objcopy.exe'), '-O', 'binary',
                    str(out / 'blink.elf'), str(out / 'blink.bin')], check=True)
    require(not subprocess.check_output([str(TC / 'arm-none-eabi-nm.exe'), '-u', str(out / 'blink.elf')]).strip(),
            'Unresolved blink symbols')
    for name, options in [('blink.lst', ['-d']), ('blink.symbols', ['-t'])]:
        (out / name).write_bytes(subprocess.check_output(
            [str(TC / 'arm-none-eabi-objdump.exe'), *options, str(out / 'blink.elf')]))
    (out / 'patch.S').write_text('.syntax unified\n.thumb\n.section .text.patch,"ax",%progbits\n'
                                '.global blink_redirect\n.thumb_func\nblink_redirect:\n'
                                f' b.w {hex(ENTRY)}\n')
    (out / 'patch.ld').write_text(f'ENTRY(blink_redirect)\nSECTIONS {{ . = {hex(PATCH)}; .text : {{ *(.text*) }} /DISCARD/ : {{ *(.ARM.attributes) *(.comment*) }} }}\n')
    subprocess.run([str(TC / 'arm-none-eabi-gcc.exe'), *flags, str(out / 'patch.S'),
                    '-T' + str(out / 'patch.ld'), '-Wl,--build-id=none', '-o', str(out / 'patch.elf')], check=True)
    subprocess.run([str(TC / 'arm-none-eabi-objcopy.exe'), '-O', 'binary',
                    str(out / 'patch.elf'), str(out / 'patch.bin')], check=True)
    blink = (out / 'blink.bin').read_bytes()
    patch = (out / 'patch.bin').read_bytes()
    prefix, boot, sector = compose(blink, patch)
    (out / 'stage1.bin').write_bytes(prefix)
    (out / 'stage1_boot.bin').write_bytes(boot)
    (out / 'sector0.bin').write_bytes(sector)
    recovery = out / 'recovery'
    recovery.mkdir()
    (recovery / 'stage1.bin').write_bytes(prefix)
    (recovery / 'capture_sector_0.bin').write_bytes(sector)
    rm = copy.deepcopy(json.loads((REFERENCE / 'recovery/manifest.json').read_text()))
    rm.update(hardware_status='unqualified-gpio-only-blink', stage1=inspect_image(boot),
              stage1_raw_bytes=len(prefix), stage1_raw_sha256=sha(prefix),
              program_bytes=len(sector), program_sha256=sha(sector))
    rm['gpio_blink_diagnostic'] = dict(normal_only_patch=hex(PATCH), entry=hex(ENTRY),
                                     camera_usb_sd_unreachable=True, no_standby=True)
    (recovery / 'manifest.json').write_text(json.dumps(rm, indent=2) + '\n')
    manifest = dict(schema=1, kind='a0-a5-gpio-blink-flash', prefix_bytes=len(prefix),
                    prefix_sha256=sha(prefix), sector0_sha256=sha(sector),
                    preserved_sector1_sha256=REFERENCE_SECTOR1,
                    reference_prefix_sha256=REFERENCE_PREFIX, reference_sector0_sha256=REFERENCE_SECTOR,
                    patch_address=PATCH, original_instruction=ORIGINAL_INSTRUCTION.hex(),
                    patch_bytes=patch.hex(), blink_entry=ENTRY, blink_bytes=len(blink),
                    blink_sha256=sha(blink), blink_limit=LIMIT,
                    uart_park=PARK, uart_guard_and_fault_handlers_byte_exact=True,
                    hold_hook_byte_exact=True, later_sector_bytes_preserved_from=0x2000,
                    boot=inspect_image(boot), flags=flags,
                    proof_address=0x34183000, period_ms=500, half_period_cycles=100000000,
                    hardware_status='offline-not-installed', recovery_allowlist_admission=False,
                    sources={n:sha((out / n).read_bytes()) for n in ('gpio_blink.c', 'build_gpio_blink.py', 'blink.ld', 'patch.S', 'patch.ld')})
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
