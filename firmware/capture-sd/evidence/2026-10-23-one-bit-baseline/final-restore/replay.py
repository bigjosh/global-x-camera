"""Offline final-v59 restoration archive builder and byte-check replay.

Default operation only verifies completed local records. Copying requires the
bench owner's explicit --confirmed-complete flag; no hardware imports/actions.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zlib

ARCHIVE = Path(__file__).resolve().parents[1]
V59 = '7fda9d00cc7ffb3fbb9e6aac6695cf18545754b5dbfce1520cf30b2da39c4e63'
V60 = '20444827100b1a33826c5b7e3362a396a0ce31f27f0c3db7fea12fb755320f7e'
V59_PREFIX = '9a6c498a94c9415ec3dc39933bae2e958ceb0a43b53a1b2c8b931ef26475d071'
V60_PREFIX = 'e14913fa5c47f9d03e6680ca3ab8499afee0bf73f6654ef7d892c7303fa0ba42'
FOLLOWING = '01cc465d3a7581d9d003b09e5db684eb7bec8e8512e12ce3565154c3aced816f'
HELPER = '2dd98e8facd32426b622cb4dc023f4efac5315a7f5d336379066bda43db06909'
DIRECTORIES = ('restore-recovery', 'restore-park', 'restore-info', 'restore-v59',
               'restore-read', 'restore-following', 'restored-recovery',
               'restored-park', 'final-normal', 'final-normal-park')


def sha(raw): return hashlib.sha256(raw).hexdigest()
def require(value, message):
    if not value: raise ValueError(message)
def load(path): return json.loads(path.read_text(encoding='utf-8-sig'))
def jsonl(path): return [json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]


def verify_park(record, prefix):
    require(record['passed'] and record['prefix_sha256'] == prefix, 'Wrong or failed recovery prefix')
    context = record['context']
    require(context['PC'] == 0x3418078c and context['CONTROL'] == 0 and
            context['PRIMASK'] == 1 and context['FAULTMASK'] == 0 and
            context['XPSR'] & 0x1000000 and not context['XPSR'] & 511,
            'Recovery is not in its exact privileged Thread park')
    require(not record['ccr'] & 0x30000 and not record['fpccr'] & 1 and
            not record['xspi_sr'] & ((1 << 5) | (0x3f << 8)), 'Cache/XSPI not idle')
    vcp = record['vcp_status']
    require(vcp['request'] == 1 and vcp['source_bits'] & 2 and vcp['good_pulses'] >= 3,
            'No accepted VCP pulse request')


def verify_core(current, desired, following_before, following_after, programmed,
                independent, request, info, status, verified, read_result, following_result):
    require(len(current) == len(desired) == len(programmed) == len(independent) == 65536,
            'Wrong first-sector byte count')
    require(sha(current) == V60 and sha(desired) == V59, 'Unexpected current/restore firmware')
    require(programmed == desired and independent == desired, 'Restored firmware not byte exact')
    require(len(following_before) == len(following_after) == 4096 and
            following_before == following_after and sha(following_before) == FOLLOWING,
            'Following 4 KiB changed or unknown')
    require(request['operation'] == 'write' and request['helper_sha256'] == HELPER and
            request['current_sha256'] == V60 and request['desired_sha256'] == V59,
            'Restore did not use the exact guarded current/desired/helper identities')
    require(info['result'] == 0 and info['command'] == 2 and info['flags'] == 39 and
            info['cleanup_result'] == 0 and info['nor_status'] & 3 == 0,
            'No successful fresh idle INFO')
    require(status['result'] == 0 and status['command'] == 3 and status['stage'] == 12 and
            status['flags'] == 47 and status['cleanup_result'] == 0 and
            not status['failure_stage'] and not status['failure_opcode'] and
            not status['nor_status'] & 3 and status['sequence'] == request['sequence'],
            'Restore programming was not fully successful')
    require(status['current_crc'] == status['expected_current_crc'] == zlib.crc32(current) and
            status['input_crc'] == status['expected_input_crc'] == status['final_crc'] == zlib.crc32(desired),
            'Current/desired/final CRC guard differs')
    require(status['changed_mask'] == status['erased_mask'] == status['completed_mask'] and
            status['first_mismatch'] == 0xffffffff, 'Incomplete sector programming')
    require(verified['byte_for_byte_match'] and verified['bytes'] == 65536 and
            verified['sha256'] == V59, 'Programmer full-readback qualification absent')
    require(read_result == dict(bytes=65536, offset=0, sha256=V59, read_only=True),
            'Independent restored read metadata differs')
    require(following_result == dict(bytes=4096, offset=65536, sha256=FOLLOWING, read_only=True),
            'Independent following-sector metadata differs')


def verify_records(work, current, desired, following_before):
    for name in DIRECTORIES:
        require((work/name).is_dir(), 'Incomplete final record directory: '+name)
    verify_core(current, desired, following_before,
        (work/'restore-following/nor.bin').read_bytes(),
        (work/'restore-v59/readback.bin').read_bytes(), (work/'restore-read/nor.bin').read_bytes(),
        load(work/'restore-v59/request.json'), load(work/'restore-info/status.json'),
        load(work/'restore-v59/status.json'), load(work/'restore-v59/verified.json'),
        load(work/'restore-read/result.json'), load(work/'restore-following/result.json'))
    for name, prefix in (('restore-park', V60_PREFIX), ('restored-park', V59_PREFIX),
                         ('final-normal-park', V59_PREFIX)):
        verify_park(load(work/name/'result.json'), prefix)
    for name in ('restore-recovery', 'restored-recovery'):
        config, events = load(work/name/'config.json'), load(work/name/'events.json')
        require(config['mode'] == 'reset-bytes' and config['baud'] == 1000000 and config['byte'] == 192,
                'Unexpected UART recovery stimulus')
        names = [event['name'] for event in events]
        require(names.index('break_api_asserted') < names.index('break_api_released') <
                names.index('uart_closed'), 'UART reset/release/close sequence incomplete')
    cycle = jsonl(work/'final-normal/cycle.jsonl')
    event = {record['event']: record for record in cycle}
    require(event['command_off']['monotonic_ns'] < event['command_auto']['monotonic_ns'] <
            event['normal_boot_terminal']['monotonic_ns'] < event['command_stop']['monotonic_ns'],
            'Final normal power-cycle sequence incomplete')
    require(event['normal_boot_terminal']['firmware_writes'] is False,
            'Unexpected final normal-cycle firmware write')
    response = load(work/'final-normal/response.json')
    require(response['event'] == 'stopped' and response['ok'] and
            response['restore_error'] is None and response['range'] == response['starting_range'] == 128,
            'JS110 helper did not close with original range restored')
    stats = response['statistics']
    require(stats['voltage']['avg'] > 4.5 and 0 < stats['current']['avg'] < .020,
            'Final measured source/current did not reach the expected powered low-current range')
    return dict(schema=1, restored_sector_sha256=V59, prior_sector_sha256=V60,
        source_v59_matches_original_archive=True, programmer_readback_matches=True,
        independent_readback_matches=True, following_4k_sha256=FOLLOWING,
        following_4k_unchanged=True, fresh_info_passed=True, successful_guarded_write=True,
        restored_vcp_recovery_passed=True, final_normal_power_cycle_recorded=True,
        final_js110_closed_with_range_restored=True, final_source_voltage_v=stats['voltage']['avg'],
        final_current_ma=stats['current']['avg']*1000, final_response_utc=response['utc'],
        final_normal_saved_png_verified=False, final_normal_standby_flag_verified=False,
        limits=['The final low-current signature is not an independent WFI/Standby flag or PNG readback.',
                'Remaining CN8/debugger bypass paths lie outside the JS110-fed measurement boundary.',
                'The recovery park before the final normal cycle does not describe the final executing PC.'])


def archive(work, out):
    current = (ARCHIVE/'build/v60c-awake/staged/capture_sector_0.bin').read_bytes()
    desired = (ARCHIVE.parent/'2026-10-20-low-power/build/prefix/capture_sector_0.bin').read_bytes()
    before = (ARCHIVE/'nor-maintenance/operations/following-nor-read/nor.bin').read_bytes()
    result = verify_records(work, current, desired, before)
    out.mkdir(exist_ok=False)
    files, omitted = {}, []
    def write(relative, raw):
        destination = out/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        files[relative] = sha(raw)
    for relative, raw in (('inputs/v60-before.bin', current), ('inputs/v59-original.bin', desired),
                          ('inputs/following-before.bin', before)):
        write(relative, raw)
    for name in DIRECTORIES:
        for path in sorted((work/name).iterdir()):
            if not path.is_file(): continue
            permitted = (path.suffix.lower() in ('.json', '.jsonl', '.log', '.txt', '.bin') and
                         path.stat().st_size <= 262144 and
                         not any(part in path.name.lower() for part in ('frame', 'image', 'png', 'pixels')))
            if permitted:
                write('records/'+name+'/'+path.name, path.read_bytes())
            else:
                omitted.append(dict(path=str(path), bytes=path.stat().st_size,
                    reason='Not a compact explicitly permitted firmware/metadata file; not copied'))
    write('verified-restore.json', (json.dumps(result, indent=2)+'\n').encode())
    write('omitted-files.json', (json.dumps(omitted, indent=2)+'\n').encode())
    write('replay.py', Path(__file__).read_bytes())
    manifest = dict(schema=1, scope='Compact final v59 restoration and final normal-cycle evidence',
                    original_work_path=str(work), files=files)
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    return result


def replay(root):
    manifest = load(root/'manifest.json')
    for name, expected in manifest['files'].items():
        path = (root/name).resolve()
        require(path.is_relative_to(root.resolve()) and sha(path.read_bytes()) == expected,
                'Archive file differs: '+name)
    actual = verify_records(root/'records', (root/'inputs/v60-before.bin').read_bytes(),
                            (root/'inputs/v59-original.bin').read_bytes(),
                            (root/'inputs/following-before.bin').read_bytes())
    require(actual == load(root/'verified-restore.json'), 'Derived final verification differs')
    return dict(passed=True, files_verified=len(manifest['files']), **actual)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--confirmed-complete', action='store_true')
    parser.add_argument('--replay', type=Path)
    args = parser.parse_args()
    if args.replay:
        result = replay(args.replay.resolve())
    elif args.work:
        if args.confirmed_complete:
            require(args.out is not None, '--out is required for an archive')
            result = archive(args.work.resolve(), args.out.resolve())
        else:
            require(args.out is None, 'No copying before --confirmed-complete')
            result = verify_records(args.work.resolve(),
                (ARCHIVE/'build/v60c-awake/staged/capture_sector_0.bin').read_bytes(),
                (ARCHIVE.parent/'2026-10-20-low-power/build/prefix/capture_sector_0.bin').read_bytes(),
                (ARCHIVE/'nor-maintenance/operations/following-nor-read/nor.bin').read_bytes())
    else:
        parser.error('Use --work for verification or --replay for an existing archive')
    print(json.dumps(result, indent=2))
