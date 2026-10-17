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
    mode = {'early': 0, 'streaming': 1, 'ack': 2, 'timed': 3,
            'early_stop': 4, 'force_stop': 5, 'force_lane1': 6}[receiver['data_enable']]
    if mode >= 2 and receiver.get('readiness_gate') != mode:
        raise ValueError('Manifest lacks the explicit reviewed readiness gate')
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
    if receiver.get('shutdown_data_off') and not item.get('shutdown_not_reached'):
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
    if item.get('shutdown_not_reached'):
        if item['outcome'] != 'failed':
            raise ValueError('Unreached shutdown exception requires explicit failed outcome')
        uninitialized=(directory/'shutdown.bin').read_bytes()
        shutdown=dict(status='not reached; raw uninitialized buffer preserved without register interpretation',
            completed=False,raw_sha256=digest(uninitialized),bytes=len(uninitialized))
    calibrated_phases = {}
    if timing and summary:
        events = timing['events']
        first_event = lambda event_id: next((e for e in events if e['id'] == event_id), None)
        def calibrated(cycle):
            before = [e for e in events if e['cycles'] <= cycle]
            after = [e for e in events if e['cycles'] >= cycle]
            if not cycle or not before or not after:
                return None
            a, b = max(before, key=lambda e: e['cycles']), min(after, key=lambda e: e['cycles'])
            return (a['time_s'] if a['cycles'] == b['cycles'] else a['time_s'] +
                (cycle-a['cycles']) * (b['time_s']-a['time_s']) / (b['cycles']-a['cycles']))
        cycles = dict(ack=header[9], streaming=header[10], enable_begin=header[11],
                      enable_end=header[12], stop_qualified=header[21], prearm=header[22])
        for label, event_id in [('start',25),('strobe',50),('armed',22),('vsync',29)]:
            event = first_event(event_id)
            cycles[label] = event['cycles'] if event else 0
        times = {k:calibrated(v) for k,v in cycles.items()}
        for begin, end in [('start','ack'),('ack','streaming'),('streaming','enable_end'),
            ('enable_end','stop_qualified'),('stop_qualified','armed'),('ack','armed'),
            ('strobe','ack'),('strobe','enable_end'),('strobe','armed'),('armed','vsync')]:
            calibrated_phases[begin+'_to_'+end+'_us'] = (round((times[end]-times[begin])*1e6,3)
                if times[begin] is not None and times[end] is not None else None)
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
        shutdown=shutdown, calibrated_phase_intervals=calibrated_phases,
        data_enable_cycles_are_physical_lane_enable=mode not in (4,5,6),
        receiver_stop_qualification=dict(reported_sr1=header[20], cycle=header[21],
            both_data_stop_flags=bool((header[20]&0x02080000)==0x02080000),
            nominal_dwell_cycles=receiver.get('stop_dwell_cycles',40000),
            enable_to_qualification_cycles=(header[21]-header[12])&0xffffffff,
            qualification='Receiver-reported STOP status; this is not independent electrical LP-11 proof'),
        calibration_method='Raw DWT timestamps interpolated between adjacent matched Saleae marker events; estimates, not new electrical measurements',
        records=records)
    if mode in (4,5,6):
        force_raw = (directory / 'force.bin').read_bytes()
        if (len(force_raw)!=128 or receiver.get('force_rx_proof_address')!='0x343f8940'
                or receiver.get('force_rx_proof_words')!=32 or receiver.get('force_rx_proof_schema')!=1):
            raise ValueError('ForceRx fixed proof manifest/layout mismatch')
        w = list(struct.unpack('<32I',force_raw))
        if w[:3] != [0x52465231,1,mode] or not 1<=w[3]<=6:
            raise ValueError('ForceRx header mismatch')
        expected = {4:0,5:3,6:2}[mode]
        dwell = receiver.get('stop_dwell_cycles')
        if dwell not in (0,40000):raise ValueError('Unsupported fixed ForceRx dwell')
        complete = bool(w[3]==6 and w[29]==0 and w[31]==0x344 and
            w[30]==3 and w[10]==3 and w[13]==w[16]==w[19]==expected and w[22]==0 and
            all(w[i] for i in (24,25,26,27)) and w[28]==dwell and
            dwell<=((w[15]-w[27])&0xffffffff)<0x80000000 and
            (w[17]&0x02080000)==0x02080000 and (w[20]&0x02080000)==0x02080000)
        ids=(399,405,406,409,441,422,425,426)
        relevant=[r for r in records if r['event'] in ids]
        sequence=False
        if not header[3] and [r['event'] for r in relevant]==list(ids):
            r={r['event']:r['cycles'] for r in relevant}
            seq=[w[4],w[5],r[399],w[6],r[405],w[9],r[406],w[12],r[409],
                 w[15],w[18],w[21],r[441],r[422],r[425],r[426]]
            sequence=all(((b-a)&0xffffffff)<0x80000000 for a,b in zip(seq,seq[1:])) and all(
                ((w[i]-w[9])&0xffffffff)<0x80000000 and
                ((w[15]-w[i])&0xffffffff)<0x80000000 for i in (24,25,26))
        source_proof=result.get('force_rx_proof',{})
        if source_proof.get('words')!=w or source_proof.get('completed')!=bool(complete and sequence):
            raise ValueError('Original ForceRx decoded proof differs from independent raw check')
        observations={name:dict(cycles=w[i],pmcr=w[i+1],sr1=w[i+2]) for name,i in zip(
            ['before_pen_before_pmcr_write','after_pen','before_stop_poll','after_stop_stable',
             'before_force_release','after_force_release'],range(6,24,3))}
        force=dict(raw_sha256=digest(force_raw),words=w,observations=observations,
            proof_complete=complete,proof_matches_fast_sequence=sequence,completed=bool(complete and sequence),
            first_stop0_cycle=w[24],first_stop1_cycle=w[25],first_both_stop_cycle=w[26],
            required_stable_cycles=w[28],physical_data_enable_bracket='FAST 405/406 and proof before/after PEN',
            qualification='Receiver read observations, not exact electrical transitions; raw errors and frame integrity are separate')
        if timing and summary:
            start=first_event(25)['time_s']
            force['calibrated_after_start_us']={label:round((calibrated(w[i])-start)*1e6,3) for label,i in
                [('before_pen',6),('after_pen',9),('first_stop0',24),('first_stop1',25),
                 ('first_both_stop',26),('stable_start',27),('after_stable',15),('force_release_observed',21)]}
            force['raw_error_after_start_us']=[round((calibrated(r['cycles'])-start)*1e6,3) for r in raw_errors]
        evidence['force_rx_proof']=force
        evidence['event_semantics'].update({'405':'Before physical early PEN/data enable',
            '406':'After physical early PEN/data enable','437':'Before no-op early lane check; not physical enable',
            '438':'After no-op early lane check; not physical enable'})
        # Do not give the diagnostic no-op timestamps misleading physical-enable names.
        for key in list(calibrated_phases):
            if 'enable_end' in key:
                calibrated_phases[key.replace('enable_end','early_lane_check_end')]=calibrated_phases.pop(key)
        for key in list(markers):
            if 'data_enable' in key:
                markers[key.replace('data_enable','early_lane_check')]=markers.pop(key)
        for key in list(intervals):
            if 'data_enable' in key:
                intervals[key.replace('data_enable','early_lane_check')]=intervals.pop(key)
        cycles=evidence['header_cycles']
        for key in list(cycles):
            if 'data_enable' in key:
                cycles[key.replace('data_enable','early_lane_check')]=cycles.pop(key)
        stop=evidence['receiver_stop_qualification']
        stop['lane_check_to_qualification_cycles']=stop.pop('enable_to_qualification_cycles')
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
    lines = ['# Receiver-readiness evidence — October 17, 2026', '', config['checkpoint'], '',
        'Times are microseconds. START is the sensor START-write-end marker. '
        'STROBE and VSYNC use the existing Saleae-correlated firmware marker method; '
        'no new direct analog exposure measurement is implied.', '',
        '| Run | Outcome | Readiness condition | STOP dwell, nominal us | START → first STROBE | Arm → first VSYNC | First-frame identity supported | Raw errors |',
        '| --- | --- | --- | ---: | ---: | ---: | --- | --- |']
    for entry in ledger:
        summary, fast = entry['summary'], entry['fast_phy']
        condition = entry['readiness_parameters'].get('data_enable_readiness', 'START ACK and STREAMING; v36 baseline')
        dwell = entry['readiness_parameters'].get('stop_dwell_us', 100)
        row = [entry['experiment_id'], entry['outcome'], condition, str(dwell)]
        if not summary:
            row += ['unavailable'] * 4
        else:
            row += [str(summary['intervals_us']['start_write_end_to_first_strobe']),
                    str(fast.get('marker_intervals', {}).get('armed_to_first_vsync_us')),
                    str(fast.get('first_frame_identity_supported')),
                    str(len(fast.get('raw_error_records', []))) + ' sampled records']
        lines.append('| ' + ' | '.join(row) + ' |')
    lines += ['', 'Raw errors are decoded independently of HAL callback counts and interrupt-enable masks. '
        'Zero retained errors does not constitute a continuous electrical trace or production-corner guarantee. '
        'A supported first-frame identity combines STROBE ordinal, frame ordering and complete native-byte integrity; '
        'it is not embedded sensor frame-ID readback. Visual assertions are separate.', '',
        'Event 250 retains an obsolete raw label in some captures; it means receiver configuration complete. '
        'Actual arm uses event 22 and FAST snapshot 422. Original raw labels remain unchanged.', '',
        'For EARLY/ForceRx modes 4, 5 and 6, physical data enable is bracketed by FAST 405/406. '
        'Events 437/438 are only no-op lane checks. The raw ForceRx proof is decoded separately. '
        'The retained-both-lanes ForceRx trial did not receive any frame, although exposure strobes continued and raw error flags stayed zero. '
        'Its original capture failure and unreached shutdown proof are retained; offline timing/rail analysis does not change its failed outcome.', '',
        'The recovery checks intentionally held PE0 low in the early park. Their generic first-GPIO analyzer '
        'failed its normal-boot marker and plateau expectations; that failure is retained. '
        'The exact prefix/park check and recorded rail discharge/restoration separately support the intended recovery result. '
        'See recovery-checks.json and the original qualification and inspection records.', '',
        'The selected lane-1 ForceRx sequence keeps the measured 100 us STOP qualification. '
        'Its two minimum-exposure trials provide 546.08–548.16 us arm-to-first-VSYNC margin. '
        'Moving PEN later by a measured 207.65–215.20 us left first observed both-lane STOP within 0.86–4.20 us of the controls, '
        'supporting a sensor/START-relative readiness event rather than a fixed PEN-relative delay. '
        'These are observations on this board, not an electrical timing bound over production corners.', '',
        'Final installed sector SHA-256: `'+config['final_program_sha256']+'`. '
        'Final normal capture, autonomous recovery park and post-release powered-state checks are retained separately. '
        'The latter observed stable rails for 3.019808 s after the JS110 session closed, with OUT0 settings restored to 3300 mV/HIGH.', '',
        'Validation reported by the owning bench agent: 15 ready_phy offline tests and 10 exact full-prefix/sector allowlist checks passed. '
        'Archive byte/provenance validation is performed independently by this archiver.', '',
        '- [Ledger](ledger.json)', '- [Source provenance](source-provenance.json)',
        '- [Visual review assertions](visual-review.json)', '- [Archive hash index](archive-index.json)', '',
        'Only explicitly completed or explicitly identified failed experiments are included. '
        'Frozen source bytes and manifests are attributed by SHA-256; unchanged sources may refer to verified objects in earlier archives. '
        'Generator-input fingerprints are retained even when an earlier generator revision is no longer available as bytes.', '',
        'Frame pixels/images, analog CSVs and full Logic recordings remain local and are excluded. '
        'Compact status buffers, JSON, digital event CSVs, programming verification and licenses are retained. '
        'Run firmware/capture-timing/verify_evidence.py to verify archived bytes without local capture originals.', '']
    return '\n'.join(lines).encode('utf-8')



