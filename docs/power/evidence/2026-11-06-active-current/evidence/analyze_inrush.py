"""Read-only JS110 analysis; no instrument imports, commands, or historical writes.

Reads completed recorder result.json/chunks.jsonl with f32 analog, packed u1
GPIO and expanded u8 range streams. Outputs are confined to this campaign.
Native IDs, not callback timestamps or file offsets, align signals. An invalid
or incomplete window never receives an energy/charge integral.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import numpy as np

HERE = Path(__file__).resolve().parent
FS = 2_000_000
NAMES = {1: 'receiver_entry', 2: 'first_strobe_irq_observed',
    3: 'first_frame_complete_irq_observed', 4: 'sd_initialization_begin',
    5: 'sd_initialization_complete', 6: 'first_slot_transport_submission',
    7: 'slot_transport_returned_success', 8: 'full_slot_commit_complete',
    9: 'sd_deinitialization_complete', 10: 'pre_standby_wfi',
    11: 'sensor_autonomous_standby_first_observed'}
PRECEDENCE = ((1, 2), (2, 3), (1, 4), (4, 5), (5, 6), (6, 7),
              (3, 7), (7, 8), (8, 9), (9, 10))
RANGES = {0: '10A', 1: '2A', 2: '180mA', 3: '18mA', 4: '1.8mA',
          5: '180uA', 6: '18uA', 7: 'OFF'}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def load_trace(folder):
    folder = Path(folder).resolve()
    result = json.loads((folder / 'result.json').read_text())
    require(result.get('success') is True, 'Recorder did not report success')
    require(not result.get('errors') and not result.get('cleanup_errors'),
            'Recorder errors/cleanup errors are not a completed recording')
    rows = [json.loads(line) for line in (folder / 'chunks.jsonl').read_text().splitlines() if line]
    signals, checks = {}, {}
    for name in ('current', 'voltage', 'power', 'gpi0', 'gpi1', 'current_range'):
        chunks = [row for row in rows if row['signal'] == name]
        if not chunks:
            require(name not in ('current', 'voltage', 'power'), 'Missing analog stream: ' + name)
            continue
        gpio, rng = name.startswith('gpi'), name == 'current_range'
        extension = '.u1' if gpio else '.u8' if rng else '.f32'
        path = folder / (name + extension)
        digest = sha(path)
        require(digest == result['sha256'][name], 'Hash mismatch: ' + name)
        raw = np.memmap(path, mode='r', dtype='u1' if gpio or rng else '<f4')
        offset, pieces = 0, []
        for index, row in enumerate(chunks):
            require(row['byte_offset'] == offset, 'File offset discontinuity: ' + name)
            require(row['sample_rate'] == FS and row['decimate_factor'] == 1,
                    'Expected native 2 MS/s stream: ' + name)
            size = int(row['byte_count'])
            require(size >= 0 and (gpio or rng or size % 4 == 0), 'Invalid byte count: ' + name)
            count = size * 8 if gpio else size if rng else size // 4
            if index + 1 < len(chunks):
                delta = int(chunks[index + 1]['sample_id']) - int(row['sample_id'])
                padding = count - delta
                require(delta >= 0 and 0 <= padding <= (7 if gpio else 1 if rng else 0),
                        'Native sample gap/overlap: ' + name)
                count = delta
            elif gpio or rng:
                # Last packed chunk lacks a subsequent ID to resolve padding.
                count = 0
            if gpio:
                pieces.append(np.unpackbits(raw[offset:offset + size], bitorder='little')[:count])
            elif rng:
                pieces.append(np.asarray(raw[offset:offset + count]))
            offset += size
        require(offset == path.stat().st_size, 'Unindexed source bytes: ' + name)
        data = np.concatenate(pieces) if gpio or rng else raw
        if rng:
            require(not len(data) or int(data.max()) <= 7, 'Unknown range code')
        start = int(chunks[0]['sample_id'])
        signals[name] = (start, data)
        checks[name] = dict(path=str(path), sha256=digest, hash_passed=True,
            native_contiguity_passed=True, first_sample_id=start,
            analyzed_end_exclusive=start + len(data), analyzed_samples=len(data),
            source_bytes=offset, source_chunks=len(chunks),
            last_chunk_excluded=bool(gpio or rng),
            nonfinite_samples=None if gpio or rng else int(np.count_nonzero(~np.isfinite(data))))
    return signals, checks, result


def slice_signal(signals, name, start, end):
    require(end >= start, 'Reversed sample window')
    if name not in signals:
        return None
    origin, data = signals[name]
    if start < origin or end > origin + len(data):
        return None
    return data[start - origin:end - origin]


def metrics(signals, start, end, onset):
    start, end = int(start), int(end)
    out = dict(start_sample_id=start, end_sample_id_exclusive=end,
        start_ms=(start - onset) / FS * 1000, end_ms=(end - onset) / FS * 1000,
        duration_ms=(end - start) / FS * 1000, valid=end > start, streams={})
    for name in ('current', 'voltage', 'power'):
        values = slice_signal(signals, name, start, end)
        valid = values is not None and len(values) > 0 and bool(np.all(np.isfinite(values)))
        out['streams'][name] = dict(covered=values is not None, finite=valid,
            nonfinite_samples=None if values is None else int(np.count_nonzero(~np.isfinite(values))))
        out['valid'] = out['valid'] and valid
        if valid:
            out[name + '_mean'] = float(np.mean(values, dtype=np.float64))
            out[name + '_min'] = float(np.min(values))
            out[name + '_max'] = float(np.max(values))
    if out['valid']:
        current = slice_signal(signals, 'current', start, end)
        power = slice_signal(signals, 'power', start, end)
        out.update(current_mean_mA=out['current_mean'] * 1000,
            charge_mC=float(np.sum(current, dtype=np.float64) / FS * 1000),
            positive_charge_mC=float(np.sum(current[current > 0], dtype=np.float64) / FS * 1000),
            negative_charge_mC=float(np.sum(current[current < 0], dtype=np.float64) / FS * 1000),
            energy_mJ=float(np.sum(power, dtype=np.float64) / FS * 1000))
        peak_id = start + int(np.argmax(current))
        out['native_peak_unqualified'] = dict(sample_id=peak_id,
            time_from_onset_us=(peak_id - onset) / FS * 1e6,
            current_A=float(current[peak_id - start]),
            source_voltage_V=float(slice_signal(signals, 'voltage', peak_id, peak_id + 1)[0]))
        threshold_metrics = {}
        for threshold in (0.1, 0.5, 1, 3, 5, 7):
            above = current > threshold
            edges = np.flatnonzero(np.diff(np.r_[False, above, False].astype(np.int8)))
            runs = edges.reshape(-1, 2)
            threshold_metrics[str(threshold)] = dict(samples=int(above.sum()),
                duration_us=float(above.sum() / FS * 1e6),
                longest_contiguous_us=float(np.max(runs[:, 1] - runs[:, 0]) / FS * 1e6) if len(runs) else 0,
                episodes=len(runs),
                first_time_us=float((start + runs[0, 0] - onset) / FS * 1e6) if len(runs) else None,
                last_end_time_us=float((start + runs[-1, 1] - onset) / FS * 1e6) if len(runs) else None)
        out['current_above_A'] = threshold_metrics
    ranges = slice_signal(signals, 'current_range', start, end)
    out['range_covered'] = ranges is not None
    if ranges is not None:
        out['range_counts'] = {str(int(v)): int(n) for v, n in zip(*np.unique(ranges, return_counts=True))}
        if out['valid']:
            out['native_peak_unqualified']['range_code'] = int(ranges[out['native_peak_unqualified']['sample_id'] - start])
    return out


def select_onset(signals, threshold=0.020, index=None, explicit=None):
    origin, current = signals['current']
    candidates = []
    if explicit is not None:
        require(slice_signal(signals, 'current', explicit, explicit + 1) is not None, 'Explicit onset outside source')
        chosen = dict(sample_id=int(explicit), method='Explicit analysis sample ID; not independently verified power-good')
    else:
        if 'current_range' in signals:
            rs, values = signals['current_range']
            changes = np.flatnonzero((values[:-1] == 7) & (values[1:] < 7)) + 1
            for position in changes:
                on = rs + int(position)
                lo, hi = max(origin, on - 20), min(origin + len(current), on + FS // 20)
                part = current[lo - origin:hi - origin]
                hits = np.flatnonzero(np.isfinite(part) & (part >= threshold))
                if len(hits):
                    candidates.append(dict(sample_id=lo + int(hits[0]), range_on_sample_id=on,
                        method='First current threshold near observed range OFF-to-ON; search -10us to +50ms'))
        if not candidates:
            finite_high = np.isfinite(current) & (current >= threshold)
            rises = np.flatnonzero(finite_high[1:] & ~finite_high[:-1]) + 1
            for position in rises:
                if position < FS // 1000:
                    continue
                previous = current[position - FS // 1000:position]
                if np.all(np.isfinite(previous)) and abs(float(np.mean(previous, dtype=np.float64))) < .0001:
                    candidates.append(dict(sample_id=origin + int(position),
                        method='Current threshold following finite 1ms with absolute mean below100uA; no usable range edge'))
        # Repeated OFF/ON records must be explicitly indexed, never guess a run.
        require(candidates, 'No current onset candidate; use --onset-sample only with independent evidence')
        require(index is not None or len(candidates) == 1,
                'Multiple onset candidates; use --on-index: ' + json.dumps(candidates))
        chosen = dict(candidates[index if index is not None else 0])
    onset = chosen['sample_id']
    chosen['threshold_A'] = threshold
    chosen['candidate_count'] = len(candidates)
    chosen['candidates'] = candidates
    chosen['pre_onset_1ms'] = metrics(signals, onset - FS // 1000, onset, onset)
    chosen['prior_1ms_abs_mean_below_100uA'] = bool(chosen['pre_onset_1ms']['valid'] and
        abs(chosen['pre_onset_1ms']['current_mean']) < .0001)
    if 'range_on_sample_id' in chosen:
        chosen['current_threshold_after_range_on_us'] = (onset - chosen['range_on_sample_id']) / FS * 1e6
    return onset, chosen


def edges(signals, name):
    if name not in signals:
        return []
    start, values = signals[name]
    indices = np.flatnonzero(values[1:] != values[:-1]) + 1
    return [dict(sample_id=start + int(i), level=int(values[i])) for i in indices]


def decode_markers(signals, onset, mode='auto'):
    ee = edges(signals, 'gpi0')
    pulses = []
    for rise, fall in zip(ee, ee[1:]):
        if rise['level'] == 1 and fall['level'] == 0:
            width = (fall['sample_id'] - rise['sample_id']) / FS * 1e6
            ids = [i for i in NAMES if abs(width - (2 * i + .24)) <= .80]
            pulses.append(dict(sample_id=rise['sample_id'], end_sample_id=fall['sample_id'],
                width_us=width, matching_ids=ids))
    trains = []
    for count in ((11, 10) if mode == 'auto' else (int(mode),)):
        expected = list(range(1, count + 1))
        precedence = PRECEDENCE + (((3, 11), (11, 8)) if count == 11 else ())
        for pos, pulse in enumerate(pulses):
            if pulse['matching_ids'] != [1] or pulse['sample_id'] < onset:
                continue
            train = pulses[pos:pos + count]
            if len(train) != count or any(len(x['matching_ids']) != 1 for x in train):
                continue
            if sorted(x['matching_ids'][0] for x in train) != expected:
                continue
            by = {x['matching_ids'][0]: x for x in train}
            if all(by[a]['sample_id'] < by[b]['sample_id'] for a, b in precedence):
                trains.append(train)
    out = dict(available='gpi0' in signals, unique_complete_train=len(trains) == 1,
        complete_train_count=len(trains), total_edges=len(ee), total_pulses=len(pulses),
        pulse_rule='Native0.5us grid, abs(width_us-(2*ID+0.24))<=0.80; contiguous unique10/11-ID train with semantic precedence',
        events=[], unclassified_pulse_preview=pulses[:200], preview_truncated=len(pulses) > 200)
    if len(trains) == 1:
        train = trains[0]
        out['events'] = [dict(id=x['matching_ids'][0], name=NAMES[x['matching_ids'][0]],
            time_ms=(x['sample_id'] - onset) / FS * 1000, **x) for x in train]
        extra = [x for x in pulses if x not in train]
        out['unclassified_pulse_count'] = len(extra)
        out['unclassified_pulse_preview'] = extra[:200]
        out['preview_truncated'] = len(extra) > 200
    return out


def cycle_metrics(signals, marker_result, onset):
    if not marker_result['unique_complete_train']:
        return dict(available=False, reason='No unique complete marker train; no cycle completion inferred')
    by = {x['id']: x for x in marker_result['events']}
    windows = {}
    for name, a, b in [('receiver_to_strobe', 1, 2), ('strobe_to_frame', 2, 3),
        ('SD_init', 4, 5), ('scan_preparation', 5, 6), ('slot_transport', 6, 7),
        ('commit', 7, 8), ('SD_deinit', 8, 9), ('cleanup', 9, 10)]:
        windows[name] = metrics(signals, by[a]['sample_id'], by[b]['sample_id'], onset)
    if 11 in by:
        windows['frame_to_sensor_standby_observed'] = metrics(signals, by[3]['sample_id'], by[11]['sample_id'], onset)
    result = dict(available=True, phase_windows_overlapping_not_additive=windows,
        onset_to_pre_Standby_raw_unqualified=metrics(signals, onset, by[10]['sample_id'], onset),
        post5ms_to_pre_Standby=metrics(signals, onset + FS // 200, by[10]['sample_id'], onset))
    # Tail-defined plateau supports the changed3.3mA hardware without assuming
    # the old6..12mA plateau. Still an analog signature, not a Standby proof.
    cs, current = signals['current']
    end = min(signals[n][0] + len(signals[n][1]) for n in ('current', 'voltage', 'power'))
    tail_start = end - FS // 10
    tail = metrics(signals, tail_start, end, onset)
    result['recording_tail_100ms'] = tail
    result['plateau_available'] = False
    if tail['valid'] and -.001 < tail['current_mean'] < .020 and tail_start > by[10]['end_sample_id']:
        bin0 = ((by[10]['end_sample_id'] + 1999) // 2000) * 2000
        count = (end - bin0) // 2000
        if count >= 10:
            values = current[bin0 - cs:bin0 - cs + count * 2000].reshape(count, 2000)
            finite = np.all(np.isfinite(values), axis=1)
            means = np.mean(values, dtype=np.float64, axis=1)
            good = finite & (np.abs(means - tail['current_mean']) <= .002)
            candidates = np.flatnonzero(np.convolve(good.astype(int), np.ones(10, dtype=int), 'valid') == 10)
            for position in candidates:
                if np.ptp(means[position:position + 10]) > .002:
                    continue
                plateau = bin0 + int(position) * 2000
                if plateau + FS // 10 > end:
                    continue
                result.update(plateau_available=True, plateau_sample_id=plateau,
                    plateau_rule='First10 consecutive1ms means within2mA of finite last100ms mean<20mA, with2mA spread;1ms endpoint resolution',
                    low_plateau_100ms=metrics(signals, plateau, plateau + FS // 10, onset),
                    onset_to_plateau_raw_unqualified=metrics(signals, onset, plateau, onset),
                    post5ms_to_plateau=metrics(signals, onset + FS // 200, plateau, onset))
                break
    result['scope'] = 'GPIO observations and analog plateau only; no fresh SBF, image-readback, per-device power or physical inrush qualification'
    return result


def analyze(trace, onset_sample=None, on_index=None, threshold=.020, markers='auto'):
    trace = Path(trace).resolve()
    signals, checks, recorder = load_trace(trace)
    onset, selection = select_onset(signals, threshold, on_index, onset_sample)
    marker_result = decode_markers(signals, onset, markers)
    windows = {str(ms) + 'ms': metrics(signals, onset, onset + round(ms / 1000 * FS), onset)
               for ms in (.25, 1, 5)}
    range_edges = [dict(**edge, time_ms=(edge['sample_id'] - onset) / FS * 1000)
                   for edge in edges(signals, 'current_range')
                   if onset - FS // 1000 <= edge['sample_id'] <= onset + FS // 100]
    out = dict(schema=1, run=trace.name, trace=str(trace), sample_rate_Hz=FS,
        source_index_sha256=sha(trace / 'chunks.jsonl'), result_sha256=sha(trace / 'result.json'),
        analysis_source_sha256=sha(Path(__file__)), checks=checks,
        recorded_on_range=recorder.get('on_range'),
        settings_before=recorder.get('initial_settings'), settings_restored=recorder.get('restored_settings'),
        current_onset=selection, startup_windows_raw_unqualified=windows,
        pre_onset_1ms=metrics(signals, onset - FS // 1000, onset, onset),
        range_changes_minus1_to_plus10ms=range_edges, stream_range_codes=RANGES,
        range_control_distinction='Control1=fixed10A,128=auto,0=OFF; stream0=10A,7=OFF',
        marker_decode=marker_result, cycle=cycle_metrics(signals, marker_result, onset),
        first5ms_qualified=False, clipping_independently_qualified=False,
        limitations=[
            'Current threshold is not measured power-good, reset release or exact switch closure.',
            'IN voltage is source-side; no target voltage ramp or target droop is inferred.',
            'Native extrema and initial startup integrals remain unqualified; range controls cannot validate analog switch response or clipping.',
            'Digital/range final chunks excluded because terminal padding lacks an independent next sample ID.',
            'An unclassified GPIO pulse is retained as evidence, never silently assigned a phase.',
            'Phase timing does not isolate individual component power; no image integrity, fresh Standby flag or sensor counter proof follows.',
            'No historical source file or recording is modified; all outputs belong to this campaign.'])
    profile = []
    for j in range(-100, 1000):
        a, b = onset + j * 20, onset + (j + 1) * 20
        m = metrics(signals, a, b, onset)
        profile.append(dict(time_us=(j + .5) * 10, valid=m['valid'],
            current_mean_A=m.get('current_mean'), current_max_A=m.get('current_max'),
            voltage_mean_V=m.get('voltage_mean'), power_mean_W=m.get('power_mean'),
            charge_mC=m.get('charge_mC'), range_codes=','.join(m.get('range_counts', {}))))
    return out, profile


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--trace', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True, help='New JSON output within inrush-20261105')
    ap.add_argument('--onset-sample', type=int)
    ap.add_argument('--on-index', type=int)
    ap.add_argument('--threshold-A', type=float, default=.020)
    ap.add_argument('--markers', choices=('auto', '10', '11'), default='auto')
    args = ap.parse_args()
    dest = args.out.resolve()
    dest.relative_to(HERE)
    require(not dest.exists(), 'Output already exists: choose a new name')
    profile = dest.with_suffix('.10us.csv')
    require(not profile.exists(), 'Profile output already exists')
    report, rows = analyze(args.trace, args.onset_sample, args.on_index, args.threshold_A, args.markers)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')
    with profile.open('x', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(dict(output=str(dest), onset=report['current_onset']['sample_id'],
        first5ms=report['startup_windows_raw_unqualified']['5ms'],
        markers=[x['id'] for x in report['marker_decode']['events']],
        cycle_available=report['cycle']['available']), indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
