"""Offline build of a tiny sensor-reset/NOR-read prefix plus checked stage2.

This tool writes local build artifacts only. It does not connect to the board.
The resulting first-sector image must use the separately guarded NOR workflow.
"""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import zlib

from build import HERE, REPO, TC, VENDOR, sha

sys.path.insert(0, str(REPO / 'firmware/boot-timing'))
from add_boot_header import make_image, inspect_image

FLASH_OFFSET = 0x2000
LOAD_ADDRESS = 0x34190000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage2', type=Path, required=True, help='Completed build.py --stage2 directory')
    parser.add_argument('--snapshot', type=Path, required=True, help='Exact preserved 64-KiB NOR sector')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stage1-source-dir', type=Path, default=HERE, help='Optional frozen prefix sources for matched experiments')
    parser.add_argument('--skip-sensor-reset', action='store_true', help='Experimental cold boot: preserve sensor startup that occurred during ROM')
    parser.add_argument('--word-reads', action='store_true', help='Read verified XSPI FIFO words where at least four bytes are available')
    parser.add_argument('--xspi64', action='store_true', help='Experimental 64MHz read with prescaler restored before handoff')
    parser.add_argument('--early-sensor', action='store_true', help='Configure/start fixed sensor profile before reading receiver stage2')
    parser.add_argument('--inline-crc', action='store_true', help='Inline the unchanged software CRC byte operation')
    parser.add_argument('--trim-sensor', action='store_true', help='Combine contiguous transfers and defer nonessential diagnostic reads')
    parser.add_argument('--disable-darkcal', action='store_true', help='Diagnostic only: disable sensor dark calibration and verify register before START')
    parser.add_argument('--dphy-noncontinuous', action='store_true', help='Diagnostic only: disable continuous sensor MIPI clock and verify before START')
    parser.add_argument('--sensor-csi-mbps', type=int, choices=[804,1000,1200], default=804)
    parser.add_argument('--sensor-source', type=Path, default=HERE/'stage1_sensor.c', help='Optional frozen early-sensor source')
    parser.add_argument('--prefix-opt', choices=['Os','O2'], default='Os')
    args = parser.parse_args()
    stage2_dir = args.stage2.resolve()
    stage2 = (stage2_dir / 'capture.bin').read_bytes()
    stage2_manifest = json.loads((stage2_dir / 'manifest.json').read_text())
    assert stage2_manifest['parameters']['stage2'] is True
    assert stage2_manifest['raw_sha256'] == sha(stage2)
    assert stage2_manifest['parameters']['rom_clocks'] is True
    assert stage2_manifest['parameters']['minimal_system_init'] is True
    assert 8 <= len(stage2) <= 65536 - FLASH_OFFSET
    stack, entry = struct.unpack_from('<II', stage2)
    assert not stack & 7 and LOAD_ADDRESS + len(stage2) < stack <= 0x341E0000
    assert entry & 1 and LOAD_ADDRESS <= (entry & ~1) < LOAD_ADDRESS + len(stage2)
    assert int(stage2_manifest['vector_address'], 0) == LOAD_ADDRESS
    saved = args.snapshot.read_bytes()
    assert len(saved) == 65536
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    crc = zlib.crc32(stage2) & 0xFFFFFFFF
    fw = VENDOR / 'STM32Cube_FW_N6/Drivers'
    includes = [fw / 'CMSIS/Include', fw / 'CMSIS/Device/ST/STM32N6xx/Include']
    sources = []
    for name in ['stage1.c', 'stage1.S', 'stage1.ld']:
        target = out / name
        target.write_bytes((args.stage1_source_dir / name).read_bytes())
        sources.append(target)
    assert not args.skip_sensor_reset or 'STAGE1_SKIP_SENSOR_RESET' in (out / 'stage1.c').read_text()
    assert not args.word_reads or 'STAGE1_WORD_READS' in (out / 'stage1.c').read_text()
    assert not args.xspi64 or (args.word_reads and 'STAGE1_XSPI_64MHZ' in (out / 'stage1.c').read_text())
    assert not args.early_sensor or (args.word_reads and args.skip_sensor_reset and stage2_manifest['parameters'].get('receiver_only'))
    assert not args.inline_crc or 'STAGE1_INLINE_CRC' in (out / 'stage1.c').read_text()
    assert not args.trim_sensor or (args.early_sensor and stage2_manifest['parameters'].get('sensor_late_diagnostics'))
    assert not args.disable_darkcal or args.early_sensor
    assert not args.dphy_noncontinuous or (args.early_sensor and args.sensor_csi_mbps==804 and not args.disable_darkcal)
    if args.sensor_csi_mbps!=804:
        assert args.early_sensor and not args.disable_darkcal
        assert stage2_manifest['parameters'].get('csi_phy_bitrate',800)==args.sensor_csi_mbps
    if args.early_sensor:
        source=out/'stage1_sensor.c'
        source.write_bytes(args.sensor_source.read_bytes())
        assert not args.disable_darkcal or 'STAGE1_DISABLE_DARKCAL' in source.read_text()
        assert not args.dphy_noncontinuous or 'STAGE1_DPHY_NONCONTINUOUS' in source.read_text()
        assert args.sensor_csi_mbps==804 or 'STAGE1_CSI_MBPS' in source.read_text()
        sources.append(source)
    gcc = str(TC / 'arm-none-eabi-gcc.exe')
    flags = ['-mcpu=cortex-m55', '-mthumb', '-mcmse', '-mfloat-abi=soft', '-mgeneral-regs-only', '-'+args.prefix_opt, '-g3',
             '-ffunction-sections', '-fdata-sections', '-fno-builtin', '-fno-unwind-tables',
             '-fno-asynchronous-unwind-tables', '-flto', '-Wall', '-Wextra', '-DSTM32N657xx',
             f'-DSTAGE2_FLASH_OFFSET={FLASH_OFFSET}U',
             f'-DSTAGE2_BYTES={len(stage2)}U', f'-DSTAGE2_EXPECTED_CRC32=0x{crc:08X}U']
    flags.append(f'-DSTAGE1_SKIP_SENSOR_RESET={int(args.skip_sensor_reset)}')
    flags.extend([f'-DSTAGE1_WORD_READS={int(args.word_reads)}',f'-DSTAGE1_XSPI_64MHZ={int(args.xspi64)}',f'-DSTAGE1_EARLY_SENSOR={int(args.early_sensor)}'])
    flags.append(f'-DSTAGE1_INLINE_CRC={int(args.inline_crc)}')
    flags.append(f'-DSTAGE1_SENSOR_TRIM={int(args.trim_sensor)}')
    flags.append(f'-DSTAGE1_DISABLE_DARKCAL={int(args.disable_darkcal)}')
    flags.extend([f'-DSTAGE1_DPHY_NONCONTINUOUS={int(args.dphy_noncontinuous)}',f'-DSTAGE1_CSI_MBPS={args.sensor_csi_mbps}'])
    flags += [f'-I{x}' for x in includes]
    objects = []
    for source in [s for s in sources if s.suffix!='.ld']:
        obj = out / (source.name + '.o')
        subprocess.run([gcc, *flags, '-c', str(source), '-o', str(obj)], check=True)
        objects.append(obj)
    elf = out / 'stage1.elf'
    subprocess.run([gcc, *flags, '-nostdlib', '-T', str(out / 'stage1.ld'),
                    *map(str, objects), '-Wl,--gc-sections,--build-id=none,--no-warn-rwx-segments',
                    f'-Wl,-Map={out / "stage1.map"}', '-o', str(elf)], check=True)
    raw_path = out / 'stage1.bin'
    subprocess.run([str(TC / 'arm-none-eabi-objcopy.exe'), '-O', 'binary', str(elf), str(raw_path)], check=True)
    raw = raw_path.read_bytes()
    boot = make_image(raw)
    assert len(boot) <= FLASH_OFFSET, 'Stage1 boot image overlaps stage2 in NOR'
    (out / 'stage1_boot.bin').write_bytes(boot)
    (out / 'stage2.bin').write_bytes(stage2)
    combined = bytearray(saved)
    combined[:len(boot)] = boot
    combined[FLASH_OFFSET:FLASH_OFFSET + len(stage2)] = stage2
    (out / 'capture_sector_0.bin').write_bytes(combined)
    symbols = subprocess.check_output([str(TC / 'arm-none-eabi-nm.exe'), '--numeric-sort', str(elf)], text=True)
    assert not re.search(r'\b(HAL_BSEC_OTP_Program|Fuse_Programming|BSP_XSPI_NOR_(?:Write|Erase)\w*)$', symbols, re.M)
    (out / 'symbols.txt').write_text(symbols, encoding='utf-8')
    (out / 'stage1.lst').write_bytes(subprocess.check_output([str(TC / 'arm-none-eabi-objdump.exe'), '-d', str(elf)]))
    manifest = {
        'hardware_status': 'untested', 'stage1': inspect_image(boot),
        'stage1_raw_bytes': len(raw), 'stage1_raw_sha256': sha(raw),
        'stage2_flash_offset': hex(FLASH_OFFSET), 'stage2_load_address': hex(LOAD_ADDRESS),
        'stage2_bytes': len(stage2), 'stage2_crc32': f'0x{crc:08x}', 'stage2_sha256': sha(stage2),
        'stage2_build_manifest': str(stage2_dir / 'manifest.json'),
        'stage2_manifest_sha256': sha((stage2_dir / 'manifest.json').read_bytes()),
        'program_bytes': len(combined), 'program_sha256': sha(combined),
        'snapshot_sha256': sha(saved), 'snapshot_path': str(args.snapshot.resolve()),
        'sources': {str(s.relative_to(REPO)): sha(s.read_bytes()) for s in sources},
        'size': subprocess.check_output([str(TC / 'arm-none-eabi-size.exe'), str(elf)], text=True),
        'compile_flags': flags,
        'stage1_source_directory': str(args.stage1_source_dir.resolve()),
        'skip_sensor_reset': args.skip_sensor_reset,
        'word_reads': args.word_reads, 'xspi64': args.xspi64, 'early_sensor': args.early_sensor,
        'inline_crc': args.inline_crc, 'prefix_opt': args.prefix_opt,
        'trim_sensor': args.trim_sensor,
        'disable_darkcal': args.disable_darkcal,
        'dphy_noncontinuous': args.dphy_noncontinuous,
        'sensor_csi_mbps': args.sensor_csi_mbps,
        'sensor_source_path': str(args.sensor_source.resolve()) if args.early_sensor else None,
    }
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    assert bytes(combined[len(boot):FLASH_OFFSET]) == saved[len(boot):FLASH_OFFSET]
    assert bytes(combined[FLASH_OFFSET + len(stage2):]) == saved[FLASH_OFFSET + len(stage2):]
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
