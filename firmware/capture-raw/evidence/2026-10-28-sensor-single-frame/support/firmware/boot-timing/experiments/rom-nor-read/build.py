"""Build the RAM-only ROM-configured NOR reader; never accesses hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

REPO = Path(__file__).resolve().parents[4]
SOURCE = Path(__file__).resolve().parent
PIN = 'e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a'
TOOLS = Path('D:/ST/STM32CubeIDE_1.15.1/STM32CubeIDE/plugins/'
    'com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.12.3.rel1.win32_'
    '1.0.200.202406191623/tools/bin')
STATUS = ['magic', 'result', 'requested_bytes', 'read_count', 'polls', 'last_sr',
          'control', 'ipsr', 'cpu_ccr', 'original_msp', 'original_msplim',
          'ahb5enr', 'ahb5rstr', 'mux_cr', 'cr', 'dcr1', 'dcr2', 'initial_sr',
          'ccr', 'tcr', 'ir', 'initial_dlr', 'initial_ar']


def run(args):
    return subprocess.run([str(a) for a in args], check=True, capture_output=True,
                          text=True).stdout


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--length', type=int, choices=[16, 64], default=16)
    p.add_argument('--out', type=Path)
    p.add_argument('--toolchain', type=Path, default=TOOLS)
    p.add_argument('--vendor', type=Path,
                   default=REPO/'tmp/bringup/x-cube-n6-camera-capture')
    a = p.parse_args()
    out = a.out or REPO/f'tmp/bringup/rom-nor-read{a.length}-20261017'
    if run(['git', '-C', a.vendor, 'rev-parse', 'HEAD']).strip() != PIN:
        p.error('Unexpected vendor revision')
    cmsis_rel = 'STM32Cube_FW_N6/Drivers/CMSIS'
    if run(['git', '-C', a.vendor, 'status', '--porcelain', '--', cmsis_rel]).strip():
        p.error('CMSIS tree is modified; expected the pinned sources')
    cmsis = a.vendor/cmsis_rel
    out.mkdir(parents=True, exist_ok=True)
    elf, binary = out/'read.elf', out/'read.bin'
    flags = ['-mcpu=cortex-m55', '-mthumb', '-mcmse', '-mfloat-abi=soft', '-Os',
             '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
             '-fno-unwind-tables', '-fno-asynchronous-unwind-tables', '-fstack-usage',
             '-Wall', '-Wextra', '-Werror', '-nostdlib', '-nostartfiles',
             '-DSTM32N657xx', f'-DNOR_READ_LENGTH={a.length}']
    command = [a.toolchain/'arm-none-eabi-gcc.exe', *flags,
               '-I', cmsis/'Include', '-I', cmsis/'Device/ST/STM32N6xx/Include',
               '-T', SOURCE/'read.ld', SOURCE/'entry.S', SOURCE/'read.c',
               '-Wl,--build-id=none', f'-Wl,-Map={out / "read.map"}', '-o', elf]
    run(command)
    run([a.toolchain/'arm-none-eabi-objcopy.exe', '-O', 'binary', elf, binary])
    listing = run([a.toolchain/'arm-none-eabi-objdump.exe', '-d', elf])
    symbols = run([a.toolchain/'arm-none-eabi-nm.exe', '--numeric-sort', elf])
    (out/'read.lst').write_text(listing)
    (out/'read.symbols.txt').write_text(symbols)
    assert not run([a.toolchain/'arm-none-eabi-nm.exe', '-u', elf]).strip()
    assert len(binary.read_bytes()) <= 0x400
    assert '341a0000 T ROM_NOR_Read' in symbols and 'bkpt' not in listing
    ready = next(line.split()[0] for line in symbols.splitlines()
                 if line.endswith(' T rom_nor_read_ready'))
    manifest = {
        'vendor_commit': PIN, 'cmsis_worktree_clean': True,
        'source_sha256': {n: sha(SOURCE/n) for n in ('entry.S', 'read.c', 'read.ld')},
        'binary_sha256': sha(binary), 'binary_bytes': binary.stat().st_size,
        'requested_bytes': a.length, 'load': '0x341A0000', 'thumb_entry': '0x341A0001',
        'ready_loop': '0x'+ready, 'stack_top': '0x341A1000', 'stack_limit': 0,
        'status': '0x341A0400', 'status_fields_in_word_order': STATUS,
        'data': '0x341A0500', 'nor_offset': 0, 'total_poll_limit': 1000000,
        'peripheral_writes': {'0x58025024': 3, '0x58025040': a.length-1,
                              '0x58025048': 0},
        'expected_first_16_hex': '53544d32000000000000000000000000',
        'hardware_access': False, 'command': [str(v) for v in command],
    }
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
