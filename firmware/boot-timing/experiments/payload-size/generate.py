"""Build local, inert-padded boot images to measure ROM image-size cost.

Historical non-debug variants: superseded for bench use by build_debug.py,
because normal-boot access needs post-marker firmware debug authorization.

Does not connect to or program hardware. Keeps the known-good 256-byte payload
unchanged, including its vectors, marker instructions and WFI loop. The extra
bytes are loaded and checksummed by ROM but never accessed by this program.

The variants append 8192 or 32768 bytes, producing 9472 or 34048 byte images.
Both fit within the first 64 KiB NOR sector. Before programming, save and
independently verify the current first 65536 bytes of NOR. --snapshot accepts
that current sector and produces programming buffers preserving the trailing
bytes, plus an exact restoration file. It does not claim to verify the
device-side snapshot.

Run from any directory. By default writes a NEW ignored tmp/bringup directory;
existing output is refused. --output selects another new directory.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

BOOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BOOT_DIR))
from add_boot_header import make_image, inspect_image

BASELINE_PAYLOAD_SHA256 = '14d4c8ff2fc72c9df04dafa4a1a910a5f9fec39f09cc9e2d3e10e91105e34c44'
BASELINE_IMAGE_SHA256 = '1c1aeff1a482f5edd6509cbcdef52da976cc5cc07e4b92bcfedebd0d08820cca'
SECTOR_BYTES = 65536
SNAPSHOT_BYTES = SECTOR_BYTES


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_checked(path, data):
    with path.open('xb') as stream:
        stream.write(data)
    if path.read_bytes() != data:
        raise ValueError(f'Local output readback failed: {path}')


def generate(output, snapshot_path=None):
    payload = (BOOT_DIR / 'build/first_gpio.bin').read_bytes()
    baseline = (BOOT_DIR / 'build/first_gpio_boot.bin').read_bytes()
    if len(payload) != 256 or digest(payload) != BASELINE_PAYLOAD_SHA256:
        raise ValueError('Baseline payload differs from the measured 256-byte image')
    if digest(baseline) != BASELINE_IMAGE_SHA256 or make_image(payload) != baseline:
        raise ValueError('Baseline boot image differs from the measured 1280-byte image')
    snapshot = snapshot_path.read_bytes() if snapshot_path else None
    if snapshot is not None:
        if len(snapshot) != SNAPSHOT_BYTES:
            raise ValueError('Current NOR sector snapshot must be exactly 65536 bytes')
        if snapshot[:len(baseline)] != baseline:
            raise ValueError('Snapshot does not begin with the known-good baseline boot image')
    output.mkdir(parents=True, exist_ok=False)
    manifest = {
        'no_hardware_access': True,
        'baseline_payload_sha256': digest(payload),
        'baseline_image_sha256': digest(baseline),
        'padding_byte': '0xa5',
        'flash_base': '0x70000000',
        'sector_bytes': SECTOR_BYTES,
        'required_restoration_prefix_bytes': SNAPSHOT_BYTES,
        'snapshot_path': str(snapshot_path.resolve()) if snapshot_path else None,
        'snapshot_sha256': digest(snapshot) if snapshot is not None else None,
        'variants': [],
        'notes': [
            'Only the header length/checksum and inert tail differ; executable bytes are identical.',
            'Payload size excludes the 1024-byte prefix; ROM checksum length includes 448 alignment bytes.',
            'Large inert tails cover the stack region; the stack may overwrite that padding safely.',
            'No signing keys, OTP, lifecycle, clocks or GPIO instructions are changed.',
            'Measure a restored baseline again after size variants to detect drift or state dependence.',
            'Full-sector buffers are for programming; only the standalone boot image is header-validated.',
        ],
    }
    for added in (0, 8192, 32768):
        size = len(payload) + added
        padded = payload + bytes([0xA5]) * added
        image = make_image(padded)
        if image[0x400:0x500] != payload:
            raise ValueError('Executable prefix unexpectedly changed')
        inspected = inspect_image(image)
        stem = f'first_gpio_plus_{added}'
        write_checked(output / f'{stem}.bin', padded)
        write_checked(output / f'{stem}_boot.bin', image)
        sectors = (len(image) + SECTOR_BYTES - 1) // SECTOR_BYTES
        if sectors != 1:
            raise ValueError('All size experiments must stay within NOR sector 0')
        entry = {**inspected, 'raw_payload_bytes': size,
                 'padding_bytes': added,
                 'raw_payload_sha256': digest(padded),
                 'boot_file': f'{stem}_boot.bin', 'erase_sectors_touched': sectors,
                 'last_flash_byte': f'{0x70000000 + len(image) - 1:#010x}'}
        if snapshot is not None:
            program = image + snapshot[len(image):sectors * SECTOR_BYTES]
            filename = f'{stem}_program_sectors.bin'
            write_checked(output / filename, program)
            entry.update({'program_file': filename, 'program_bytes': len(program),
                          'program_sha256': digest(program)})
        manifest['variants'].append(entry)
    if snapshot is not None:
        write_checked(output / 'restore_current_sector_0.bin', snapshot)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=BOOT_DIR.parents[1] / 'tmp/bringup/payload-size-20261017')
    parser.add_argument('--snapshot', type=Path,
                        help='Verified CURRENT first 65536 bytes of NOR, not the pre-baseline backup')
    args = parser.parse_args()
    try:
        result = generate(args.output.resolve(), args.snapshot)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Error: {exc}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
