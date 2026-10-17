"""Independently inspect one exported power cycle, without instrument access.

Usage: python firmware/boot-timing/inspect_cycle.py CAPTURE_DIRECTORY

Reads existing CSV/configuration files and writes independent-review.json.
CH0=NRST, CH1=PD0, CH2=PE0, CH3=auxiliary 3.3 V, CH4=target 5 V.
Requires a sustained measured off interval, ordered boot markers, and stable
final levels. This validates the measured waveforms, not unprobed MCU rails,
the external boot mode, or the absence of a debugger. No hardware libraries
are imported. A failed inspection still writes its findings and exits 1.
"""

from array import array
from bisect import bisect_left, bisect_right
import argparse
import csv
import json
import math
from pathlib import Path
import statistics


def read_csv(path, digital=False):
    times = array('d')
    values = [array('d') for _ in range(6)]
    with path.open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        required = ['Time [s]'] + [f'Channel {ch}' for ch in range(6)]
        if any(name not in (reader.fieldnames or []) for name in required):
            raise ValueError(f'{path.name}: expected six-channel Logic raw CSV')
        for row in reader:
            timestamp = float(row['Time [s]'])
            if not math.isfinite(timestamp) or (times and timestamp <= times[-1]):
                raise ValueError(f'{path.name}: timestamps must increase and be finite')
            times.append(timestamp)
            for ch in range(6):
                value = float(row[f'Channel {ch}'])
                if not math.isfinite(value) or (digital and value not in (0, 1)):
                    raise ValueError(f'{path.name}: invalid channel {ch} value')
                values[ch].append(value)
    if len(times) < 2:
        raise ValueError(f'{path.name}: insufficient samples')
    return times, values


