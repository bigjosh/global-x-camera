"""Verify an independently reviewed exact GPIO-blink UART recovery image.

No reset or stimulus. The original full-prefix, pulse, context and XSPI-idle
checks remain in use. Candidates require explicit byte-identity admission here.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'firmware/boot-timing'))
import nor_bench
nor_bench.CLI = ROOT / 'tmp/bringup/control-smoke-20261107/tools/programmer-2.23.0/bin/STM32_Programmer_CLI.exe'

# November13 build01: independent frozen-prefix comparison, decoded normal-only
# B.W, retained fault vectors/helpers and early PA2 hook,624-byte linked GPIO loop.
# This is precise candidate admission, not a claim of hardware qualification.
APPROVED = {
    '6d4deeee7b248f7e2d71a79d9bd5dcfd36bce87658138918c88b7dc87efa0869':
        dict(bytes=7160, sector='28257715f614d42048618847be4edb1f13564edb47b0f265efb38785fa63d23a'),
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    manifest = json.loads((args.build / 'manifest.json').read_text())
    entry = APPROVED.get(manifest.get('prefix_sha256'))
    if (manifest.get('kind') != 'a0-a5-gpio-blink-flash' or entry is None or
            manifest.get('sector0_sha256') != entry['sector'] or
            manifest.get('prefix_bytes') != entry['bytes']):
        raise ValueError('GPIO-blink build has not received exact independent review')
    spec = importlib.util.spec_from_file_location('blink_early_guard',
             ROOT / 'firmware/capture-timing/recovery_gpio/check_park.py')
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    guard.APPROVED[manifest['prefix_sha256']] = dict(entry, park=0x3418078C, vcp=True)
    sys.argv = ['guard', '--build', str(args.build / 'recovery'), '--out', str(args.out)]
    guard.main()


if __name__ == '__main__':
    main()