def derive_failed_timing(logic,result):
    """Pure offline continuation after a failed capture skipped its analyzers."""
    import csv
    from collections import deque
    from statistics import median
    helper=DEST/'extra/analyze.py'
    if not helper.exists():helper=ROOT/'firmware/capture-timing/analyze.py'
    spec=importlib.util.spec_from_file_location('ready_archive_analyze',helper)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    analog=logic/'analog.csv';recent=deque();longest=0.;begin=None;window=None
    with analog.open(encoding='utf-8-sig',newline='') as stream:
        for row in csv.DictReader(stream):
            stamp=float(row['Time [s]'])
            values=[float(row['Channel '+str(ch)]) for ch in (3,4,5)]
            recent.append((stamp,values))
            while recent and recent[0][0]<stamp-.5:recent.popleft()
            if all(v<.1 for v in values):
                if begin is None:begin=stamp
                if stamp-begin>longest:longest=stamp-begin;window=(begin,stamp)
            else:begin=None
    final={str(ch):dict(min_v=min(r[1][i] for r in recent),max_v=max(r[1][i] for r in recent),
        median_v=median(r[1][i] for r in recent)) for i,ch in enumerate((3,4,5))}
    passed=bool(window and longest>=1 and all(final[str(ch)]['min_v']>=low and
        final[str(ch)]['max_v']<=high for ch,low,high in [(3,3,3.6),(4,4.5,5.5),(5,3,3.6)]))
    if not passed:raise ValueError('Failed capture has insufficient independent rail evidence')
    with analog.open('rb') as source:analog_hash=hashlib.file_digest(source,'sha256').hexdigest()
    rail=dict(passed=passed,common_off_s=longest,common_off_window_s=window,final=final,
        derivation='Offline after original cold_experiment failed; no hardware accessed and original failure retained',
        analog_source_sha256=analog_hash,
        limitation='Only the three measured rails are qualified; no direct core/always-on rail probe')
    timing=module.correlate(module.transitions(logic/'digital.csv'),result,mode='cold',after_s=sum(window)/2)
    return timing,rail

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
        timing_document=read_json(timing_path) if timing_path.exists() else None
        derived_rail=None
        if item.get('derive_failed_timing'):
            if item['outcome']!='failed' or timing_document is not None:
                raise ValueError('Offline failed analysis must not replace a completed/original timing result')
            timing_document,derived_rail=derive_failed_timing(logic,result)
            plan.generated(archive/'timing-derived-after-failure.json',timing_document)
            plan.generated(archive/'rail-derived-after-failure.json',derived_rail)
        if result is not None and timing_document is not None:
            try:
                entry['summary'] = summarize_documents(timing_document, result)
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
        entry['rail_validation'] = read_json(rail) if rail.exists() else derived_rail
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
        entry['readiness_parameters'] = {key: receiver[key] for key in
            ('data_enable_readiness','stop_dwell_us','stop_dwell_cycles','data_stop_state_required',
             'force_rx','force_rx_us','coarse_lines','force_rx_retained','physical_data_enable',
             'data_check_events_are_lane_enable','pre_pen_delay_us','pre_pen_delay_cycles',
             'pre_pen_delay_location','force_rx_retained_mask') if key in receiver}
        entry['recovery_guard'] = guard_evidence(prefix)
        entry['fast_phy'] = fast_evidence(plan, item, archive, receiver, entry['summary'],
                                        timing_document)
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
        if item.get('qualified_park_with_generic_inspection_failure'):
            qualification_path=directory/'qualification.json'
            qualification=read_json(qualification_path) if qualification_path.exists() else None
            generic = read_json(directory / 'logic/independent-review.json')
            outcome = read_json(directory / 'logic/cycle-outcome.json')
            off = generic['common_continuous_off_below_0_1_v']['duration_s']
            rails = generic['final_levels']
            if not (generic.get('passed') is False and outcome.get('passed') is False
                    and outcome['cycle_returncode'] == outcome['capture_returncode'] == 0
                    and outcome['inspection_returncode'] == 1
                    and generic['checks']['continuous_common_off_at_least_minimum'] is True
                    and generic['checks']['rail_90pct_crossings_sustained_through_end'] is True
                    and off >= 1
                    and rails['3']['min_v'] >= 2.97 and rails['3']['max_v'] <= 3.63
                    and rails['4']['min_v'] >= 4.5 and rails['4']['max_v'] <= 5.5
                    and rails['5']['min_v'] >= 2.97 and rails['5']['max_v'] <= 3.63):
                raise ValueError(f'Qualified recovery evidence mismatch: {name}')
            if qualification and not (qualification.get('recovery_park_passed') is True
                    and qualification.get('generic_capture_cycle_exit_code') == 1
                    and qualification.get('generic_inspection_passed') is False
                    and abs(off-qualification['common_rail_off_seconds']) < 1e-6
                    and qualification['exact_live_prefix_sha256']==result['prefix_sha256']
                    and int(qualification['verified_park_address'],16)==result['context']['PC']):
                raise ValueError(f'Supplied recovery qualification differs from primary records: {name}')
            rail = dict(generic_inspection_passed=False,
                intended_park_rail_evidence_verified=True, qualification=qualification,
                interpretation='Generic inspection remains failed; independent exact park and the retained rail subset support the intended recovery check')
            rail_ok = True
        else:
            rail = read_json(directory / 'logic/rail-validation.json')
            rail_ok = rail.get('passed') is True
        live_hash = digest((directory / 'park/live-prefix.bin').read_bytes())
        expected_pc = int(prefix['recovery_gpio']['park_address'], 16)
        if not (result.get('passed') is True and rail_ok
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
    if config.get('final_state_directory'):
        if config['final_program_sha256'] != builds[config['final_prefix_build']][1]['program_sha256']:
            raise ValueError('Final selected sector fingerprint differs from frozen manifest')
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
    plan.copy(DEST / 'prepare-archive.py', Path('prepare-archive.py'))
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
