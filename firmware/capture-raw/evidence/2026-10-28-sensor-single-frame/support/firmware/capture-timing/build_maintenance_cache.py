"""Relocate the reviewed stackless cache helper away from staged capture code."""
import hashlib
import argparse
import json
from pathlib import Path
import subprocess
from build import REPO, TC, VENDOR

SOURCE = REPO / 'firmware/boot-timing/experiments/cache-prep'
OUT = REPO / 'tmp/bringup/capture-maintenance-cache-20261017'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw10', action='store_true')
    args = parser.parse_args()
    OUT = REPO / ('tmp/bringup/capture-maintenance-cache-raw10-20261017' if args.raw10
                  else 'tmp/bringup/capture-maintenance-cache-20261017')
    load = 0x343C0000 if args.raw10 else 0x341A0000
    status = load + 0x400
    OUT.mkdir(parents=True, exist_ok=False)
    for name in ('cache_prep.c', 'cache_prep.S', 'cache_prep.ld'):
        text = (SOURCE / name).read_text()
        text = text.replace('0x34190000', f'0x{load:08X}').replace('0x34190400', f'0x{status:08X}')
        (OUT / name).write_text(text, encoding='utf-8', newline='\n')
    cmsis = VENDOR / 'STM32Cube_FW_N6/Drivers/CMSIS'
    cmd = [str(TC / 'arm-none-eabi-gcc.exe'), '-mcpu=cortex-m55', '-mthumb', '-mcmse',
           '-mfloat-abi=soft', '-mgeneral-regs-only', '-Os', '-ffreestanding', '-fno-builtin',
           '-fno-unwind-tables', '-fno-asynchronous-unwind-tables', '-nostdlib', '-nostartfiles',
           '-DSTM32N657xx', '-I', str(cmsis / 'Include'), '-I', str(cmsis / 'Device/ST/STM32N6xx/Include'),
           '-T', str(OUT / 'cache_prep.ld'), str(OUT / 'cache_prep.S'), str(OUT / 'cache_prep.c'),
           '-Wl,--build-id=none', '-o', str(OUT / 'cache_prep.elf')]
    subprocess.run(cmd, check=True)
    subprocess.run([str(TC / 'arm-none-eabi-objcopy.exe'), '-O', 'binary',
                    str(OUT / 'cache_prep.elf'), str(OUT / 'cache_prep.bin')], check=True)
    listing = subprocess.check_output([str(TC / 'arm-none-eabi-objdump.exe'), '-d',
                                       str(OUT / 'cache_prep.elf')], text=True)
    (OUT / 'cache_prep.lst').write_text(listing)
    assert 'bkpt' not in listing and '<Cache_Prep>' in listing and '<cache_prep_ready>' in listing
    data = (OUT / 'cache_prep.bin').read_bytes()
    assert len(data) == 148
    manifest = dict(load=hex(load), entry=hex(load+1), status=hex(status),
                    sha256=hashlib.sha256(data).hexdigest(), bytes=len(data), command=cmd)
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