def _inspect(folder, minimum_off_s=1.0):
    required = ['boot.sal', 'analog.csv', 'digital.csv', 'capture-config.json']
    missing = [name for name in required
               if not (folder / name).is_file() or not (folder / name).stat().st_size]
    if missing:
        raise ValueError(f'Missing or empty capture artifacts: {missing}')
    config = json.loads((folder / 'capture-config.json').read_text(encoding='utf-8-sig'))
    t, v = read_csv(folder / 'analog.csv')
    dt, dv = read_csv(folder / 'digital.csv', digital=True)
    edges = {ch: [[dt[i], int(dv[ch][i])] for i in range(1, len(dt))
                  if dv[ch][i] != dv[ch][i-1]] for ch in range(6)}
    rises = {ch: [ts for ts, level in edges[ch] if level] for ch in (0, 1, 2)}
    marker = {ch: ts[0] if len(ts) == 1 else None for ch, ts in rises.items()}
    nrst, pd0, pe0 = [marker[ch] for ch in (0, 1, 2)]
    anchor = min((ts for ts in marker.values() if ts is not None), default=t[-1])
    preceding_falls = [ts for ch in (0, 1, 2) for ts, level in edges[ch]
                       if not level and ts < anchor]
    lower = max(preceding_falls, default=t[0])

    def stats(ch, start, end):
        samples = v[ch][bisect_left(t, start):bisect_right(t, end)]
        if not samples:
            return None
        return {'samples': len(samples), 'median_v': statistics.median(samples),
                'min_v': min(samples), 'max_v': max(samples)}

    def low_runs(channels):
        runs, start = [], None
        a, b = bisect_left(t, lower), bisect_right(t, anchor)
        for i in range(a, b):
            low = all(v[ch][i] < 0.1 for ch in channels)
            if low and start is None:
                start = i
            elif not low and start is not None:
                runs.append((start, i - 1))
                start = None
        if start is not None:
            runs.append((start, b - 1))
        result = [{'start_s': t[a], 'end_s': t[b], 'duration_s': t[b] - t[a]}
                  for a, b in runs]
        return sorted(result, key=lambda item: item['duration_s'], reverse=True)

    common_runs = low_runs((3, 4))
    common = common_runs[0] if common_runs else None
    ramp_start = common['end_s'] if common else lower

    def crossings(ch, threshold):
        begin = max(1, bisect_right(t, ramp_start))
        up, down = [], []
        for i in range(begin, len(t)):
            if v[ch][i-1] < threshold <= v[ch][i]:
                up.append(t[i])
            elif v[ch][i-1] >= threshold > v[ch][i]:
                down.append(t[i])
        before_marker = [ts for ts in up if pd0 is None or ts <= pd0]
        first = before_marker[0] if before_marker else None
        last = before_marker[-1] if before_marker else None
        return {'threshold_v': threshold, 'up_s': up, 'down_s': down,
                'first_crossing_to_pd0_ms': (pd0 - first) * 1000
                if pd0 is not None and first is not None else None,
                'last_crossing_to_pd0_ms': (pd0 - last) * 1000
                if pd0 is not None and last is not None else None,
                'last_crossing_sustained_to_end': last is not None
                and not any(ts > last for ts in down)}

    rails = {str(ch): {str(threshold): crossings(ch, threshold)
                      for threshold in thresholds}
             for ch, thresholds in ((3, (0.33, 2.97)), (4, (0.5, 4.5)))}
    final_start = max(t[0], t[-1] - 2.0, (pe0 + 0.001) if pe0 is not None else t[0])
    final = {str(ch): stats(ch, final_start, t[-1]) for ch in range(6)}
    off_levels = {str(ch): stats(ch, common['start_s'], common['end_s'])
                  for ch in range(6)} if common else {}
    spacing = statistics.median(t[i] - t[i-1] for i in range(1, min(len(t), 4097)))
    largest_gap = max(t[i] - t[i-1] for i in range(1, len(t)))
    expected_rate = config.get('analog_sample_rate')
    digital_rate = config.get('digital_sample_rate')
    marker_order = nrst is not None and pd0 is not None and pe0 is not None \
        and nrst < pd0 <= pe0 and pe0 - pd0 < 10e-6
    final_ranges = {0: (2.7, 3.6), 1: (2.7, 3.6), 2: (2.7, 3.6),
                    3: (2.97, 3.6), 4: (4.5, 5.5)}
    checks = {
        'one_rising_edge_per_reset_and_marker': all(len(rises[ch]) == 1 for ch in (0, 1, 2)),
        'nrst_then_pd0_then_pe0_within_10_us': marker_order,
        'continuous_common_off_at_least_minimum': common is not None
        and common['duration_s'] >= minimum_off_s,
        'reset_and_markers_low_during_common_off': bool(common)
        and all(off_levels[str(ch)]['max_v'] < 0.5 for ch in (0, 1, 2)),
        'no_reset_or_marker_fall_after_its_rise': all(marker[ch] is not None
        and not any(ts > marker[ch] and not level for ts, level in edges[ch]) for ch in (0, 1, 2)),
        'final_plateau_at_least_0_5_s': pe0 is not None and t[-1] - final_start >= 0.5,
        'final_levels_in_range': all(final[str(ch)] is not None
        and low <= final[str(ch)]['min_v'] <= final[str(ch)]['max_v'] <= high
        for ch, (low, high) in final_ranges.items()),
        'rail_90pct_crossings_sustained_through_end': all(
            rails[str(ch)][str(threshold)]['last_crossing_sustained_to_end']
            for ch, threshold in ((3, 2.97), (4, 4.5))),
        'analog_sampling_continuous': largest_gap <= spacing * 1.1,
        'analog_rate_matches_configuration': expected_rate is not None and expected_rate > 0
        and abs(spacing * expected_rate - 1) < 0.01,
        'digital_and_analog_exports_cover_same_interval':
        abs(t[0] - dt[0]) <= spacing * 2 and abs(t[-1] - dt[-1]) <= spacing * 2,
    }
    result = {
        'passed': all(checks.values()), 'checks': checks,
        'failed_checks': [name for name, value in checks.items() if not value],
        'duration_s': t[-1] - t[0], 'analog_samples': len(t),
        'analog_spacing_us': spacing * 1e6, 'largest_analog_gap_us': largest_gap * 1e6,
        'digital_spacing_us': 1e6 / digital_rate if digital_rate and digital_rate > 0 else None,
        'minimum_off_s': minimum_off_s,
        'common_continuous_off_below_0_1_v': common,
        'longest_off_rail_runs': {str(ch): low_runs((ch,))[:3] for ch in (3, 4)},
        'off_levels': off_levels, 'digital_edges': edges,
        'final_window_s': [final_start, t[-1]], 'final_levels': final,
        'rails': rails,
        'timing': {'nrst_rise_s': nrst, 'pd0_rise_s': pd0, 'pe0_rise_s': pe0,
                   'nrst_to_pd0_ms': (pd0 - nrst) * 1000 if pd0 is not None and nrst is not None else None,
                   'pd0_to_pe0_us': (pe0 - pd0) * 1e6 if pd0 is not None and pe0 is not None else None},
        'limitations': [
            'Bench voltage thresholds are not MCU PGOOD or the exact instant of power application.',
            'NRST may release during the ramp, before the 90% rail crossings.',
            'A sustained low interval on measured rails does not prove unprobed rails discharged.',
            'Waveforms alone do not establish boot mode or the absence of debugger intervention.',
            'This check expects one boot; captures with multiple marker rises fail.',
            'Capture files are checked for presence, not application-level .sal integrity.',
        ],
    }
    (folder / 'independent-review.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def inspect(folder, minimum_off_s=1.0):
    """Write an explicit failure for incomplete/invalid exports as well."""
    try:
        return _inspect(folder, minimum_off_s)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {'passed': False, 'status': 'incomplete_or_invalid_capture',
                  'error': str(exc), 'timing': None}
        if folder.is_dir():
            (folder / 'independent-review.json').write_text(
                json.dumps(result, indent=2) + '\n', encoding='utf-8')
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--minimum-off-seconds', type=float, default=1.0)
    args = parser.parse_args()
    if not math.isfinite(args.minimum_off_seconds) or args.minimum_off_seconds <= 0:
        parser.error('--minimum-off-seconds must be finite and positive')
    result = inspect(args.folder.resolve(), args.minimum_off_seconds)
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
