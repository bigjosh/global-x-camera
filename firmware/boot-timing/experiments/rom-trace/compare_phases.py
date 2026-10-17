"""Compare decoded ROM phase intervals offline; preserve raw tick units.

Pass decode_trace.py JSON files, followed by --output PATH. Boundary buffer
names distinguish same-buffer intervals from assumption-dependent differences
between buffers. No hardware or capture directory is modified.
"""
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(path):
    decoded = json.loads(path.read_text(encoding='utf-8-sig'))
    records = decoded['records']
    def buffer_name(record):
        return record['source'].replace('\\', '/').rsplit('/', 1)[-1]
    by_buffer = {name: sorted([record for record in records if buffer_name(record) == name],
                              key=lambda record: record['offset'])
                 for name in ('secure-trace.bin', 'nonsecure-trace.bin')}
    checks = {
        'no_rejected_candidates': all(not value for value in decoded['rejected_candidates'].values()),
        'raw_buffers_match_decoder_hashes': all(Path(item['path']).stat().st_size == item['bytes']
            and digest(Path(item['path'])) == item['sha256'] for item in decoded['buffers']),
        'timestamps_increase_within_each_buffer': all(items[i]['timestamp_raw'] > items[i - 1]['timestamp_raw']
                                         for items in by_buffer.values() for i in range(1, len(items))),
    }

    def unique(field, value):
        found = [record for record in records if record[field] == value]
        checks['one_' + value] = len(found) == 1
        return found[0] if len(found) == 1 else None

    def span(start, end):
        if start is None or end is None or end['timestamp_raw'] < start['timestamp_raw']:
            return None
        return end['timestamp_raw'] - start['timestamp_raw']

    padding = unique('event', 'DWNLDMGR_FoundPaddingHeader')
    following = next((record for record in records if padding is not None
                      and record['timestamp_raw'] > padding['timestamp_raw']
                      and record['event'] == 'BOOTCORE_NoDataCacheBitValue'), None)
    checks['nocache_event_after_padding'] = following is not None
    entry = unique('event', 'SECBOOT_AuthImageEntryPoint')
    jump = unique('event', 'SECBOOT_AuthDecisionIsJumpToImage')
    length = unique('event', 'SECBOOT_AuthImageLength')
    wait_start = unique('code', '0x00002900')
    wait_end = unique('code', '0x00000152')
    single = unique('event', 'OSPI_TryingSingleMode')
    secure_start = unique('code', '0x2a000004')
    secure_next = next((record for record in by_buffer['secure-trace.bin'] if secure_start is not None
                       and record['offset'] > secure_start['offset']
                       and record['event'] == 'BOOTCORE_NoDataCacheBitValue'), None)
    checks['secure_nocache_event_after_unknown_0x2a000004'] = secure_next is not None
    return {
        'label': path.stem, 'decoded_json': str(path.resolve()), 'decoded_sha256': digest(path),
        'structural_checks_passed': all(checks.values()), 'checks': checks,
        'record_count': decoded['record_count'],
        'record_counts_by_buffer': {name: len(items) for name, items in by_buffer.items()},
        'raw_buffers': decoded['buffers'], 'reference': decoded.get('reference'),
        'auth_image_length': int(length['arguments'][0], 16) if length and length['arguments'] else None,
        'auth_entry_address': entry['arguments'][0] if entry and entry['arguments'] else None,
        'phase_spans_raw_ticks': {
            'trying_single_mode_to_padding_header': span(single, padding),
            'nonsecure_padding_to_secure_nocache_timestamp_difference': span(padding, following),
            'secure_unknown_0x2a000004_to_next_nocache': span(secure_start, secure_next),
            'auth_entry_event_to_jump_decision': span(entry, jump),
            'unknown_0x2900_to_unknown_0x152': span(wait_start, wait_end),
        },
        'unknown_0x152_arguments': wait_end['arguments'] if wait_end else None,
        'phase_buffer_scope': {
            'trying_single_mode_to_padding_header': 'nonsecure only',
            'nonsecure_padding_to_secure_nocache_timestamp_difference': 'cross-buffer; shared timebase assumed',
            'secure_unknown_0x2a000004_to_next_nocache': 'secure only; start semantics unknown',
            'auth_entry_event_to_jump_decision': 'secure only',
            'unknown_0x2900_to_unknown_0x152': 'secure only; both event semantics unknown',
        },
        'event_boundaries': {name: {'offset': record['offset'], 'timestamp_raw': record['timestamp_raw'],
                                   'code': record['code'], 'event': record['event'], 'buffer': buffer_name(record)}
                             for name, record in [('padding_header', padding), ('next_nocache', following),
                                                  ('secure_unknown_start', secure_start), ('secure_next_nocache', secure_next),
                                                  ('auth_entry', entry), ('jump_decision', jump)] if record},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('decoded', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in {path.resolve() for path in args.decoded}:
        parser.error('Output must not overwrite an input')
    try:
        runs = [compare(path) for path in args.decoded]
        baseline = next((run for run in runs if run['label'] == 'baseline-01'), None)
        if baseline:
            for run in runs:
                run['phase_delta_from_baseline_01_raw_ticks'] = {
                    key: value - baseline['phase_spans_raw_ticks'][key]
                    for key, value in run['phase_spans_raw_ticks'].items()
                    if value is not None and baseline['phase_spans_raw_ticks'][key] is not None}
        result = {
            'structural_checks_passed': all(run['structural_checks_passed'] for run in runs),
            'runs': runs,
            'limitations': [
                'Values are raw ROM timer ticks, not external NRST or rail timestamps; phase_buffer_scope identifies each boundary source.',
                'The nonsecure-padding to secure-nocache subtraction additionally assumes a shared timebase across the two buffers.',
                'Microsecond comparisons require the stated timer-rate/continuity assumption; they are not a new clock measurement.',
                'Known events identify interval boundaries, not a complete semantic breakdown of the intervening ROM instructions.',
                'The 0x2900 and 0x152 event names remain unknown; their spacing and argument are numeric observations only.',
                'No rejected records and matching hashes do not by themselves prove a complete trace.',
                'Only variants with saved ROM buffers are included; absent repeat buffers are not synthesized.',
            ]}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        for run in runs:
            print(run['label'], run['structural_checks_passed'], run['auth_image_length'],
                  run['phase_spans_raw_ticks'])
        return 0 if result['structural_checks_passed'] else 1
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f'Error: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
