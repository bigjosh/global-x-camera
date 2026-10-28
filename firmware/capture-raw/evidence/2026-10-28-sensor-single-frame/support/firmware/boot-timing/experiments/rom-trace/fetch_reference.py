"""Optionally fetch the pinned ST parser to ignored local storage; no hardware.

The decoder itself never downloads files. This separate helper uses verified
HTTPS, checks SHA-256 before saving, preserves upstream notices, and refuses
to overwrite a different existing file. Upstream terms remain applicable.
"""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[4]
                        / 'tmp/boot-rom-reference/rom_trace_parser.c')
    args = parser.parse_args()
    reference = json.loads(Path(__file__).with_name('reference-provenance.json')
                           .read_text(encoding='utf-8'))['parser']
    try:
        if args.output.exists():
            data = args.output.read_bytes()
        else:
            with urllib.request.urlopen(reference['url'], timeout=30) as response:
                data = response.read()
        digest = hashlib.sha256(data).hexdigest()
        if digest != reference['sha256']:
            raise ValueError('Reference SHA-256 mismatch; no output was written')
        if not args.output.exists():
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open('xb') as target:
                target.write(data)
        if args.output.read_bytes() != data:
            raise ValueError('Saved reference readback differs')
        print(json.dumps({'path': str(args.output.resolve()), 'url': reference['url'],
                          'bytes': len(data), 'sha256': digest}, indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
