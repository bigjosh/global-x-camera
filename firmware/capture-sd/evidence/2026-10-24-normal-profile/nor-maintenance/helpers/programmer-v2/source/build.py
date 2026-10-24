"""Build the bounded RAM NOR helper and INFO command; no hardware access."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import zlib

REPO = Path(__file__).resolve().parents[4]
SOURCE = Path(__file__).resolve().parent
PIN = 'e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a'
TOOLS = Path('D:/ST/STM32CubeIDE_1.15.1/STM32CubeIDE/plugins/'
    'com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.12.3.rel1.win32_'
    '1.0.200.202406191623/tools/bin')


def run(args):
    return subprocess.run([str(a) for a in args], check=True, capture_output=True,
                          text=True).stdout


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def crc_bitwise(data):
    """Same unsigned 32-bit IEEE algorithm as the target, checked against zlib."""
    crc = 0xFFFFFFFF
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ (0xEDB88320 if crc & 1 else 0)
    return (~crc) & 0xFFFFFFFF


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path)
    p.add_argument('--toolchain', type=Path, default=TOOLS)
    p.add_argument('--vendor', type=Path,
                   default=REPO/'tmp/bringup/x-cube-n6-camera-capture')
    a = p.parse_args()
    out = a.out or REPO/'tmp/bringup/rom-nor-programmer-v2-20261024'
    if run(['git', '-C', a.vendor, 'rev-parse', 'HEAD']).strip() != PIN:
        p.error('Unexpected vendor revision')
    cmsis_rel = 'STM32Cube_FW_N6/Drivers/CMSIS'
    if run(['git', '-C', a.vendor, 'status', '--porcelain', '--', cmsis_rel]).strip():
        p.error('CMSIS tree is modified; expected pinned sources')
    cmsis = a.vendor/cmsis_rel
    out.mkdir(parents=True, exist_ok=True)
    elf, binary = out/'programmer.elf', out/'programmer.bin'
    flags = ['-mcpu=cortex-m55', '-mthumb', '-mcmse', '-mfloat-abi=soft', '-Os',
             '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
             '-fno-unwind-tables', '-fno-asynchronous-unwind-tables', '-fstack-usage',
             '-Wall', '-Wextra', '-Werror', '-nostdlib', '-nostartfiles',
             '-DSTM32N657xx']
    command = [a.toolchain/'arm-none-eabi-gcc.exe', *flags,
               '-I', cmsis/'Include', '-I', cmsis/'Device/ST/STM32N6xx/Include',
               '-T', SOURCE/'programmer.ld', SOURCE/'entry.S', SOURCE/'programmer.c',
               '-Wl,--build-id=none', f'-Wl,-Map={out / "programmer.map"}', '-o', elf]
    try:
        run(command)
    except subprocess.CalledProcessError as e:
        raise SystemExit(e.stderr) from e
    run([a.toolchain/'arm-none-eabi-objcopy.exe', '-O', 'binary', elf, binary])
    listing = run([a.toolchain/'arm-none-eabi-objdump.exe', '-d', elf])
    symbols = run([a.toolchain/'arm-none-eabi-nm.exe', '--numeric-sort', elf])
    (out/'programmer.lst').write_text(listing)
    (out/'programmer.symbols.txt').write_text(symbols)
    assert not run([a.toolchain/'arm-none-eabi-nm.exe', '-u', elf]).strip()
    assert len(binary.read_bytes()) <= 0x10000
    assert '341e0000 T ROM_NOR_Programmer' in symbols and 'bkpt' not in listing
    ready = next(line.split()[0] for line in symbols.splitlines()
                 if line.endswith(' T rom_nor_programmer_ready'))
    source = (SOURCE/'programmer.c').read_text()
    status = re.search(r'enum \{ (MAGIC,.*?)STATUS_WORDS \};', source, re.S).group(1)
    status = [s.strip().lower() for s in status.split(',') if s.strip()]
    assert len(status)*4 <= 0x200
    for data in (b'', b'123456789', bytes(range(256)), b'\xff'*65536):
        assert crc_bitwise(data) == zlib.crc32(data)
    manifest = {
        'vendor_commit': PIN, 'cmsis_worktree_clean': True,
        'source_sha256': {n: sha(SOURCE/n) for n in
                           ('entry.S', 'programmer.c', 'programmer.ld', 'completion_poll.h')},
        'binary_sha256': sha(binary), 'binary_bytes': binary.stat().st_size,
        'load': '0x341E0000', 'thumb_entry': '0x341E0001',
        'ready_loop': '0x'+ready, 'stack_top': '0x341B8000', 'stack_limit': 0,
        'command_address': '0x341B4000',
        'command_fields_in_word_order': ['magic=0x4E4F5244', 'sequence',
            'opcode=2(INFO)/3(WRITE)', 'length=0(INFO)/65536(WRITE)', 'flash_offset=0',
            'write_permit=0(INFO)/0x57524954(WRITE)', 'expected_current_crc32',
            'expected_input_crc32'],
        'status': '0x341B4100', 'status_words': len(status),
        'status_fields_in_word_order': status,
        'revision': 2,
        'completion_policy': 'Fresh RDSR after WIP=0; require WIP=0 and WEL=0 within original deadline',
        'completion_diagnostic_address': '0x341B4300',
        'completion_diagnostic_fields_in_word_order': [v.strip().lower() for v in
            re.search(r'enum \{ (DIAG_MAGIC,.*?)DIAG_WORDS \};', source, re.S).group(1).split(',') if v.strip()],
        'input': '0x341C0000', 'readback': '0x341D0000', 'buffer_bytes': 65536,
        'clock_hz': 400000000, 'minimum_cs_high_us': 1,
        'timeout_us': {'small_controller_transfer': 10000, 'large_read': 100000,
                       'page_program_wip': 10000, 'sector_erase_wip': 1000000,
                       'cleanup_status_only_wip': 1000000},
        'per_transfer_poll_backstop': 8000000, 'wip_poll_backstop': 1000000,
        'crc32': 'IEEE reflected 0xEDB88320, init/xorout=0xFFFFFFFF; zlib-compatible',
        'host_crc_equivalence_checks': 'passed',
        'hardware_access': False, 'command': [str(v) for v in command],
    }
    (out/'command-info.bin').write_bytes(struct.pack('<8I', 0x4E4F5244, 1, 2, 0, 0, 0, 0, 0))
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
