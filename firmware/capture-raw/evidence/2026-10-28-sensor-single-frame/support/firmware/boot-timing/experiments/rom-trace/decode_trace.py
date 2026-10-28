"""Decode saved STM32N6 ROM trace buffers; no network or device access.

Numeric decoding needs only Python's standard library. Optional --reference
extracts event names from an exact hash-verified local ST parser; vendor source
and its lookup table are not bundled. See reference-provenance.json and README.
Raw timestamp sorting is not a reconstruction across timer resets or wrap.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct

PROVENANCE = Path(__file__).with_name('reference-provenance.json')


def load_reference(path):
    expected = json.loads(PROVENANCE.read_text(encoding='utf-8'))['parser']
    source = path.read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    if digest != expected['sha256']:
        raise ValueError('Reference SHA-256 does not match the pinned ST parser')
    names = {int(code, 16): name for code, name in re.findall(
        r'case\s+(0x[0-9a-fA-F]+)\s*:\s*\*outString\s*=\s*"([^"]+)"',
        source.decode('utf-8'))}
    if len(names) != expected['event_count']:
        raise ValueError('Pinned reference event count does not match')
    return names, {'path': str(path), 'sha256': digest, 'url': expected['url']}


def decode(path, names):
    data = path.read_bytes()
    records, rejected = [], []
    pos = 0
    while pos + 4 <= len(data):
        if struct.unpack_from('<I', data, pos)[0] != 0xFFDDBB00:
            pos += 4
            continue
        if pos + 20 > len(data):
            rejected.append({'offset': pos, 'reason': 'truncated_header'})
            break
        _, size, stamp, level, code = struct.unpack_from('<5I', data, pos)
        end = pos + 8 + size
        if size < 12 or size % 4 or end > len(data) or level > 3:
            rejected.append({'offset': pos, 'size': size, 'level': level})
            pos += 4
            continue
        words = struct.unpack_from('<' + 'I' * ((size - 12) // 4), data, pos + 20)
        records.append({'source': str(path), 'offset': pos,
                        'timestamp_raw': stamp, 'level': ['INFO', 'WARN', 'ERR', 'DEBUG'][level],
                        'code': f'0x{code:08x}', 'event': names.get(code, 'UNKNOWN'),
                        'arguments': [f'0x{word:08x}' for word in words]})
        pos = end
    return records, rejected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('buffers', nargs='+', type=Path)
    parser.add_argument('--reference', type=Path,
                        help='Optional local ST parser matching reference-provenance.json')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    inputs = args.buffers + ([args.reference] if args.reference else [])
    if args.output and args.output.resolve() in {path.resolve() for path in inputs}:
        parser.error('Output must not overwrite an input')
    try:
        names, reference = load_reference(args.reference) if args.reference else ({}, None)
        all_records, rejected, buffers = [], {}, []
        for path in args.buffers:
            records, bad = decode(path, names)
            all_records.extend(records)
            rejected[str(path)] = bad
            data = path.read_bytes()
            buffers.append({'path': str(path), 'bytes': len(data),
                            'sha256': hashlib.sha256(data).hexdigest(),
                            'record_count': len(records)})
        all_records.sort(key=lambda record: record['timestamp_raw'])
        output = {'reference': reference, 'reference_event_count': len(names),
                  'record_count': len(all_records), 'buffers': buffers,
                  'code_counts': dict(sorted(Counter(record['code'] for record in all_records).items())),
                  'records': all_records, 'rejected_candidates': rejected,
                  'timing_caveat': 'Raw timer timestamps, not power-on or NRST time. Qualify origin, '
                                   'continuity and clock rate. Raw sorting does not unwrap the '
                                   '32-bit timer or establish ordering across resets/buffers.',
                  'decoding_caveat': 'UNKNOWN retains the numeric code. Rejected candidates are '
                                     'reported; decoded records alone do not prove a complete trace.'}
        text = json.dumps(output, indent=2)
        if args.output:
            args.output.write_text(text + '\n', encoding='utf-8')
        print(text)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
