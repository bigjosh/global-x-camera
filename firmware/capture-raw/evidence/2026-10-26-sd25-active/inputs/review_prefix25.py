"""Independent offline exact recovery audit for the selected 25 MHz startup profile."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'tmp/bringup/sd-fourbit-20261024/flash125-v23'
OLD_PREFIX = '09fb59cfed0f715927e76f32d5f74187e4c2f1702a70ce192e0d17dcee2f822a'
OLD_SECTOR = 'bb31867394a4e0d0fb9ab3f9fa96d0d16ffc7256e2a274db74be4f11f9cfdc14'
TC = Path('D:/ST/STM32CubeIDE_1.15.1/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.12.3.rel1.win32_1.0.200.202406191623/tools/bin')
CRC_WORDS = (3228, 4948)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def listing(text):
    rows = []
    for line in text.splitlines():
        match = re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f ]+)\t(.*)$', line)
        if match:
            address = int(match[1], 16)
            if address - 0x34180400 not in CRC_WORDS:
                rows.append((address, match[2].strip(), match[3].strip()))
    assert len(rows) > 1000
    return rows


def elf_check(path, expected_binary):
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary:
        binary = Path(temporary) / 'elf.bin'
        subprocess.run([str(TC / 'arm-none-eabi-objcopy.exe'), '-O', 'binary',
                        str(path), str(binary)], check=True)
        assert binary.read_bytes() == expected_binary
    return subprocess.check_output(
        [str(TC / 'arm-none-eabi-objdump.exe'), '-d', str(path)], text=True)


def review(build):
    old, new = BASE / 'staged', build / 'staged'
    om = json.loads((old / 'manifest.json').read_text())
    nm = json.loads((new / 'manifest.json').read_text())
    m = json.loads((build / 'manifest.json').read_text())
    base = (old / 'stage1.bin').read_bytes()
    prefix = (new / 'stage1.bin').read_bytes()
    code = (build / 'capture.bin').read_bytes()
    sector = (new / 'capture_sector_0.bin').read_bytes()
    assert sha(base) == OLD_PREFIX
    assert sha((old / 'capture_sector_0.bin').read_bytes()) == OLD_SECTOR
    assert len(prefix) == len(base) == 5140
    assert m['flash'] and m['sd_clock_negedge'] and m['sd_clock_negedge_init']
    assert m['sd_clock_hz'] == 25000000 and m['sd_bus_width'] == 4
    assert m['sd_review_profile'] and m['sd_startup_opt']
    assert m['sd_kernel_hz'] == 150000000 and m['sd_switch_clock_hz'] is None
    assert m['sd_identification_clock_negedge'] and m['sd_transfer_clock_negedge']
    assert m['sd_gpio_speed'] == 3 and m['transport'] == 'idma'
    assert m['magic_format'] and m['line_stream'] and m['async_stop']
    assert m['chunk_sectors'] == 3730 and m['exposure_coarse'] == 1428
    for key in ('sd_high_speed', 'sd_high_speed_mixed_slew',
                'sd_high_speed_fixed_compensation', 'sd_high_speed_combined_electrical',
                'sd_fixed_compensation', 'sd_compensation_modified', 'sd_idma_read',
                'raw_dma_tail_wait', 'dma_sleep', 'preinit', 'line_snapshots',
                'line_poison', 'whole_image_preerase', 'cycle_trace', 'sd_early_run_clock'):
        assert not m.get(key), key
    assert nm['stage2_bytes'] == m['late_load']['early_bytes'] == 15804
    assert m['late_load']['after_arm'] and m['late_load']['interrupts_enabled']
    assert sha(prefix) == nm['stage1_raw_sha256']
    assert sha(code) == m['binary_sha256'] == nm['stage2_full_sha256']
    assert len(sector) == 65536 and sha(sector) == nm['program_sha256']
    assert sector[0x2000:0x2000 + len(code)] == code
    boot = (new / 'stage1_boot.bin').read_bytes()
    assert boot[1024:1024 + len(prefix)] == prefix
    assert sha(boot) == nm['stage1']['sha256'] and sector[:len(boot)] == boot
    assert nm['checked_recovery_literal_offsets'] == om['checked_recovery_literal_offsets']
    for offset in nm['checked_recovery_literal_offsets']:
        assert prefix[offset:offset + 4] == base[offset:offset + 4]
    for key in ('recovery_gpio', 'recovery_vcp'):
        assert nm[key] == om[key], key
    changed = [i for i, (a, b) in enumerate(zip(base, prefix)) if a != b]
    assert {i & ~3 for i in changed}.issubset(set(CRC_WORDS))
    crc = zlib.crc32(code[:15804])
    for offset in CRC_WORDS:
        assert struct.unpack_from('<I', prefix, offset)[0] == crc
    assert nm['stage2_crc32'] == hex(crc)
    rows = listing(elf_check(new / 'stage1.elf', prefix))
    assert rows == listing((new / 'stage1.lst').read_text())
    assert rows == listing(elf_check(old / 'stage1.elf', base))
    assert rows == listing((old / 'stage1.lst').read_text())
    elf_check(build / 'capture.elf', code)
    assert prefix[0x38C:0x38E] == b'\xfe\xe7'
    return dict(passed=True, hardware_accessed=False, allowlist_modified=False,
                reviewer='/root/promote25_review', build=str(build.relative_to(ROOT)),
                profile='reviewed25-startup-no-tail', standby=bool(m['standby']),
                baseline_prefix_sha256=OLD_PREFIX, baseline_sector_sha256=OLD_SECTOR,
                binary_sha256=sha(code), prefix_sha256=sha(prefix), sector_sha256=sha(sector),
                prefix_bytes=len(prefix), early_load_bytes=15804,
                recovery_literal_count=len(nm['checked_recovery_literal_offsets']),
                compared_listing_rows=len(rows), recovery_schema_unchanged=True,
                fresh_objcopy_and_objdump_verified=True,
                changed_prefix_bytes=changed, crc_literal_offsets=list(CRC_WORDS),
                early_crc32=hex(crc), park_address='0x3418078c',
                limits='Exact-pair recovery admission only. Cold capture/readback and Standby still require root-owned hardware verification.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = review(args.build.resolve())
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
