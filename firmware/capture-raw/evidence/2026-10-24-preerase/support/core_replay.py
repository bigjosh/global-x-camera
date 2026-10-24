"""Verify archived RAW-slot proofs, source bytes, failed/successful SD payloads.

Offline only. Never imports the bench, serial, debugger or instrument runners.
The independent scalar RAW10 decoder and pure format/producer validators are
loaded from their verified archived source bytes. No hardware state is inferred.
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import statistics
import struct
import types
import zlib

HERE = Path(__file__).resolve().parent
FRAME_BYTES = 1909600


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def checked_name(name):
    p = PurePosixPath(name)
    if not name or '\\' in name or ':' in name or p.is_absolute() or '..' in p.parts:
        raise ValueError('Unsafe archived relative name: ' + name)
    return p


def read_object(record):
    path = (HERE / checked_name(record['path'])).resolve()
    path.relative_to(HERE.resolve())
    raw = path.read_bytes()
    if len(raw) != record['stored_bytes'] or sha(raw) != record['stored_sha256']:
        raise ValueError('Stored object identity differs: ' + str(path))
    if record['encoding'] == 'zlib':
        decoder = zlib.decompressobj()
        data = decoder.decompress(raw, record['bytes'] + 1)
        if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError('Truncated, trailing or oversized compressed object')
    elif record['encoding'] == 'identity':
        data = raw
    else:
        raise ValueError('Unknown object encoding')
    if len(data) != record['bytes'] or sha(data) != record['sha256']:
        raise ValueError('Decoded object identity differs: ' + str(path))
    return data


def file_bytes(record):
    return {name: read_object(item) for name, item in record['files'].items()
            if checked_name(name)}


def load_tool(index, name):
    item = index['tools'][name]
    raw = read_object(item)
    module = types.ModuleType('raw_archive_' + Path(name).stem)
    module.__file__ = str(HERE / item['path'])
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module


def verify_builds(index):
    builds = {}
    for name, record in index['builds'].items():
        files = file_bytes(record)
        m = json.loads(files['manifest.json'])
        code = files['capture.bin']
        if sha(code) != m['binary_sha256'] or len(code) != m['binary_bytes']:
            raise ValueError('Build code differs: ' + name)
        for source, expected in m['source_hashes'].items():
            if sha(files[source]) != expected:
                raise ValueError('Build source differs: ' + name + '/' + source)
        if struct.unpack_from('<II', code) != (m['stack'], m['entry']):
            raise ValueError('Build vector differs: ' + name)
        for key in ('park', 'reject_park'):
            off = m[key] - m['load']
            if off < 0 or code[off:off+2] != b'\xfe\xe7':
                raise ValueError('Terminal loop differs: ' + name)
        if 'staged/manifest.json' in files:
            pm = json.loads(files['staged/manifest.json'])
            if sha(files['staged/capture_sector_0.bin']) != pm['program_sha256']:
                raise ValueError('Cold NOR sector differs: ' + name)
            for source, expected in pm['sources'].items():
                if sha(files['staged/' + source.replace('\\', '/').rsplit('/', 1)[-1]]) != expected:
                    raise ValueError('Cold prefix source differs')
        builds[m['binary_sha256']] = (name, m, code)
    return builds


def terminal_proof(verified, files, prefix, builds):
    """Replay durable terminal facts, without executing the hardware bench gate."""
    p = verified['proof']
    if not verified.get('passed') or verified['binary_sha256'] not in builds:
        raise ValueError('Missing build/terminal provenance')
    name, m, code = builds[verified['binary_sha256']]
    if (p['magic'], p['schema'], p['words'], p['state'], p['result'], p['stage'], p['terminal']) != (
            0x52535731, 1, 96, 3, 0, 8, 0x5253444e):
        raise ValueError('Unsuccessful or incomplete terminal')
    for key in ('sd_error', 'initialized', 'controller_owned', 'cleanup_error', 'control',
                'ipsr', 'cpacr', 'systick', 'capture_error'):
        if p[key]:
            raise ValueError('Unsafe terminal field: ' + key)
    if p['media_idle'] != 1 or p['primask'] != 1 or p['ccr'] & (1 << 16) or p['last_ready'] & 0x1f00 != 0x900:
        raise ValueError('Idle/context mismatch')
    flash_inspection = verified.get('kind') == 'raw-flash-inspection'
    request = verified.get('request_words')
    if flash_inspection:
        if not m['flash'] or m['standby'] or p['nonce'] or p['operation'] != 1:
            raise ValueError('Expected awake FLASH inspection')
    elif (not request or len(request) != 16 or request[0] != 0x52535131
          or request[1] != p['nonce'] or request[2] != p['operation']):
        raise ValueError('Request identity differs')
    # Historical JSON keeps the exact 96-word ordered field list (last two were
    # originally reserved, later chunk_count/overflow). Validate binary identity.
    binary = struct.pack('<96I', *p.values())
    candidates = [prefix + sub + '/final-proof.bin' for sub in ('operation', 'bootstrap')]
    if flash_inspection:
        candidates = [prefix + 'inspection/' + f for f in
                      ('proof-before.bin', 'proof-before-halt.bin', 'proof-final.bin')]
    actual = [files[k] for k in candidates if k in files]
    if not actual or any(raw != binary for raw in actual):
        raise ValueError('Binary/JSON final proof differs')
    for sub in ('operation', 'bootstrap'):
        for suffix in ('executable-readback.bin', 'completed-code.bin'):
            key = prefix + sub + '/' + suffix
            expected = code[:m['immutable_bytes']] if suffix == 'completed-code.bin' else code
            if key in files and files[key] != expected:
                raise ValueError('Executed code differs: ' + key)
        key = prefix + sub + '/raw-request-readback.bin'
        if key in files and files[key] != struct.pack('<16I', *request):
            raise ValueError('Live request differs')
    if flash_inspection:
        for i, (start, end) in enumerate(m['immutable_ranges']):
            if files[prefix + f'inspection/code-{i}.bin'] != code[start-m['load']:end-m['load']]:
                raise ValueError('Cold immutable range differs')
        loader = struct.unpack('<16I', files[prefix+'inspection/late-loader.bin'])
        late = m['late_load']
        if (loader[0] != 0x524c4431 or loader[15] != 0x524c4f4b or loader[10]
                or loader[3] != late['late_bytes'] or loader[5] != late['late_bytes']
                or loader[6] != late['late_crc32'] or loader[7] != late['late_crc32']):
            raise ValueError('Cold late-loader proof differs')
    op = p['operation']
    if op == 1:
        if (p['camera_ready'], p['dma_bytes'], p['frames'], p['format'], p['data_type'],
            p['written_sectors']) != (FRAME_BYTES, FRAME_BYTES, 1, 10, 48, 3730):
            raise ValueError('Capture completeness differs')
        if p['errors'] or p['canary'] or not p['camera_stop'] or not p['commit_done']:
            raise ValueError('Camera/commit failure')
        if p['card_write_lo'] != 3732 or p['card_write_hi']:
            raise ValueError('Unexpected capture writes')
    elif op == 2:
        if not p['slot_count'] or p['formatted_slots'] != p['slot_count'] or p['card_write_lo'] != p['slot_count'] + 2:
            raise ValueError('Incomplete format')
        if (p['generation_lo'], p['generation_hi']) != tuple(request[3:5]):
            raise ValueError('Format generation differs')
        if request[5] and p['slot_count'] != request[5]:
            raise ValueError('Bounded format count differs')
    elif op == 3:
        if p['card_write_lo'] or p['card_write_hi'] or p['read_lba'] != request[3] or p['read_count'] != request[4]:
            raise ValueError('Read scope/write guard differs')
        if not 0 < p['read_count'] <= 512 or p['read_bytes'] != p['read_count'] * 512:
            raise ValueError('Read length differs')
    else:
        raise ValueError('Unsupported operation')
    return dict(build=name, operation=op, slot=p['slot'], slot_count=p['slot_count'])


def replay_cold_and_failure(index, records, builds, fmt):
    if 'awake-inspect02' not in records:
        return None
    install = records['flash-awake-write01']
    installed = json.loads(install['verified.json'])
    desired = json.loads(install['request.json'])['desired_sha256']
    mrecord = index['builds']['flash-awake-line-v9']
    sector = read_object(mrecord['files']['staged/capture_sector_0.bin'])
    if not installed['byte_for_byte_match'] or sha(sector) != desired or install['readback.bin'] != sector:
        raise ValueError('v9 NOR installation readback differs')
    before = records['nor-following-before01']['nor.bin']
    after = records['nor-following-after01']['nor.bin']
    if len(before) != 4096 or before != after:
        raise ValueError('Following NOR guard changed')
    completion = json.loads(records['flash-awake-write01-diagnostic']['result.json'])
    if completion['pending_operations'] or completion['first_failure_result'] or completion['last_status'] & 3:
        raise ValueError('NOR helper completion was not idle')
    cold = records['awake-cycle01']
    cycle = json.loads(cold['result.json'])
    phase = json.loads(cold['phase-summary.json'])
    if (not cycle['recording_complete'] or cycle['expected_end'] != 'awake'
            or cycle['phase_decode_passed'] or phase['decode_passed']
            or cycle['sector_sha256'] != desired
            or sha(cold['phase-summary.json']) != cycle['phase_summary_sha256']
            or sha(cold['raw/manifest.json']) != cycle['raw_manifest_sha256']):
        raise ValueError('Awake observation/failed phase qualification changed')
    raw_manifest = json.loads(cold['raw/manifest.json'])
    if sha(cold['raw/chunks.jsonl']) != raw_manifest['chunks_sha256']:
        raise ValueError('Native sample metadata changed')
    for name, info in raw_manifest['files'].items():
        omitted = index['records']['awake-cycle01']['omitted']['raw/' + info['path']]
        if omitted['sha256'] != info['sha256'] or omitted['bytes'] != info['bytes']:
            raise ValueError('Omitted raw waveform identity differs')
    inspection = records['awake-inspect02']
    verified = json.loads(inspection['verified.json'])
    fresh = json.loads(inspection['fresh-boot.json'])
    if (fresh['binary_sha256'] != verified['binary_sha256'] or fresh['sector_sha256'] != desired
            or fresh['cold_boot_confirmed'] is not True or verified['sector_sha256'] != desired
            or fresh['evidence'][0]['sha256'] != sha(cold['result.json'])):
        raise ValueError('Cold inspection freshness binding differs')
    report = json.loads(inspection['readback-comparison.json'])
    retrieval = records['read-scene-slot0']
    read_result = json.loads(retrieval['verified.json'])
    omitted_frame = index['records']['awake-inspect02']['omitted']['frame.bin']
    volume = fmt.parse_volume(retrieval['volume.bin'])
    slot = fmt.parse_slot(retrieval['header.bin'], volume, 0)
    if (not report['passed'] or not report['exact_camera_byte_comparison']
            or not report['padding_zero'] or report['bytes'] != FRAME_BYTES
            or report['payload_sha256'] != verified['frame_sha256']
            or report['payload_sha256'] != read_result['payload_sha256']
            or report['payload_sha256'] != omitted_frame['sha256'] or slot['state'] != 'FULL'):
        raise ValueError('Historical scene comparison/hashes differ')
    # Pixels are intentionally omitted, so this remains a historical equality
    # report with matching identities, not a new replay of scene pixel values.
    profile = records['awake-profile01']
    fields = json.loads(profile['profile.json'])
    actual = struct.unpack('<32I', profile['profile.bin'])
    if tuple(fields.values()) != actual[:len(fields)] or fields['CP_STATE'] != 2 or fields['CP_ERRORS']:
        raise ValueError('Cold post-frame profile differs')
    failed = json.loads(records['wfi-failure-diagnostic02']['result.json'])
    fp = failed['proof']
    plan = json.loads(records['wfi-pattern01']['plan.json'])
    _, fm, fcode = builds[plan['binary_sha256']]
    diag = records['wfi-failure-diagnostic02']
    if diag['proof.bin'] != struct.pack('<96I', *fp.values()) or diag['code.bin'] != fcode[:fm['immutable_bytes']]:
        raise ValueError('WFI failure identity differs')
    abort = struct.unpack('<16I', diag['abort.bin'])
    if (fp['state'] != 15 or fp['result'] != 0x332 or fp['sd_error'] != 21
            or fp['written_sectors'] != 1024 or fp['commit_done'] or fp['payload_done']
            or fp['initialized'] or fp['controller_owned'] or fp['media_idle'] != 1
            or fp['cleanup_error'] or tuple(failed['abort']) != abort
            or abort[:3] != (0x43414231, 1, 2) or abort[3] != fp['result']
            or abort[6] or abort[15] or abort[10] & 68 != 68
            or abort[12] & 32 or abort[13] & 32):
        raise ValueError('Failed WFI/observed reset evidence changed')
    return dict(installed_sector_sha256=desired, full_nor_readback=True,
        following_4096_bytes_unchanged=True, cold_awake_terminal_inspected=True,
        strict_phase_decode_passed=False, actual_standby_verified=False,
        historical_scene_readback_reported_exact=True, scene_pixels_replayed=False,
        scene_payload_sha256=report['payload_sha256'],
        failed_wfi_preserved=True, failed_wfi_sd_error=21,
        failed_wfi_written_sectors=1024, failure_camera_reset_observed=True,
        failure_sd_idle_deinitialized=True)


def replay_wfi_abort_and_install(index, records, builds):
    if 'wfi-pattern02' not in records:
        return None
    failed = records['wfi-pattern02']
    plan = json.loads(failed['plan.json'])
    name, m, code = builds[plan['binary_sha256']]
    if (name != 'ram-line-wfi-v14b' or not m['dma_sleep'] or m['flash']
            or 'verified.json' in failed
            or failed['bootstrap/executable-readback.bin'] != code):
        raise ValueError('Failed WFI v14b identity/completion classification differs')
    interruption = json.loads(failed['intervention.json'])
    if (interruption['storage_idle_proven'] is not False
            or not interruption['no_idle_claim'] or not interruption['authorization']):
        raise ValueError('Unknown-storage intervention authorization changed')
    if b'CLI call 18 failed' not in failed['attachments/wfi-pattern02-output.txt']:
        raise ValueError('Original WFI host failure is missing')
    for name in ('wfi-pattern02-observe01', 'early-park09'):
        if b'Cannot connect to access port 1' not in records[name]['cli-01.log']:
            raise ValueError('Failed access/reset evidence changed')
    signals = json.loads(records['recovery-vcp09']['signal-summary.json'])
    reset_lows = [r for r in signals['digital_intervals']['Channel 0'] if r['level'] == 0]
    if len(reset_lows) != 1 or reset_lows[0]['end_s'] <= reset_lows[0]['start_s']:
        raise ValueError('Observed reset pulse missing')
    abort = records['wfi-abort-cold-recovery01']
    events = [json.loads(line) for line in abort['cycle.jsonl'].splitlines()]
    authorization = [e for e in events if e['event'] == 'intentional_failed_trial_abort']
    if (len(authorization) != 1 or authorization[0]['storage_idle_proven'] is not False
            or not authorization[0]['authorization']):
        raise ValueError('Cold abort must retain explicit non-idle authorization')
    stops = [e for e in events if e['event'] == 'command_stop']
    if (len(stops) != 1 or not stops[0]['response']['ok']
            or stops[0]['response']['range'] != 128
            or stops[0]['response']['starting_range'] != 128
            or stops[0]['response']['restore_error'] is not None):
        raise ValueError('Helper cleanup restoration evidence changed')
    inspection = records['abort-restored-inspect01']
    verified = json.loads(inspection['verified.json'])
    fresh = json.loads(inspection['fresh-boot.json'])
    p = verified['proof']
    if (p['slot'] != 3 or p['operation'] != 1 or p['formatted_slots']
            or not fresh['cold_boot_confirmed']
            or fresh['binary_sha256'] != verified['binary_sha256']
            or fresh['sector_sha256'] != verified['sector_sha256']
            or fresh['evidence'][0]['sha256'] != sha(abort['session.jsonl'])
            or fresh['evidence'][1]['sha256'] != sha(records['wfi-abort-restored-observe01']['proof.json'])):
        raise ValueError('Restored v9 capture binding differs')
    full = json.loads(records['format-full01']['verified.json'])['proof']
    if any(p[k] != full[k] for k in ('generation_lo', 'generation_hi', 'slot_count')):
        raise ValueError('Restored capture uses a different volume generation')
    install = records['flash-standby-write01']
    request = json.loads(install['request.json'])
    installed = json.loads(install['verified.json'])
    b = index['builds']['flash-standby-line-v12']
    sector = read_object(b['files']['staged/capture_sector_0.bin'])
    sm = json.loads(read_object(b['files']['manifest.json']))
    if (not sm['standby'] or sm['dma_sleep'] or not sm['flash']
            or not installed['byte_for_byte_match']
            or sha(sector) != request['desired_sha256']
            or installed['sha256'] != request['desired_sha256']
            or install['readback.bin'] != sector
            or request['current_sha256'] != verified['sector_sha256']
            or sha(records['nor-before02']['nor.bin']) != request['current_sha256']):
        raise ValueError('Polling Standby v12 installation differs')
    guard = records['nor-following-after02']['nor.bin']
    if len(guard) != 4096 or guard != records['nor-following-before01']['nor.bin']:
        raise ValueError('v12 following NOR guard changed')
    completion = json.loads(records['flash-standby-write01-diagnostic']['result.json'])
    if completion['pending_operations'] or completion['first_failure_result'] or completion['last_status'] & 3:
        raise ValueError('v12 NOR helper was not idle')
    return dict(failed_wfi_build_sha256=plan['binary_sha256'], wfi_completion_proven=False,
        reset_did_not_recover=True, cold_abort_storage_idle_proven=False,
        explicit_abort_authorization_preserved=True, helper_restored_range=128,
        restored_v9_slot=3, restored_v9_capture_terminal_verified=True,
        same_volume_generation=True, interrupted_slot_contents_verified=False,
        standby_install_sector_sha256=request['desired_sha256'],
        standby_install_full_readback=True, following_4096_bytes_unchanged=True,
        standby_mode_from_build=True, actual_standby_qualified_here=False)


def replay_standby_cycles(index, records):
    if 'standby-three-cycle-analysis' not in records:
        return None
    build = file_bytes(index['builds']['flash-standby-line-v12'])
    pm = json.loads(build['staged/manifest.json'])
    m = json.loads(build['manifest.json'])
    prefix = build['staged/stage1.bin']
    prefix_sha = sha(prefix)
    sector_sha = sha(build['staged/capture_sector_0.bin'])
    report = records['standby-three-cycle-analysis']
    manifest = json.loads(report['manifest.json'])
    for name, expected in manifest['files'].items():
        if sha(report[name]) != expected:
            raise ValueError('Standby analysis file changed: ' + name)
    summary = json.loads(report['summary.json'])
    if (sha(report['attachments/spec.json']) != manifest['spec_sha256']
            or sha(report['attachments/baseline-summary.json']) != summary['v66c_baseline_sha256']
            or index['tools']['cycle_energy.py']['sha256'] != summary['energy_analyzer_sha256']
            or summary['sector_sha256'] != sector_sha or summary['prefix_sha256'] != prefix_sha):
        raise ValueError('Standby analysis source identities differ')
    phases = []
    energies = []
    durations = []
    for number in range(1, 4):
        name = f'standby-cycle{number:02d}'
        tag = f'standby{number:02d}'
        files = records[name]
        r = json.loads(files['result.json'])
        q = json.loads(files['attachments/qualification.json'])
        phase = json.loads(files['phase-summary.json'])
        if (not r['recording_complete'] or r['expected_end'] != 'standby'
                or r['sector_sha256'] != sector_sha
                or sha(files['raw/manifest.json']) != r['raw_manifest_sha256']
                or sha(files['phase-summary.json']) != r['phase_summary_sha256']
                or sha(files['safe-start-proof.json']) != r['safe_start_proof_sha256']):
            raise ValueError('Standby recording identity differs')
        raw = json.loads(files['raw/manifest.json'])
        if not raw['finalized'] or not raw['status']['complete'] or not raw['status']['coverage']['passed']:
            raise ValueError('Standby raw recording incomplete')
        if sha(files['raw/chunks.jsonl']) != raw['chunks_sha256']:
            raise ValueError('Standby native sample metadata differs')
        for info in raw['files'].values():
            omitted = index['records'][name]['omitted']['raw/' + info['path']]
            if (omitted['sha256'], omitted['bytes']) != (info['sha256'], info['bytes']):
                raise ValueError('Standby omitted waveform identity differs')
        parkfiles = records[tag+'-park']
        park = json.loads(parkfiles['result.json'])
        sf = records[tag+'-sbf']
        sbf = json.loads(sf['result.json'])
        if (q['schema'] != 1 or q['bench_owner'] != 'root' or q['cycle'] != name
                or q['sector_sha256'] != sector_sha
                or q['recording_result_sha256'] != sha(files['result.json'])
                or q['owner_attests_no_intervening_poweroff'] is not True
                or q['owner_attests_sbf_cleared_before_cycle'] is not True
                or not q['owner_attestation']
                or q['sbf_evidence']['sha256'] != sha(sf['result.json'])):
            raise ValueError('Standby owner attribution missing or mismatched')
        if (not park['passed'] or park['prefix_sha256'] != prefix_sha
                or parkfiles['live-prefix.bin'] != prefix
                or parkfiles['recovery-status.bin'] != struct.pack('<24I', *park['status'].values())
                or parkfiles['vcp-status.bin'] != struct.pack('<32I', *park['vcp_status'].values())
                or park['context']['PC'] != int(pm['recovery_gpio']['park_address'], 0)
                or park['context']['CONTROL'] or park['context']['PRIMASK'] != 1
                or park['ccr'] & ((1 << 16) | (1 << 17)) or park['xspi_sr'] & 32
                or park['vcp_status']['request'] != 1 or park['vcp_status']['bad_pulses']):
            raise ValueError('Standby exact warm recovery park differs')
        if (not sbf['passed'] or not sbf['sbf'] or sbf['cpucr'] & 512 == 0
                or sbf['prefix_sha256'] != prefix_sha or sbf['cpucr_written']
                or sbf['reset_or_power_changed'] or sbf['ram_writes'] or sbf['nor_commands']
                or sbf['prior_park_result_sha256'] != sha(parkfiles['result.json'])
                or sbf['fresh_park_result'] != park
                or sf['registers/before-prefix.bin'] != prefix
                or sf['registers/pwr-cpucr.bin'] != struct.pack('<I', sbf['cpucr'])
                or sbf['guard_before'] != sbf['guard_after']):
            raise ValueError('Standby read-only SBF observation differs')
        # Decode native transition bytes directly. The final over-width pulse
        # must remain unknown; ordering is never used to repair its identity.
        signal = files['phase/binary/digital_1.bin']
        magic, version, kind, initial, begin, end, count = struct.unpack_from('<8siiIddQ', signal)
        if (magic != b'<SALEAE>' or version or kind or initial or len(signal) != 44+8*count
                or count != 20):
            raise ValueError('Unexpected Standby marker digital geometry')
        edges = struct.unpack_from('<'+'d'*count, signal, 44)
        if not all(math.isfinite(t) and begin <= t <= end for t in edges) or any(a >= b for a,b in zip(edges, edges[1:])):
            raise ValueError('Standby marker transitions invalid')
        protocol = m['phase_markers']
        step = protocol['nominal_high_us_per_id']*1e-6
        tol = protocol['pulse_width_tolerance_us']*1e-6
        decoded = []
        for i, (a,b) in enumerate(zip(edges[::2], edges[1::2])):
            width = b-a
            candidate = math.floor(width/step + .5)
            ident = candidate if 1 <= candidate <= 10 and abs(width-candidate*step) <= tol+1e-15 else None
            saved = phase['pulses'][i]
            if (saved['event_id'] != ident or saved['start_s'] != a
                    or saved['end_s'] != b or saved['width_s'] != width):
                raise ValueError('Standby phase decode differs from binary')
            decoded.append(ident)
        if (phase['decode_passed'] or r['phase_decode_passed']
                or decoded != [1,2,4,3,5,6,7,8,9,None]):
            raise ValueError('Failed final marker must remain unknown')
        item = summary['cycles'][number-1]
        energy = json.loads(report[name+'/energy.json'])
        context = json.loads(report[name+'/context.json'])
        if (item['name'] != name or not item['terminal_state_qualified']
                or not energy['terminal_state_qualified']
                or item['qualification_sha256'] != sha(files['attachments/qualification.json'])
                or item['sbf_evidence_sha256'] != sha(sf['result.json'])
                or energy['terminal_evidence_sha256'] != sha(report[name+'/context.json'])
                or context['recording_result_sha256'] != sha(files['result.json'])
                or energy['criteria'] != summary['same_boundary_criteria']
                or energy['criteria']['current_valid_abs_max_a'] != 9.5
                or energy['peak_current_a'] != item['peak_current_a']):
            raise ValueError('Standby energy report bindings differ')
        if (energy['onset_to_plateau_s'] != item['onset_to_plateau_s']
                or energy['onset_to_plateau_energy_j'] != item['onset_to_plateau_energy_j']
                or energy['plateau_confirmation_energy_j'] != item['plateau_confirmation_energy_j']):
            raise ValueError('Standby energy summary differs')
        boundary = energy['boundaries']
        duration = (boundary['terminal_plateau_start_sample_id']-boundary['current_onset_sample_id'])*boundary['sample_interval_s']
        if not math.isclose(duration, item['onset_to_plateau_s'], rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError('Standby native sample duration differs')
        energies.append(item['onset_to_plateau_energy_j'])
        durations.append(duration)
        phases.append(dict(cycle=name, sbf=True, owner_attribution_preserved=True,
                           exact_warm_recovery=True, directly_decoded_events=decoded[:-1],
                           final_marker_unknown=True))
    for key, values in (('energy_j', energies), ('current_onset_to_plateau_s', durations)):
        expected = dict(n=len(values), median=statistics.median(values), minimum=min(values), maximum=max(values))
        if any(not math.isclose(summary[key][k], v, rel_tol=1e-12, abs_tol=1e-12) for k,v in expected.items()):
            raise ValueError('Standby aggregate differs')
    return dict(cycles=phases, actual_standby_qualified=True,
        image_integrity_qualification_separate=True,
        median_reported_energy_j=statistics.median(energies),
        median_current_onset_to_plateau_s=statistics.median(durations),
        signed_raw_integral_report_preserved=True, native_sample_energy_reintegrated_here=False,
        unchanged_current_validity_limit_a=9.5, startup_samples_removed=False,
        isolated_battery_energy=False)


def replay_compacts(records, compact_name='standby-three-cycle-compacts',
                    analysis_name='standby-three-cycle-analysis'):
    if compact_name not in records:
        return None
    files = records[compact_name]
    analysis = records[analysis_name]
    manifest = json.loads(files['manifest.json'])
    if manifest['source_analysis_manifest_sha256'] != sha(analysis['manifest.json']):
        raise ValueError('Compact source analysis changed')
    for name, digest in manifest['files'].items():
        if sha(files[name]) != digest:
            raise ValueError('Compact file identity changed: ' + name)
    if files['summary.json'] != analysis['summary.json']:
        raise ValueError('Compact summary differs')
    segments = (
        ('pretrigger_energy_j','integration_start_sample_id','current_onset_sample_id'),
        ('onset_to_plateau_energy_j','current_onset_sample_id','terminal_plateau_start_sample_id'),
        ('plateau_confirmation_energy_j','terminal_plateau_start_sample_id','integration_end_sample_id'),
        ('pretrigger_through_confirmed_plateau_energy_j','integration_start_sample_id','integration_end_sample_id'))
    count = 0
    names = [r['name'] for r in json.loads(files['summary.json'])['cycles']]
    if not names or len(set(names)) != len(names):
        raise ValueError('Invalid compact cycle names')
    for name in names:
        wrapped = json.loads(files[name+'/analysis.json'])
        compact = json.loads(gzip.decompress(files[name+'/power-compact.json.gz']))
        cycle, = wrapped['cycles']
        raw = json.loads(files[name+'/raw-manifest.json'])
        if (cycle != json.loads(analysis[name+'/energy.json'])
                or compact['analysis_sha256'] != sha(files[name+'/analysis.json'])
                or compact['raw_manifest_sha256'] != sha(files[name+'/raw-manifest.json'])
                or compact['raw_files'] != raw['files']
                or compact['raw_chunks_sha256'] != raw['chunks_sha256']
                or files[name+'/raw-manifest.json'] != records[name]['raw/manifest.json']
                or gzip.decompress(files[name+'/raw-chunks.jsonl.gz']) != records[name]['raw/chunks.jsonl']
                or compact['cycle_analysis'] != cycle
                or sha(files[name+'/context.json']) != cycle['terminal_evidence_sha256']
                or compact['sample_rate_hz'] != 2000000 or compact['decimate_factor'] != 1):
            raise ValueError('Compact native sample/source binding differs')
        rows, bounds = compact['rows'], compact['boundaries']
        if (not rows or any(len(r) != 12 or r[2] != r[1]-r[0] or r[2] <= 0
                or not all(math.isfinite(v) for v in r) for r in rows)
                or any(a[1] != b[0] for a,b in zip(rows,rows[1:]))):
            raise ValueError('Compact row geometry/coverage differs')
        for key, a, b in segments:
            chosen = [r for r in rows if bounds[a] <= r[0] and r[1] <= bounds[b]]
            if not chosen or chosen[0][0] != bounds[a] or chosen[-1][1] != bounds[b]:
                raise ValueError('Compact integral boundary does not coincide with bins')
            integral = math.fsum(r[9] for r in chosen)/compact['sample_rate_hz']
            if (not math.isclose(integral, cycle[key], rel_tol=1e-12, abs_tol=1e-12)
                    or not math.isclose(integral, compact['exact_segment_integrals_j'][key], rel_tol=1e-12, abs_tol=1e-12)):
                raise ValueError('Compact signed integral differs: '+key)
            count += 1
    return dict(passed=True, cycles=len(names), energy_intervals_replayed=count,
                exact_native_sample_sum_bins=True, raw_boundary_classification_replayed=False)


def replay_final_storage(index, records, fmt):
    if 'final-headers01' not in records:
        return None
    headers = records['final-headers01']
    summary = json.loads(headers['summary.json'])
    slot6 = records['read-standby-slot6']
    volume = fmt.parse_volume(slot6['volume.bin'])
    if volume != summary['volume']:
        raise ValueError('Final volume differs')
    actual = [fmt.parse_slot(headers[f'slot{n}/operation/sectors.bin'], volume, n) for n in range(8)]
    states = [s['state'] for s in actual]
    if actual != summary['slots'] or states != ['FULL','PARTIAL','PARTIAL','FULL','FULL','FULL','FULL','FREE']:
        raise ValueError('Final allocation states differ')
    if fmt.parse_slot(slot6['header.bin'], volume, 6) != actual[6]:
        raise ValueError('Slot6 readback header differs')
    report = json.loads(slot6['readback-validation.json'])
    verified = json.loads(slot6['verified.json'])
    omitted = index['records']['read-standby-slot6']['omitted']['frame.bin']
    if (not report['passed'] or not report['full_payload_read']
            or not report['header_crcs_valid'] or not report['padding_zero']
            or not report['png_samples_match_read_raw'] or report['original_sensor_frame_comparison']
            or report['bytes'] != FRAME_BYTES or omitted['bytes'] != FRAME_BYTES
            or report['raw_sha256'] != omitted['sha256']
            or report['raw_sha256'] != verified['payload_sha256']
            or report['png_sha256'] != index['records']['read-standby-slot6']['omitted']['scene.png']['sha256']):
        raise ValueError('Historical slot6 full-read/decode evidence differs')
    old = records['reread-scene-slot0']
    preserved = json.loads(old['preservation-comparison.json'])
    first = json.loads(records['awake-inspect02']['readback-comparison.json'])
    if (not preserved['passed'] or not preserved['exact_camera_byte_comparison']
            or not preserved['header_crcs_valid'] or not preserved['padding_zero']
            or preserved['payload_sha256'] != first['payload_sha256']
            or preserved['payload_sha256'] != index['records']['reread-scene-slot0']['omitted']['frame.bin']['sha256']
            or preserved['payload_sha256'] != json.loads(old['verified.json'])['payload_sha256']
            or fmt.parse_slot(old['header.bin'], volume, 0) != actual[0]):
        raise ValueError('Historical original-image preservation differs')
    return dict(final_slot_states=states, header_crcs_replayed=True,
        slot6_full_read_and_png_decode_report_verified=True,
        slot6_original_sensor_frame_comparison=False, scene_pixels_replayed=False,
        original_slot0_preservation_report_verified=True,
        original_slot0_sha256=preserved['payload_sha256'], power_loss_protection_qualified=False)


def replay_final_state(index, records, record_name='standby-cycle04',
                       expected_slot=7, qualified_prior=3):
    if record_name not in records:
        return None
    files = records[record_name]
    final = json.loads(files['attachments/final-state.json'])
    result = json.loads(files['result.json'])
    response = json.loads(files['response.json'])
    if (final['schema'] != 1 or final['bench_owner'] != 'root'
            or final['target_power'] != 'on' or final['js_range'] != 128
            or final['active_bench_helpers'] or final['dma_sleep']
            or final['final_cycle_slot_read'] or final['final_cycle_sbf_read']
            or final['final_cycle_expected_slot'] != expected_slot or final['qualified_prior_cycles'] != qualified_prior
            or result['terminal_state_qualified'] or result['image_integrity_verified']
            or not result['recording_complete'] or result['sector_sha256'] != final['sector_sha256']
            or sha(files['phase-summary.json']) != result['phase_summary_sha256']
            or sha(files['safe-start-proof.json']) != result['safe_start_proof_sha256']
            or sha(files['raw/manifest.json']) != result['raw_manifest_sha256']):
        raise ValueError('Final signature-only state changed')
    raw = json.loads(files['raw/manifest.json'])
    if sha(files['raw/chunks.jsonl']) != raw['chunks_sha256']:
        raise ValueError('Final recording native metadata changed')
    for info in raw['files'].values():
        omitted = index['records'][record_name]['omitted']['raw/'+info['path']]
        if (omitted['sha256'],omitted['bytes']) != (info['sha256'],info['bytes']):
            raise ValueError('Final omitted waveform differs')
    if (response['event'] != 'stopped' or not response['ok'] or response['restore_error'] is not None
            or response['range'] != 128 or response['statistics']['current']['avg'] != final['current_a']
            or response['statistics']['voltage']['avg'] != final['input_voltage_v']):
        raise ValueError('Final helper cleanup/measurement differs')
    for evidence in final['evidence']:
        path = evidence['path'].replace('\\','/')
        matching = []
        for name, selected in index['records'].items():
            for rel, artifact in selected['files'].items():
                if path.endswith('/'+selected['source']+'/'+rel):
                    matching.append(artifact)
        for selected in index['selection']['records']:
            for name, source in selected.get('attachments', {}).items():
                if path.endswith('/'+source.replace('\\','/')):
                    matching.append(index['records'][selected['id']]['files']['attachments/'+name])
        if len(matching) != 1 or matching[0]['sha256'] != evidence['sha256']:
            raise ValueError('Final state evidence binding differs: '+path)
    return dict(utc=final['utc'],sector_sha256=final['sector_sha256'],
        target_power='on',js_range=128,active_helpers=False,
        input_voltage_v=final['input_voltage_v'],current_a=final['current_a'],
        final_cycle_signature_only=True,final_cycle_sbf_verified=False,
        final_slot_expected=expected_slot,final_slot_readback_verified=False)


def replay_v15(index, records, fmt):
    if 'v15-install' not in records:
        return None
    build = file_bytes(index['builds']['flash-standby-line-v15'])
    old = file_bytes(index['builds']['flash-standby-line-v12'])
    m = json.loads(build['manifest.json'])
    pm = json.loads(build['staged/manifest.json'])
    review = json.loads(build['offline-review.json'])
    installation = records['v15-install']
    request = json.loads(installation['request.json'])
    verified = json.loads(installation['verified.json'])
    sector = build['staged/capture_sector_0.bin']
    prefix = build['staged/stage1.bin']
    if (not m['standby'] or not m['flash'] or m['dma_sleep']
            or installation['readback.bin'] != sector or not verified['byte_for_byte_match']
            or sha(sector) != pm['program_sha256'] or sha(sector) != request['desired_sha256']
            or verified['sha256'] != sha(sector)
            or request['current_sha256'] != sha(old['staged/capture_sector_0.bin'])):
        raise ValueError('Corrected v15 install differs')
    guard = records['v15-following-after']['following-sector.bin']
    if len(guard) != 4096 or guard != records['nor-following-after02']['nor.bin']:
        raise ValueError('v15 following NOR guard changed')
    done = json.loads(records['v15-install-diagnostic']['result.json'])
    if done['pending_operations'] or done['first_failure_result'] or done['last_status'] & 3:
        raise ValueError('v15 NOR helper not idle')
    if (review['hardware_access'] or review['hardware_qualified']
            or review['sector_sha256'] != sha(sector)
            or review['prefix_sha256'] != sha(prefix)
            or review['receiver_sha256'] != m['binary_sha256']
            or not review['recovery_unchanged']):
        raise ValueError('v15 offline review scope/identity differs')
    old_prefix = old['staged/stage1.bin']
    changed = [hex(n) for n,(a,b) in enumerate(zip(old_prefix,prefix)) if a != b]
    if len(old_prefix) != len(prefix) or changed != review['prefix_changed_offsets']:
        raise ValueError('v15 documented prefix difference changed')
    result = dict(selected_build='flash-standby-line-v15',sector_sha256=sha(sector),
        prefix_sha256=sha(prefix),full_nor_readback=True,
        following_4096_bytes_unchanged=True,offline_review_preserved=True,
        v12_energy_metrics_reassigned=False)
    if 'v15-cycle01' not in records:
        return result
    files = records['v15-cycle01']
    cycle = json.loads(files['result.json'])
    q = json.loads(files['attachments/qualification.json'])
    sf = records['v15-sbf01']
    sbf = json.loads(sf['result.json'])
    pf = records['v15-park01']
    park = json.loads(pf['result.json'])
    if (not cycle['recording_complete'] or cycle['sector_sha256'] != sha(sector)
            or sha(files['phase-summary.json']) != cycle['phase_summary_sha256']
            or sha(files['raw/manifest.json']) != cycle['raw_manifest_sha256']
            or sha(files['safe-start-proof.json']) != cycle['safe_start_proof_sha256']
            or q['recording_result_sha256'] != sha(files['result.json'])
            or q['sector_sha256'] != sha(sector) or q['cycle'] != 'v15-cycle01'
            or q['bench_owner'] != 'root' or not q['owner_attests_no_intervening_poweroff']
            or not q['owner_attests_sbf_cleared_before_cycle'] or not q['owner_attestation']
            or q['sbf_evidence']['sha256'] != sha(sf['result.json'])):
        raise ValueError('v15 cold cycle/SBF attribution differs')
    raw = json.loads(files['raw/manifest.json'])
    if sha(files['raw/chunks.jsonl']) != raw['chunks_sha256']:
        raise ValueError('v15 native sample metadata changed')
    for info in raw['files'].values():
        omitted = index['records']['v15-cycle01']['omitted']['raw/'+info['path']]
        if (omitted['sha256'],omitted['bytes']) != (info['sha256'],info['bytes']):
            raise ValueError('v15 omitted waveform identity differs')
    if (not park['passed'] or park['prefix_sha256'] != sha(prefix)
            or pf['live-prefix.bin'] != prefix or sf['registers/before-prefix.bin'] != prefix
            or pf['recovery-status.bin'] != struct.pack('<24I',*park['status'].values())
            or pf['vcp-status.bin'] != struct.pack('<32I',*park['vcp_status'].values())
            or park['context']['PC'] != int(pm['recovery_gpio']['park_address'],0)
            or not sbf['passed'] or not sbf['sbf'] or sbf['cpucr'] & 512 == 0
            or sbf['cpucr_written'] or sbf['reset_or_power_changed']
            or sbf['fresh_park_result'] != park
            or sbf['prior_park_result_sha256'] != sha(pf['result.json'])
            or sf['registers/pwr-cpucr.bin'] != struct.pack('<I',sbf['cpucr'])):
        raise ValueError('v15 exact recovery/SBF bytes differ')
    image = records['v15-read-slot8b']
    report = json.loads(image['readback-validation.json'])
    volume = fmt.parse_volume(image['volume.bin'])
    header = fmt.parse_slot(image['header.bin'],volume,8)
    if (not report['passed'] or report['header'] != header or header['state'] != 'FULL'
            or not report['full_payload_read'] or not report['padding_zero']
            or not report['png_samples_match_read_raw'] or report['original_sensor_frame_comparison']
            or report['bytes'] != FRAME_BYTES
            or report['raw_sha256'] != json.loads(image['verified.json'])['payload_sha256']
            or report['raw_sha256'] != index['records']['v15-read-slot8b']['omitted']['frame.bin']['sha256']
            or report['png_sha256'] != index['records']['v15-read-slot8b']['omitted']['scene.png']['sha256']
            or q['image_evidence']['sha256'] != sha(image['readback-validation.json'])):
        raise ValueError('v15 historical image read/decode binding differs')
    analysis = records.get('v15-smoke-analysis')
    if analysis:
        manifest = json.loads(analysis['manifest.json'])
        for name,digest in manifest['files'].items():
            if sha(analysis[name]) != digest:
                raise ValueError('v15 analysis artifact differs')
        normalized = json.loads(files['attachments/qualification-analysis.json'])
        if (normalized['normalized_from_sha256'] != sha(files['attachments/qualification.json'])
                or not normalized['owner_attests_complete_slot_readback'] or normalized['slot'] != 8):
            raise ValueError('v15 normalized qualification differs')
        summary = json.loads(analysis['summary.json'])
        item, = summary['cycles']
        if (item['name'] != 'v15-cycle01' or summary['sector_sha256'] != sha(sector)
                or item['qualification_sha256'] != sha(files['attachments/qualification-analysis.json'])
                or not item['terminal_state_qualified'] or not item['image_integrity_verified']):
            raise ValueError('v15 single smoke analysis binding differs')
        result.update(smoke_runs=1,onset_to_plateau_s=item['onset_to_plateau_s'],
                      onset_to_plateau_energy_j=item['onset_to_plateau_energy_j'])
    result.update(sbf_qualified=True,exact_warm_recovery=True,
        slot8_full_read_and_png_decode_report_verified=True,
        original_sensor_frame_comparison=False,scene_pixels_replayed=False)
    return result


def run():
    index = json.loads((HERE / 'index.json').read_bytes())
    if index['schema'] != 1 or index['line_ending_normalization']:
        raise ValueError('Unknown archive schema')
    builds = verify_builds(index)
    records = {name: file_bytes(record) for name, record in index['records'].items()}
    for item in index['tools'].values():
        read_object(item)
    fmt = load_tool(index, 'raw_slots.py')
    scalar = load_tool(index, 'verify_decode.py')
    producer = load_tool(index, 'verify_producer.py')
    scalar.self_test()
    reference = read_object(index['native16_reference'])
    if len(reference) != 3055360:
        raise ValueError('Native16 pattern geometry differs')
    terminals = []
    comparisons = []
    preserved_failures = []
    line = None
    for name, files in records.items():
        selected = index['records'][name]
        for rel, raw in files.items():
            if not rel.endswith('verified.json'):
                continue
            verified = json.loads(raw)
            if verified.get('proof', {}).get('magic') != 0x52535731:
                continue
            prefix = rel[:-len('verified.json')]
            terminals.append(dict(record=name, path=rel, **terminal_proof(verified, files, prefix, builds)))
        if selected['pixels'] != 'pattern':
            for k, raw in files.items():
                if k.rsplit('/', 1)[-1] in ('frame.bin', 'payload-padded.bin', 'snapshots.bin', 'sectors.bin'):
                    if (k not in selected.get('metadata_sectors', []) or len(raw) != 512
                            or raw[:8] not in (b'GXRAWSL1',b'GXRWVOL1')
                            or zlib.crc32(raw[:508]) != int.from_bytes(raw[508:], 'little')):
                        raise ValueError('Unspecified/scene pixel payload included')
            continue
        if selected.get('capture'):
            capture_name = selected['capture']
            camera_files = records[capture_name]
            v = json.loads(camera_files['verified.json'])
            expected = camera_files['frame.bin']
            if sha(expected) != v['frame_sha256'] or len(expected) != FRAME_BYTES:
                raise ValueError('Camera pattern identity differs')
            if scalar.decode_scalar(expected) != reference:
                raise ValueError('Camera pattern does not match independent native16 reference')
            volume = fmt.parse_volume(files['volume.bin'])
            slot = fmt.parse_slot(files['header.bin'], volume, v['proof']['slot'])
            if slot['state'] != 'FULL':
                raise ValueError('Expected FULL slot')
            raw = files['payload-padded.bin']
            if len(raw) != 3730*512 or raw[FRAME_BYTES:] != bytes(160):
                raise ValueError('Payload/tail length or padding differs')
            chunks = []
            for rel in sorted(k for k in files if k.startswith('payload-') and k.endswith('/operation/sectors.bin')):
                chunks.append(files[rel])
            if b''.join(chunks) != raw:
                raise ValueError('SD payload does not match its read transactions')
            if files['header/operation/sectors.bin'] != files['header.bin'] or files['volume/operation/sectors.bin'] != files['volume.bin']:
                raise ValueError('Header does not match read transaction')
            compared = raw[:FRAME_BYTES]
            mismatch = sum(a != b for a, b in zip(compared, expected))
            if capture_name == 'idma-pattern01':
                failure = json.loads(camera_files['readback-failure.json'])
                if not mismatch or any(compared) or failure['passed'] or mismatch != failure['mismatched_bytes']:
                    raise ValueError('Historical zero-payload failure changed')
                if sha(compared) != failure['sd_sha256'] or sha(expected) != failure['camera_sha256']:
                    raise ValueError('Failure payload hashes differ')
                preserved_failures.append(dict(record=capture_name, mismatched_bytes=mismatch,
                    all_sd_payload_zero=True, controller_reported_success=True))
            else:
                report = json.loads(camera_files['readback-comparison.json'])
                if mismatch or not report['passed'] or sha(compared) != report['payload_sha256']:
                    raise ValueError('Qualified payload comparison changed')
                comparisons.append(dict(capture=capture_name, readback=name, slot=slot['index'],
                    bytes=FRAME_BYTES, pixels=1527680, exact=True, sha256=sha(compared)))
                if capture_name == 'line-pattern01':
                    line = producer.verify(camera_files['producer.bin'], camera_files['snapshots.bin'],
                        expected, camera_files['chunks.bin'], v['proof'])
                    if line != json.loads(camera_files['producer-comparison.json']):
                        raise ValueError('LINE qualification report differs')
    rif = json.loads(records['rif-port-diagnostic01']['result.json'])
    if any(rif[key] for key in ('seccfgr1', 'privcfgr1', 'lockcfgr1')):
        raise ValueError('Historical nonsecure SDMMC2-port evidence differs')
    if 'verified.json' in records['format128-01']:
        raise ValueError('Refused initial format was promoted to success')
    full = json.loads(records['format-full01']['verified.json'])['proof']
    if full['slot_count'] != 32834:
        raise ValueError('Historical all-capacity slot count differs')
    cold = replay_cold_and_failure(index, records, builds, fmt)
    abort = replay_wfi_abort_and_install(index, records, builds)
    standby = replay_standby_cycles(index, records)
    compacts = replay_compacts(records)
    final_storage = replay_final_storage(index, records, fmt)
    final_state = replay_final_state(index, records)
    v15 = replay_v15(index, records, fmt)
    v15_compacts = replay_compacts(records,'v15-smoke-compacts','v15-smoke-analysis')
    v15_final = replay_final_state(index,records,'v15-cycle02-final',9,1)
    return dict(passed=True, source_builds_verified=len(builds), records_verified=len(records),
        terminal_proofs_verified=len(terminals), completed_slot_comparisons=comparisons,
        preserved_payload_failures=preserved_failures, initial_format_refusal_preserved=True,
        full_format_slots=full['slot_count'], scalar_vectors=4096,
        line_overlap_qualified=bool(line and line['overlap_observed']),
        line_immediate_snapshot_bytes=line['exact_snapshot_bytes'] if line else 0,
        no_scene_pixels=True, hardware_access=False, cold_awake_and_wfi_failure=cold,
        failed_wfi_abort_and_standby_install=abort,
        standby_cycles=standby,
        compact_energy=compacts, final_storage=final_storage,
        final_bench_state=final_state,
        corrected_v15=v15,
        corrected_v15_energy=v15_compacts,
        corrected_v15_final_state=v15_final,
        limits=index['limits'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    result = run()
    raw = json.dumps(result, indent=2) + '\n'
    if args.out:
        args.out.write_text(raw, encoding='utf-8', newline='\n')
    print(raw, end='')


if __name__ == '__main__':
    main()
