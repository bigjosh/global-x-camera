"""Prepare the explicit completed-run receiver-readiness archive checkpoint.

No hardware access. The archive itself is published separately, after validation.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
base = (HERE.parent / '2026-10-17-fast-phy/archive-script.py').read_text()
start = base.index('def checkpoint_readme(')
end = base.index('\ndef main():', start)
readme = '''def checkpoint_readme(config, ledger):
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
    return '\\n'.join(lines).encode('utf-8')

'''
base = base[:start] + readme + base[end:]
# A checkpoint can be prepared while the owning hardware task is still running.
begin = base.index("    final_directory = repo_path(config['final_state_directory'])")
finish = base.index('    license_path = EVIDENCE', begin)
base = base[:begin] + "    if config.get('final_state_directory'):\n" + ''.join(
    '    ' + line if line.strip() else line for line in base[begin:finish].splitlines(keepends=True)) + base[finish:]
base = base.replace("        final_directory = repo_path(config['final_state_directory'])", """        if config['final_program_sha256'] != builds[config['final_prefix_build']][1]['program_sha256']:
            raise ValueError('Final selected sector fingerprint differs from frozen manifest')
        final_directory = repo_path(config['final_state_directory'])""")
base = base.replace("        entry['recovery_guard'] = guard_evidence(prefix)", """        entry['readiness_parameters'] = {key: receiver[key] for key in
            ('data_enable_readiness','stop_dwell_us','stop_dwell_cycles','data_stop_state_required',
             'force_rx','force_rx_us','coarse_lines','force_rx_retained','physical_data_enable',
             'data_check_events_are_lane_enable','pre_pen_delay_us','pre_pen_delay_cycles',
             'pre_pen_delay_location','force_rx_retained_mask') if key in receiver}
        entry['recovery_guard'] = guard_evidence(prefix)""")
base = base.replace("    mode = {'early': 0, 'streaming': 1}[receiver['data_enable']]", """    mode = {'early': 0, 'streaming': 1, 'ack': 2, 'timed': 3,
            'early_stop': 4, 'force_stop': 5, 'force_lane1': 6}[receiver['data_enable']]
    if mode >= 2 and receiver.get('readiness_gate') != mode:
        raise ValueError('Manifest lacks the explicit reviewed readiness gate')""")
base = base.replace("    evidence = dict(status='verified raw buffer and matching build'", """    calibrated_phases = {}
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
    evidence = dict(status='verified raw buffer and matching build'""")
base = base.replace("        shutdown=shutdown, records=records)", """        shutdown=shutdown, calibrated_phase_intervals=calibrated_phases,
        data_enable_cycles_are_physical_lane_enable=mode not in (4,5,6),
        receiver_stop_qualification=dict(reported_sr1=header[20], cycle=header[21],
            both_data_stop_flags=bool((header[20]&0x02080000)==0x02080000),
            nominal_dwell_cycles=receiver.get('stop_dwell_cycles',40000),
            enable_to_qualification_cycles=(header[21]-header[12])&0xffffffff,
            qualification='Receiver-reported STOP status; this is not independent electrical LP-11 proof'),
        calibration_method='Raw DWT timestamps interpolated between adjacent matched Saleae marker events; estimates, not new electrical measurements',
        records=records)""")
force_support = '''    if mode in (4,5,6):
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
'''
base = base.replace("    plan.generated(archive / 'fast-derived.json', evidence)", force_support+"    plan.generated(archive / 'fast-derived.json', evidence)")
base = base.replace("    if receiver.get('shutdown_data_off'):", "    if receiver.get('shutdown_data_off') and not item.get('shutdown_not_reached'):")
base = base.replace("    calibrated_phases = {}", """    if item.get('shutdown_not_reached'):
        if item['outcome'] != 'failed':
            raise ValueError('Unreached shutdown exception requires explicit failed outcome')
        uninitialized=(directory/'shutdown.bin').read_bytes()
        shutdown=dict(status='not reached; raw uninitialized buffer preserved without register interpretation',
            completed=False,raw_sha256=digest(uninitialized),bytes=len(uninitialized))
    calibrated_phases = {}""")
offline_support = '''
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

'''
base = base.replace('def main():',offline_support+'def main():')
base = base.replace("        if result is not None and timing_path.exists():", """        timing_document=read_json(timing_path) if timing_path.exists() else None
        derived_rail=None
        if item.get('derive_failed_timing'):
            if item['outcome']!='failed' or timing_document is not None:
                raise ValueError('Offline failed analysis must not replace a completed/original timing result')
            timing_document,derived_rail=derive_failed_timing(logic,result)
            plan.generated(archive/'timing-derived-after-failure.json',timing_document)
            plan.generated(archive/'rail-derived-after-failure.json',derived_rail)
        if result is not None and timing_document is not None:""")
base = base.replace("summarize_documents(read_json(timing_path), result)","summarize_documents(timing_document, result)")
base = base.replace("entry['rail_validation'] = read_json(rail) if rail.exists() else None", "entry['rail_validation'] = read_json(rail) if rail.exists() else derived_rail")
base = base.replace("read_json(timing_path) if timing_path.exists() else None)","timing_document)")
base = base.replace("    plan.copy(Path(__file__).resolve(), Path('archive-script.py'))", "    plan.copy(Path(__file__).resolve(), Path('archive-script.py'))\n    plan.copy(DEST / 'prepare-archive.py', Path('prepare-archive.py'))")
base = base.replace("        rail = read_json(directory / 'logic/rail-validation.json')", """        if item.get('qualified_park_with_generic_inspection_failure'):
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
            rail_ok = rail.get('passed') is True""")
base = base.replace("result.get('passed') is True and rail.get('passed') is True", "result.get('passed') is True and rail_ok")

HERE.joinpath('archive-script.py').write_text(base, encoding='utf-8', newline='\n')

config = dict(schema=1, date='2026-10-17',
    checkpoint='Final hardware checkpoint: fourteen trials, including the failed retained-both-lanes ForceRx case, three autonomous recovery checks, and a released, powered final default configuration.',
    scope='Receiver readiness without delaying the sensor START command: minimum-exposure baseline and bounded data-lane enable/STOP qualification experiments.',
    builds=[], captures=[], extra_files=[dict(source='firmware/capture-timing/summarize.py', archive='summarize.py'),
        dict(source='firmware/capture-timing/analyze.py',archive='analyze.py')])
rows = [
    ('v36-coarse5-baseline-01', 'capture-phy-fast-v36-shutdown-coarse5-20261017', 'phy-ready-v36-coarse5-baseline-01'),
    ('v37-streaming-stop10-install-01', 'capture-phy-ready-v37-streaming-stop10-coarse5-20261017', 'phy-ready-v37-streaming-stop10-install-01'),
    ('v37-streaming-stop0-install-01', 'capture-phy-ready-v37-streaming-stop0-coarse5-20261017', 'phy-ready-v37-streaming-stop0-install-01'),
    ('v38a-ack-stop0-install-01', 'capture-phy-ready-v38a-ack-stop0-coarse5-20261017', 'phy-ready-v38a-ack-stop0-install-01'),
    ('v38b-ack-default-install-01', 'capture-phy-ready-v38b-ack-stop0-default-20261017', 'phy-ready-v38b-ack-default-install-01'),
    ('v39-early-stop100-install-01', 'capture-phy-ready-v39-early-stop100-coarse5-20261017', 'phy-ready-v39-early-stop100-install-01'),
    ('v39-force-stop100-install-01', 'capture-phy-ready-v39-force-stop100-coarse5-20261017', 'phy-ready-v39-force-stop100-install-01'),
    ('v41-lane1-stop100-install-01', 'capture-phy-ready-v41-force-lane1-stop100-coarse5-20261017', 'phy-ready-v41-lane1-stop100-install-01'),
    ('v42-both-stop0-install-01', 'capture-phy-ready-v42-force-stop0-coarse5-20261017', 'phy-ready-v42-both-stop0-install-01'),
    ('v43-lane1-pen200-install-01', 'capture-phy-ready-v43-force-lane1-stop100-pen200-coarse5-20261017', 'phy-ready-v43-lane1-pen200-install-01'),
    ('v41-default-install-01', 'capture-phy-ready-v41-force-lane1-stop100-default-20261017', 'phy-ready-v41-default-install-01'),
]
for name, build, capture in rows:
    for part in ['receiver','staged']:
        config['builds'].append(dict(id=name+'-'+part, directory='tmp/bringup/'+build+'/'+part))
    directory = 'tmp/bringup/'+capture
    item = dict(id=name, directory=directory+'/cold', fast_directory=directory+'/fast',
        receiver_build=name+'-receiver', prefix_build=name+'-staged', outcome='completed',
        programming_cycle_directory=directory)
    if name == 'v37-streaming-stop0-install-01':
        item['visual_review'] = dict(reviewer='root agent',
            status='Dark minimum-exposure scene with distinct illuminated shapes/reflections; not blank and no visible gross corruption',
            provenance='Root message during this archive task: directly viewed completed STOP0 cold/ram/frame.png.')
    if name == 'v38b-ack-default-install-01':
        item['visual_review'] = dict(reviewer='root agent',
            status='Clear bench/room scene with lights, ceiling patterns, equipment and text; not blank and no visible gross corruption',
            provenance='Root message during this archive task: directly viewed completed ACK default frame.png. Actual scene described without assuming the earlier LED-panel orientation.')
    if name == 'v41-lane1-stop100-install-01':
        item['visual_review'] = dict(reviewer='root agent',
            status='Dark minimum-exposure scene with expected illuminated shapes and reflections; not blank and no obvious gross corruption',
            provenance='Root message during this archive task: directly reviewed completed v41 minimum frame.')
    if name == 'v41-default-install-01':
        item['visual_review'] = dict(reviewer='root agent',
            status='Clear room/bench scene with lights, equipment and text; no visible gross corruption',
            provenance='Root message during this archive task: directly viewed completed v41 default frame.png.')
    if name == 'v39-force-stop100-install-01':
        item.update(outcome='failed',fast_directory=directory+'/fast-failure',shutdown_not_reached=True,
            derive_failed_timing=True,outcome_note='No VSYNC or frame despite repeated sensor exposures; zero retained raw CSI errors is not capture success. Original cold experiment exit 1 and failed initial shutdown-proof read are retained.')
        config['extra_files'].append(dict(source=directory+'/cold.log',archive='v39-force-stop100-cold-failure.log'))
        for path in (ROOT/directory/'fast').iterdir():
            if path.is_file() and path.suffix in ('.json','.jsonl','.log','.bin'):
                config['extra_files'].append(dict(source=path.relative_to(ROOT).as_posix(),
                    archive='v39-force-stop100-initial-fast-attempt/'+path.name))
    config['captures'].append(item)
config['captures'].append(dict(id='v38a-ack-stop0-cold-02', directory='tmp/bringup/phy-ready-v38a-ack-stop0-cold-02',
    fast_directory='tmp/bringup/phy-ready-v38a-ack-stop0-cold-02/fast',
    receiver_build='v38a-ack-stop0-install-01-receiver', prefix_build='v38a-ack-stop0-install-01-staged',
    outcome='completed', programming_cycle_directory='tmp/bringup/phy-ready-v38a-ack-stop0-install-01'))
config['captures'].append(dict(id='v41-lane1-min-restore-02', directory='tmp/bringup/phy-ready-v41-lane1-min-restore-02/cold',
    fast_directory='tmp/bringup/phy-ready-v41-lane1-min-restore-02/fast',
    receiver_build='v41-lane1-stop100-install-01-receiver', prefix_build='v41-lane1-stop100-install-01-staged',
    outcome='completed', programming_cycle_directory='tmp/bringup/phy-ready-v41-lane1-min-restore-02'))
config['captures'].append(dict(id='v41-final-normal-02',directory='tmp/bringup/phy-ready-v41-final-normal-02',
    fast_directory='tmp/bringup/phy-ready-v41-final-normal-02/fast',
    receiver_build='v41-default-install-01-receiver',prefix_build='v41-default-install-01-staged',
    outcome='completed',programming_cycle_directory='tmp/bringup/phy-ready-v41-default-install-01'))
config['recovery_checks'] = [dict(id=name+'-recovery-01', directory='tmp/bringup/phy-ready-'+name+'-recovery-01',
    prefix_build=prefix+'-staged', qualified_park_with_generic_inspection_failure=True)
    for name,prefix in [('v38a','v38a-ack-stop0-install-01'),('v39','v39-force-stop100-install-01')]]
config['recovery_checks'].append(dict(id='v41-final-recovery-01', directory='tmp/bringup/phy-ready-v41-final-recovery-01',
    prefix_build='v41-default-install-01-staged',qualified_park_with_generic_inspection_failure=True))
config.update(final_state_directory='tmp/bringup/phy-ready-final-release-01',
    final_capture='v41-final-normal-02',final_prefix_build='v41-default-install-01-staged',
    final_program_sha256='c92ee95920009b188aef53645fce8e9bb6cb8bd34d78cf789d252037be16af2f')
for folder in ['phy-ready-session-01','phy-ready-session-02']:
    for name in ['release.json','session.jsonl']:
        config['extra_files'].append(dict(source='tmp/bringup/'+folder+'/'+name,archive=folder+'/'+name))
for name in ['powered-state.json','capture-config.json','boot-summary.json','digital.csv']:
    config['extra_files'].append(dict(source='tmp/bringup/phy-ready-final-release-01/'+name,
        archive='final-release/'+name))
for path in (ROOT/'firmware/capture-timing/ready_phy').iterdir():
    if path.is_file() and path.suffix in ('.py','.md'):
        config['extra_files'].append(dict(source=path.relative_to(ROOT).as_posix(),archive='ready_phy/'+path.name))
for name in ['read_ready_phy.py','ready_mailbox_02.py','ready_final_power.py','verify_ready_allowlist.py']:
    config['extra_files'].append(dict(source='tmp/bringup/'+name,archive='bench-helpers/'+name))
for path in ['firmware/capture-timing/recovery_gpio/check_park.py','firmware/boot-timing/nor_bench.py']:
    config['extra_files'].append(dict(source=path,archive='guard-helpers/'+Path(path).name))
HERE.joinpath('archive-config.json').write_text(json.dumps(config,indent=2)+'\n', encoding='utf-8')
print(HERE)
