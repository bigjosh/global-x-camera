"""Plan or publish byte-exact PHY-sequencing evidence from an explicit JSON list.

No instrument access. Defaults to validation only; --write publishes immutable
files after every source, attribution and destination has been checked.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import struct

DEST = Path(__file__).resolve().parent
ROOT = DEST.parents[3]
EVIDENCE = DEST.parent
# Use the archived helper when replaying an already-published checkpoint.
import importlib.util
summary_path = DEST / 'extra/summarize.py'
if not summary_path.exists():
    summary_path = ROOT / 'firmware/capture-timing/summarize.py'
summary_spec = importlib.util.spec_from_file_location('fast_archive_summary', summary_path)
summary_module = importlib.util.module_from_spec(summary_spec)
summary_spec.loader.exec_module(summary_module)
summarize_documents = summary_module.summarize_documents


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2) + '\n').encode('utf-8')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def repo_path(value):
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError(f'Source escapes repository: {value}')
    return path


def short(path):
    return str(path.relative_to(ROOT)).replace('\\', '/')


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', value):
        raise ValueError(f'Invalid experiment/build identifier: {value!r}')
    return value


class Plan:
    def __init__(self):
        self.pending = {}
        self.files = {}

    def add(self, relative, data, source=None, shared=False):
        relative = Path(relative)
        path = (DEST / relative).resolve()
        boundary = EVIDENCE.resolve() if shared else DEST.resolve()
        if not path.is_relative_to(boundary):
            raise ValueError(f'Archive destination escapes boundary: {relative}')
        if len(data) > 2_000_000:
            raise ValueError(f'Unexpected large evidence file: {source or relative}')
        if path.exists() and path.read_bytes() != data:
            raise ValueError(f'Refusing different overwrite: {path}')
        if path in self.pending and self.pending[path] != data:
            raise ValueError(f'Conflicting planned bytes: {path}')
        if shared and not path.exists():
            raise ValueError(f'Shared object does not exist: {path}')
        if not shared:
            self.pending[path] = data
        if source is not None:
            key = str(relative).replace('\\', '/')
            self.files[key] = dict(source=source, archive=key,
                                   bytes=len(data), sha256=digest(data))

    def copy(self, source, relative):
        self.add(relative, source.read_bytes(), short(source))

    def generated(self, relative, value):
        self.add(relative, encoded(value), 'derived by archive-script.py')

    def write(self):
        for path, data in self.pending.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                if path.read_bytes() != data:
                    raise ValueError(f'Destination changed after validation: {path}')
            else:
                with path.open('xb') as stream:
                    stream.write(data)


def shared_object(expected):
    for path in sorted(EVIDENCE.glob(f'*/source-objects/{expected}.*')):
        if digest(path.read_bytes()) == expected:
            return path
    return None


def sources_for(plan, builds):
    provenance = []
    for build_id, (directory, manifest) in builds.items():
        for name, expected in manifest.get('sources', {}).items():
            if not re.fullmatch(r'[a-fA-F0-9]{64}', expected):
                raise ValueError(f'Invalid source hash in {build_id}: {name}')
            source = repo_path(name)
            record = dict(build=build_id, source=name.replace('\\', '/'),
                          expected_sha256=expected)
            current = source.read_bytes() if source.exists() else None
            record['current_sha256'] = digest(current) if current is not None else None
            exact = current is not None and digest(current) == expected
            shared = shared_object(expected)
            if shared is not None:
                relative = Path('..') / shared.relative_to(EVIDENCE)
                plan.add(relative, shared.read_bytes(), short(shared), shared=True)
                record.update(status='verified exact bytes archived',
                              archive=str(relative).replace('\\', '/'),
                              current_source_matches=exact)
            elif exact:
                relative = Path('source-objects') / (expected + source.suffix.lower())
                plan.copy(source, relative)
                record.update(status='verified exact bytes archived', archive=str(relative).replace('\\', '/'),
                              current_source_matches=True)
            else:
                record['status'] = ('missing; historical bytes unavailable' if current is None
                                    else 'changed since build; historical bytes unavailable')
            provenance.append(record)
    return provenance


def copy_capture(plan, directory, logic, archive):
    # The compact raw records are retained even when no frame/timing was produced.
    for name in ('timing.json', 'events-analysis.json', 'analysis-note.json',
                 'diagnostic-analysis.json', 'phy-summary.json', 'offline-failure-summary.json',
                 'logic.log', 'cycle.log', 'bench.log'):
        path = directory / name
        if path.exists():
            plan.copy(path, archive / name)
    ram = directory / 'ram'
    if ram.exists():
        for path in sorted(ram.iterdir()):
            if path.is_file() and (path.suffix.lower() in ('.json', '.jsonl', '.log', '.txt')
                                  or path.suffix.lower() == '.bin' and path.name != 'frame.bin'):
                if path.suffix.lower() == '.bin' and path.stat().st_size > 65536:
                    raise ValueError(f'Unexpected RAM dump size: {path}')
                plan.copy(path, archive / 'ram' / path.name)
    for name in ('digital.csv', 'capture-config.json', 'boot-summary.json',
                 'rail-validation.json', 'powered-state.json'):
        path = logic / name
        if path.exists():
            plan.copy(path, archive / 'logic' / name)



# RM0486/CMSIS STM32N657 CSI status bits: protocol errors in SR0[30:24],
# command FIFO full in SR0[21], D-PHY errors in SR1[12:8] and SR1[4:0].
# Always inspect raw flags independently of HAL callback count or interrupt enables.
SR0_ERROR_MASK = 0x7f200000
SR1_ERROR_MASK = 0x00001f1f
FAST_FIELDS = ('event cycles tick sr0 sr1 ier0 ier1 prcr pcr cr lmcfgr '
               'apb5rstr pa0 frames vsyncs strobe_ordinal').split()


def fast_evidence(plan, item, archive, receiver, summary, timing):
    if not item.get('fast_directory'):
        return dict(status='not instrumented; raw FAST phase snapshots unavailable')
    directory = repo_path(item['fast_directory'])
    for path in sorted(directory.iterdir()):
        if path.is_file() and (path.suffix.lower() in ('.json', '.jsonl', '.log', '.txt')
                or path.suffix.lower() == '.bin' and path.stat().st_size <= 65536
                and path.name not in ('frame.bin', 'readback.bin')):
            plan.copy(path, archive / 'fast' / path.name)
    raw = (directory / 'fast.bin').read_bytes()
    if len(raw) != 2176 or receiver.get('fast_phy_status_words') != 544:
        raise ValueError('FAST buffer or manifest schema/size mismatch')
    words = list(struct.unpack('<544I', raw))
    header = words[:32]
    if header[0] != 0x46505931 or header[8] != 1 or header[2] > 32:
        raise ValueError('FAST header invalid')
    mode = {'early': 0, 'streaming': 1}[receiver['data_enable']]
    if header[6] != mode:
        raise ValueError('FAST mode differs from receiver manifest')
    result = read_json(directory / 'result.json')
    if result.get('receiver_sha256') != receiver['raw_sha256'] or result['words'] != words:
        raise ValueError('FAST decoded result does not match raw bytes/build')
    records = [dict(zip(FAST_FIELDS, words[32+i*16:48+i*16])) for i in range(header[2])]
    original = result['records']
    if len(original) != len(records) or any(any(a[k] != b[k] for k in FAST_FIELDS)
                                           for a, b in zip(records, original)):
        raise ValueError('FAST decoded records differ from raw buffer')
    first_frame = next((i for i, r in enumerate(records) if r['event'] == 430), None)
    before_sensor_stop = next((i for i, r in enumerate(records) if r['event'] == 439), None)
    after_sensor_stop = next((i for i, r in enumerate(records) if r['event'] == 436), None)
    groups = dict(startup_through_first_frame=[], after_frame_before_sensor_stop=[],
                  during_sensor_stop=[], after_sensor_stop=[], unclassified=[])
    raw_errors = []
    for i, record in enumerate(records):
        record['csi_read'] = record['prcr'] != 0xffffffff
        if not record['csi_read']:
            continue
        record['sr0_errors'] = record['sr0'] & SR0_ERROR_MASK
        record['sr1_errors'] = record['sr1'] & SR1_ERROR_MASK
        phase = ('startup_through_first_frame' if first_frame is not None and i <= first_frame else
                 'after_frame_before_sensor_stop' if before_sensor_stop is not None and i <= before_sensor_stop else
                 'during_sensor_stop' if after_sensor_stop is not None and i <= after_sensor_stop else
                 'after_sensor_stop' if after_sensor_stop is not None else 'unclassified')
        record['phase'] = phase
        groups[phase].append(record)
        if record['sr0_errors'] or record['sr1_errors']:
            raw_errors.append(record)
    phase_summary = {}
    for name, values in groups.items():
        error0 = error1 = 0
        for record in values:
            error0 |= record['sr0_errors']; error1 |= record['sr1_errors']
        phase_summary[name] = dict(snapshot_count=len(values), sr0_error_union=error0,
                                  sr1_error_union=error1,
                                  ier1_values=sorted(set(r['ier1'] for r in values)),
                                  qualifier='sampled raw flags; not a continuous lane waveform')
    vsync = next((r for r in records if r['event'] == 429), None)
    frame = next((r for r in records if r['event'] == 430), None)
    ordinal_supported = bool(header[3] == 0 and vsync and frame and header[30] == 1
        and header[31] == 1 and vsync['strobe_ordinal'] == 1 and frame['strobe_ordinal'] == 1
        and vsync['vsyncs'] == 1 and frame['frames'] == 1)
    if ordinal_supported != result['first_physical_exposure_ordinal_supported']:
        raise ValueError('FAST ordinal assertion differs from independently decoded bytes')
    pulses = summary['strobe_pulses'] if summary else []
    external_order = bool(pulses and summary['phases_us']['first_vsync'] is not None
        and summary['phases_us']['first_frame_complete'] is not None
        and pulses[0]['fall_us'] <= summary['phases_us']['first_vsync']
        < summary['phases_us']['first_frame_complete']
        and (len(pulses) < 2 or summary['phases_us']['first_frame_complete'] < pulses[1]['rise_us']))
    markers = {}
    if timing and timing.get('nrst_release_s') is not None:
        for label, event_id in [('start_ack_observed', 425), ('streaming_observed', 26),
            ('before_data_enable', 437), ('after_data_enable', 438), ('stop_qualified', 409),
            ('before_arm', 441), ('armed', 22), ('first_vsync', 29)]:
            event = next((e for e in timing['events'] if e['id'] == event_id), None)
            markers[label] = (round((event['time_s'] - timing['nrst_release_s']) * 1e6, 3)
                              if event else None)
    intervals = {}
    if markers and summary:
        first = summary['first_strobe_us']
        for label in ['start_ack_observed', 'streaming_observed', 'after_data_enable', 'armed']:
            intervals[label + '_after_first_strobe_us'] = (round(markers[label] - first, 3)
                if markers[label] is not None and first is not None else None)
        intervals['armed_to_first_vsync_us'] = (round(markers['first_vsync'] - markers['armed'], 3)
            if markers['first_vsync'] is not None and markers['armed'] is not None else None)
    shutdown = dict(status='not enabled in this build')
    if receiver.get('shutdown_data_off'):
        proof_path = directory / item.get('shutdown_filename', 'shutdown.bin')
        proof_bytes = proof_path.read_bytes()
        if (len(proof_bytes) != 64 or receiver.get('shutdown_proof_address') != '0x343f8900'
                or receiver.get('shutdown_proof_words') != 16 or receiver.get('shutdown_proof_schema') != 1):
            raise ValueError('Shutdown proof manifest/size mismatch')
        w = list(struct.unpack('<16I', proof_bytes))
        if w[:2] != [0x46534431, 1] or not 1 <= w[2] <= 4:
            raise ValueError('Shutdown proof header invalid')
        clocks = ((w[3] & 0x44) == 0x44 and (w[4] & 0x30000) == 0x30000
                  and not (w[5] & 0x44))
        idle = not (w[6] & 0x20000 or w[7] & 8 or w[8] & 0x8000 or w[9] & 0x80000000)
        proof_complete = bool(w[2] == 4 and w[15] == 0 and clocks and idle
                              and w[10] & 2 and w[11] == 15 and w[12] == 3)
        relevant = [r for r in records if r['event'] in (439, 442, 443, 436)]
        sequence = False
        controls_preserved = False
        if not header[3] and header[1] == 40 and [r['event'] for r in relevant] == [439,442,443,436]:
            times = [relevant[0]['cycles'], relevant[1]['cycles'], w[13], w[14],
                     relevant[2]['cycles'], relevant[3]['cycles']]
            sequence = all(((b-a) & 0xffffffff) < 0x80000000 for a,b in zip(times,times[1:]))
            before, after = relevant[1:3]
            controls_preserved = bool(before['pcr'] == w[11] == 15 and after['pcr'] == w[12] == 3
                and before['prcr'] == after['prcr'] == w[10]
                and all(before[k] == after[k] for k in ['ier0','ier1','cr','lmcfgr','apb5rstr']))
        shutdown = dict(status='verified raw proof', raw_sha256=digest(proof_bytes), words=w,
            clocks_and_reset_valid=clocks, idle_conditions_satisfied=idle if w[2]>=2 else None,
            proof_complete=proof_complete, proof_matches_fast_sequence=sequence,
            other_control_registers_preserved=controls_preserved,
            completed=bool(proof_complete and sequence and controls_preserved))
        if 'shutdown_proof' in result and result['shutdown_proof']['words'] != w:
            raise ValueError('Shutdown decoded result differs from raw bytes')
    evidence = dict(status='verified raw buffer and matching build', raw_sha256=digest(raw),
        mode=receiver['data_enable'], overflow=header[3], first_ordinal_supported=ordinal_supported,
        external_first_pulse_frame_order=external_order,
        first_frame_identity_supported=bool(ordinal_supported and external_order
            and summary['image_integrity_matches'] and summary['completed']),
        first_frame_identity_limit='STROBE ordinal and event ordering, not sensor embedded frame-ID readback',
        error_masks=dict(sr0=SR0_ERROR_MASK, sr1=SR1_ERROR_MASK),
        raw_phase_errors=phase_summary, raw_error_records=raw_errors,
        header_cycles=dict(start_ack=header[9], streaming=header[10],
                           data_enable_begin=header[11], data_enable_end=header[12], arm=header[22]),
        strobe_ordinal_at_arm=header[23], marker_phases_after_nrst_us=markers,
        marker_intervals=intervals,
        timing_qualification='Saleae-correlated firmware marker edges; STROBE markers use the existing ISR correlation, not a new direct analog exposure measurement',
        event_semantics={'250': 'Receiver configuration completed; inherited raw label saying armed is obsolete in FAST builds',
                         '22': 'Actual receiver armed marker', '422': 'FAST raw snapshot after receiver arm'},
        shutdown=shutdown, records=records)
    plan.generated(archive / 'fast-derived.json', evidence)
    return evidence


def guard_evidence(prefix):
    sources = {name.replace('\\', '/'): value for name, value in prefix.get('sources', {}).items()
               if Path(name.replace('\\', '/')).name in ('recovery_gpio.c', 'recovery_gpio.h')}
    return dict(source_sha256=sources, prefix_program_sha256=prefix.get('program_sha256'),
                prefix_raw_sha256=prefix.get('stage1_raw_sha256'),
                declared_recovery_gpio=prefix.get('recovery_gpio'),
                qualification='source and complete image identity; not a new independent electrical guard test')


def checkpoint_readme(config, ledger):
    lines = ['# Fast free-running PHY evidence — October 17, 2026', '',
        config['checkpoint'], '',
        'All times below are microseconds. Reset means the measured NRST release; START means the end of the sensor START write. '
        'Exposure timing retains the existing Saleae/firmware STROBE-marker correlation. '
        'This archive does not introduce a direct analog exposure measurement.', '',
        '| Capture | Applied coarse lines | Reset → first STROBE | START → first STROBE | Arm → first VSYNC | First frame ordinal supported | Raw SR1 error union through first frame | Raw SR1 error union during sensor STOP |',
        '| --- | ---: | ---: | ---: | ---: | --- | --- | --- |']
    for entry in ledger:
        summary, fast = entry['summary'], entry['fast_phy']
        if summary is None:
            lines.append('| '+entry['experiment_id']+' | — | — | — | — | unavailable | unavailable | unavailable |')
            continue
        phases = fast.get('raw_phase_errors', {})
        error = lambda phase: ('0x%08x' % phases[phase]['sr1_error_union'] if phase in phases else 'not instrumented')
        identity = ('yes' if fast.get('first_frame_identity_supported') else
                    'no' if 'first_frame_identity_supported' in fast else 'not instrumented')
        cells = [entry['experiment_id'], str(summary['first_frame_status']['applied_coarse_lines']),
            str(summary['first_strobe_us']), str(summary['intervals_us']['start_write_end_to_first_strobe']),
            str(fast.get('marker_intervals', {}).get('armed_to_first_vsync_us', 'not instrumented')),
            identity, error('startup_through_first_frame'), error('during_sensor_stop')]
        lines.append('| '+' | '.join(cells)+' |')
    short_margins = [e['fast_phy']['marker_intervals']['armed_to_first_vsync_us'] for e in ledger
        if e['summary'] and e['summary']['first_frame_status']['applied_coarse_lines'] == 5
        and e['fast_phy'].get('shutdown', {}).get('completed')
        and e['fast_phy'].get('marker_intervals', {}).get('armed_to_first_vsync_us') is not None]
    if short_margins:
        lines += ['', 'For the completed v36 five-line captures, observed arm-marker to first-VSYNC-marker margin is '
            +str(min(short_margins))+'–'+str(max(short_margins))+' µs. These bench runs do not qualify a guaranteed '
            'margin across voltage, temperature, sensor revisions or production variation.']
    v36 = [e for e in ledger if e['fast_phy'].get('shutdown', {}).get('completed')]
    default_count = sum(e['summary']['first_frame_status']['applied_coarse_lines'] == 1428 for e in v36)
    minimum_count = sum(e['summary']['first_frame_status']['applied_coarse_lines'] == 5 for e in v36)
    selected = next(e for e in ledger if e['experiment_id'] == config['final_capture'])
    lines += ['', str(len(v36))+' v36 runs completed with shutdown proof: '+str(default_count)
        +' at the default exposure and '+str(minimum_count)+' at the five-line minimum. '
        'Every one supports first-frame ordinal 1, matches native frame integrity and has no sampled raw CSI errors in any recorded phase.', '',
        'Final installed first-64-KiB image SHA-256: `'+selected['recovery_guard']['prefix_program_sha256']+'`.', '']
    lines += ['The root agent reported 117 passing offline tests on the unchanged source:']
    for test in config['validation_report']['suites']:
        lines.append('- `'+test['command']+'` — '+str(test['passed'])+' passed.')
    lines += ['', config['validation_report']['discovery_note'], '']
    lines += ['',
        'Raw status unions are independent of HAL callback counts and interrupt-enable masks. '
        'They describe the retained snapshots and IRQ-entry records; a zero value is not a continuous electrical lane trace. '
        '`0x00001000` is the lane-1 D-PHY control/state-sequence error. The ledger also retains SR0 protocol-error masks, '
        'all raw phase records, interrupt-enable values and shutdown proof where instrumented.', '',
        'A supported first-frame ordinal combines the first-STROBE ordinal from the FAST buffer, correlated first-pulse/VSYNC/frame order, '
        'completed frame readback and matching integrity. It is not sensor embedded frame-ID readback. '
        'Visual review is recorded separately and is never inferred from pixel statistics.', '',
        'For v35/v36 FAST builds, the inherited raw label on event 250 is obsolete: this event means receiver configuration completed. '
        'Actual arm timing uses event 22 and FAST snapshot 422. The archived raw labels are preserved without alteration.', '',
        '- [Ledger and derived phase records](ledger.json)',
        '- [Explicit visual review assertions](visual-review.json)',
        '- [Final recovery park verification](recovery-checks.json)',
        '- [Final powered state and released instrument session](final-state.json)',
        '- [Build source provenance](source-provenance.json)',
        '- [Archive hash index](archive-index.json)', '',
        'Every capture is linked to a receiver manifest and a complete prefix image verified by full 64 KiB programming readback. '
        'The ledger records the recovery GPIO source hashes and each prefix hash; the earlier '
        '[diode recovery qualification](../2026-10-17-diode-recovery-smoke/README.md) remains the electrical recovery evidence. '
        'Original manifests retain their build-time `hardware_status` fields unchanged.', '',
        'The archive contains compact JSON, status buffers, source objects, build manifests, programming verification and digital event CSVs. '
        'Frame images, raw frame pixels, analog CSVs and full Logic recordings remain local under `tmp/bringup` and are deliberately excluded. '
        'Unchanged source objects may be referenced by verified hash from earlier evidence archives. Vendor licenses and provenance are retained.', '',
        'Each manifest preserves its original generator-input fingerprints. A fingerprint does not imply the historical generator bytes '
        'were recovered: separately archived generator revisions appear explicitly in the hash index. Compiled source files are '
        'individually attributed in the source-provenance record.', '',
        'The top-level `firmware/capture-timing/verify_evidence.py` checks every indexed byte without the local capture originals. '
        'Replaying this archive script requires the original paths named in its configuration. '
        'Publication uses `--write` and refuses differing overwrites.', '']
    return '\n'.join(lines).encode('utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    config_path = repo_path(args.config)
    config = read_json(config_path)
    if config.get('schema') != 1 or not config.get('captures') or not config.get('builds'):
        raise ValueError('Configuration needs schema=1 and nonempty captures/builds lists')
    plan = Plan()
    builds = {}
    for item in config['builds']:
        name = identifier(item['id'])
        if name in builds:
            raise ValueError(f'Duplicate build: {name}')
        directory = repo_path(item['directory'])
        manifest = read_json(directory / 'manifest.json')
        builds[name] = directory, manifest
        plan.copy(directory / 'manifest.json', Path('builds') / name / 'manifest.json')
    ledger, visual = [], []
    ids = set()
    for item in config['captures']:
        name = identifier(item['id'])
        if name in ids or item['outcome'] not in ('completed', 'failed', 'partial'):
            raise ValueError(f'Duplicate id or invalid explicit outcome: {name}')
        ids.add(name)
        directory = repo_path(item['directory'])
        if not directory.is_dir():
            raise ValueError(f'Capture directory does not exist: {directory}')
        receiver_dir, receiver = builds[item['receiver_build']]
        prefix_dir, prefix = builds[item['prefix_build']]
        if prefix.get('stage2_sha256') != receiver.get('raw_sha256'):
            raise ValueError(f'Prefix/receiver payload attribution mismatch: {name}')
        expected_manifest = prefix.get('stage2_manifest_sha256')
        if expected_manifest and digest((receiver_dir / 'manifest.json').read_bytes()) != expected_manifest:
            raise ValueError(f'Receiver manifest bytes do not match prefix: {name}')
        entry = dict(experiment_id=name, outcome=item['outcome'],
                     outcome_note=item.get('outcome_note'), capture_dir=short(directory),
                     receiver_build=item['receiver_build'], prefix_build=item['prefix_build'],
                     summary=None, programming_verification='not supplied')
        archive = Path('captures') / name
        logic = repo_path(item['logic_directory']) if item.get('logic_directory') else directory / 'logic'
        copy_capture(plan, directory, logic, archive)
        timing_path, result_path = directory / 'timing.json', directory / 'ram/capture-result.json'
        result = read_json(result_path) if result_path.exists() else None
        if result is not None and result.get('build_sha256') != receiver['raw_sha256']:
            raise ValueError(f'RAM result/build attribution mismatch: {name}')
        if result is not None and timing_path.exists():
            try:
                entry['summary'] = summarize_documents(read_json(timing_path), result)
            except (ValueError, KeyError, TypeError) as error:
                entry['summary_unavailable_reason'] = str(error)
        else:
            entry['summary_unavailable_reason'] = 'Timing and/or RAM result absent; no timing inferred.'
        parameters = receiver.get('parameters', {})
        semantics = {key: parameters[key] for key in
                     ('captured_sensor_frame', 'first_frame_latency_eligible') if key in parameters}
        if semantics:
            entry['capture_semantics_from_manifest'] = semantics
            if entry['summary'] is not None:
                entry['summary'].update(semantics)
                if semantics.get('first_frame_latency_eligible') is False:
                    entry['summary']['warnings'].append(
                        'First frame-complete phase means first received frame, not first requested sensor image; '
                        'this diagnostic is ineligible for first-frame latency claims.')
                frame_number = semantics.get('captured_sensor_frame')
                if isinstance(frame_number, int) and frame_number > len(entry['summary']['strobe_pulses']):
                    raise ValueError(f'Insufficient exposure evidence for declared captured frame: {name}')
        rail = logic / 'rail-validation.json'
        entry['rail_validation'] = read_json(rail) if rail.exists() else None
        cycle_value = item.get('programming_cycle_directory')
        direct_value = item.get('programming_directory')
        if cycle_value and direct_value:
            raise ValueError(f'Choose cycle or direct programming records, not both: {name}')
        if cycle_value:
            cycle = repo_path(cycle_value)
            for path in sorted(cycle.rglob('*')):
                relative = path.relative_to(cycle)
                if (path.is_file() and (relative.parts[0] in ('write', 'info', 'maintenance')
                                       or relative == Path('programmed-image.json'))
                        and (path.suffix.lower() in ('.json', '.jsonl', '.log', '.txt')
                             or path.suffix.lower() == '.bin' and path.name != 'readback.bin'
                             and path.stat().st_size <= 65536)):
                    plan.copy(path, archive / 'cycle' / relative)
            programmed_path, verified_path = cycle / 'programmed-image.json', cycle / 'write/verified.json'
            if programmed_path.exists() and verified_path.exists():
                programmed, verified = read_json(programmed_path), read_json(verified_path)
                if not (programmed['sha256'] == verified['sha256'] == prefix['program_sha256']
                        and verified.get('byte_for_byte_match') is True):
                    raise ValueError(f'Programmed image attribution mismatch: {name}')
                entry['programming_verification'] = 'full byte-for-byte readback matches prefix manifest'
            else:
                entry['programming_verification'] = 'supplied cycle lacks complete verification records'
        elif direct_value:
            programming = repo_path(direct_value)
            for path in sorted(programming.iterdir()):
                if path.is_file() and (path.suffix.lower() in ('.json', '.jsonl', '.log', '.txt')
                        or path.suffix.lower() == '.bin' and path.name != 'readback.bin'
                        and path.stat().st_size <= 65536):
                    plan.copy(path, archive / 'programming' / path.name)
            request = read_json(programming / 'request.json')
            verified = read_json(programming / 'verified.json')
            if not (request.get('operation') == 'write'
                    and request['desired_sha256'] == verified['sha256'] == prefix['program_sha256']
                    and verified.get('byte_for_byte_match') is True
                    and verified.get('bytes') == prefix['program_bytes']):
                raise ValueError(f'Direct programming attribution mismatch: {name}')
            entry['programming_verification'] = 'full byte-for-byte readback matches prefix manifest'
        if item['outcome'] == 'completed' and not (
                entry['summary'] is not None and result.get('completed') is True
                and result.get('image_integrity_matches') is True
                and result.get('frames', 0) >= 1
                and entry['summary']['phases_us']['first_frame_complete'] is not None
                and entry['rail_validation']
                and entry['rail_validation'].get('passed') is True
                and entry['programming_verification'].startswith('full byte-for-byte')):
            raise ValueError(f'Completed capture lacks frame/timing/rails/programming qualification: {name}')
        review = item.get('visual_review')
        if review is not None:
            if not result or not all(review.get(k) for k in ('status', 'reviewer', 'provenance')):
                raise ValueError(f'Visual assertion requires result, status, reviewer and provenance: {name}')
            visual.append(dict(experiment_id=name, **review,
                               source_result_sha256=digest(result_path.read_bytes()),
                               raw_result_visual_field_preserved=True))
        else:
            visual.append(dict(experiment_id=name, status='not supplied; no visual success inferred'))
        entry['recovery_guard'] = guard_evidence(prefix)
        entry['fast_phy'] = fast_evidence(plan, item, archive, receiver, entry['summary'],
                                        read_json(timing_path) if timing_path.exists() else None)
        entry['generator_input_fingerprints'] = dict(receiver=receiver.get('generator_inputs', {}),
                                                    prefix=prefix.get('generator_inputs', {}))
        if item.get('normal_guard_directory'):
            normal_dir = repo_path(item['normal_guard_directory'])
            for path in sorted(normal_dir.iterdir()):
                if path.is_file() and (path.suffix.lower() in ('.json', '.jsonl', '.log')
                        or path.suffix.lower() == '.bin' and path.stat().st_size <= 65536):
                    plan.copy(path, archive / 'normal-guard' / path.name)
            normal = read_json(normal_dir / 'result.json')
            if not (normal.get('passed') is True and normal.get('normal_branch_observed') is True
                    and normal['status']['state'] == 2 and normal['status']['reason'] == 0
                    and normal['status']['idr'] & 2):
                raise ValueError('Final normal recovery branch proof failed')
            entry['normal_guard_observed'] = normal
        ledger.append(entry)
    recovery_checks = []
    for item in config.get('recovery_checks', []):
        name = identifier(item['id'])
        directory = repo_path(item['directory'])
        prefix = builds[item['prefix_build']][1]
        archive = Path('recovery') / name
        for path in sorted(directory.rglob('*')):
            if not path.is_file() or path.name == 'analog.csv':
                continue
            if (path.suffix.lower() in ('.json', '.jsonl', '.log', '.txt')
                    or path.name == 'digital.csv'
                    or path.suffix.lower() == '.bin' and path.stat().st_size <= 65536):
                plan.copy(path, archive / path.relative_to(directory))
        result = read_json(directory / 'park/result.json')
        rail = read_json(directory / 'logic/rail-validation.json')
        live_hash = digest((directory / 'park/live-prefix.bin').read_bytes())
        expected_pc = int(prefix['recovery_gpio']['park_address'], 16)
        if not (result.get('passed') is True and rail.get('passed') is True
                and live_hash == result['prefix_sha256'] == prefix['stage1_raw_sha256']
                and result['context']['PC'] == expected_pc
                and result['status']['state'] == 3 and result['status']['reason'] == 1
                and not result['status']['idr'] & 2 and not result['ccr'] & 0x30000
                and result.get('ram_writes') is False and result.get('nor_commands') is False):
            raise ValueError(f'Recovery proof attribution/park check failed: {name}')
        recovery_checks.append(dict(id=name, prefix_build=item['prefix_build'], result=result,
                                    rail_validation=rail, live_prefix_sha256=live_hash,
                                    independently_matched_prefix_and_park=True))
    plan.generated('recovery-checks.json', recovery_checks)
    provenance = sources_for(plan, builds)
    # Explicit additional compact records (for example final power-release evidence).
    for item in config.get('extra_files', []):
        source = repo_path(item['source'])
        if source.suffix.lower() == '.bin':
            if (source.stat().st_size > 65536 or source.name in ('frame.bin', 'readback.bin', 'capture_sector_0.bin')):
                raise ValueError(f'Unsupported extra binary: {source}')
        elif source.suffix.lower() not in ('.json', '.jsonl', '.log', '.txt', '.csv', '.md', '.py', '.cfg', '.inc'):
            raise ValueError(f'Unsupported extra-file type: {source}')
        plan.copy(source, Path('extra') / item['archive'])
    final_directory = repo_path(config['final_state_directory'])
    final_state = read_json(final_directory / 'powered-state.json')
    if not (final_state.get('passed') is True and final_state['session_release']['ok'] is True
            and final_state['session_release']['range'] == 128
            and final_state['session_release']['recovery_output']['extio_voltage_mv'] == 3300
            and final_state['session_release']['recovery_output']['gpo0'] == 1):
        raise ValueError('Final power/session release verification failed')
    plan.generated('final-state.json', dict(source=short(final_directory / 'powered-state.json'),
        observation=final_state, final_capture=config['final_capture'],
        installed_program_sha256=builds[config['final_prefix_build']][1]['program_sha256'],
        no_additional_hardware_access_by_archiver=True))
    license_path = EVIDENCE / '2026-10-17-through-v16/license-index.json'
    for item in read_json(license_path)['files']:
        source = repo_path(item['source'])
        if digest(source.read_bytes()) != item['sha256']:
            raise ValueError(f'License source changed: {source}')
        plan.copy(source, Path(item['archive']))
    plan.copy(license_path, Path('license-index.json'))
    plan.copy(config_path, Path('archive-config.json'))
    plan.copy(Path(__file__).resolve(), Path('archive-script.py'))
    plan.generated('source-provenance.json', provenance)
    plan.generated('visual-review.json', dict(date=config.get('date'), reviews=visual))
    plan.generated('ledger.json', dict(schema=1, checkpoint=config.get('checkpoint'), time_unit='us', experiments=ledger))
    plan.add('README.md', checkpoint_readme(config, ledger), 'derived by archive-script.py')
    # The index cannot include its own hash; all other generated records are indexed.
    plan.add('archive-index.json', encoded(dict(schema=1,
        scope=config.get('scope', 'Fast free-running PHY sequencing checkpoint; completed runs only.'),
        files=list(plan.files.values()))))
    if args.write:
        plan.write()
    print(json.dumps(dict(mode='written' if args.write else 'validated; no files written',
        experiments=len(ledger), files=len(plan.files),
        bytes=sum(item['bytes'] for item in plan.files.values()),
        sources_unavailable=[item for item in provenance
                             if item['status'] != 'verified exact bytes archived']), indent=2))


if __name__ == '__main__':
    main()
