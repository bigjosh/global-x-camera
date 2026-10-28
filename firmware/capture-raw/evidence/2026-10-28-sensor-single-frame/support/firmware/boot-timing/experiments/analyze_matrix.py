"""Compare first-GPIO captures offline, without altering the capture directories.

Example (ADDED_BYTES is the packaged boot-image size minus its baseline size):
  python firmware/boot-timing/experiments/analyze_matrix.py \
    --run baseline-1 0 tmp/bringup/opt-matrix-baseline-01 \
    --run plus-8k 8192 tmp/bringup/opt-matrix-plus-8k-01 \
    --run plus-32k 32768 tmp/bringup/opt-matrix-plus-32k-01 \
    --run baseline-2 0 tmp/bringup/opt-matrix-baseline-02 \
    --run tiny -64 tmp/bringup/opt-matrix-tiny-01 \
    --output tmp/bringup/opt-matrix-analysis.json

Requires a passed cycle-outcome.json and existing inspect_cycle.py
independent-review.json results. Also checks
raw exports, including CH5 main-VDDIO discharge and thresholds that the older
inspector does not assess. Missing, changing, or failed captures never enter
the fit. Labels containing "tiny" are excluded because code also differs.
Only --output is written, and it must be outside every capture directory.
"""

import argparse
from bisect import bisect_left, bisect_right
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from inspect_cycle import read_csv


def load_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def stamp(path):
    value = path.stat()
    return value.st_size, value.st_mtime_ns


def longest_low(t, values, channels, start, end):
    best, first = None, None
    a, b = bisect_left(t, start), bisect_right(t, end)
    for i in range(a, b + 1):
        low = i < b and all(values[ch][i] < 0.1 for ch in channels)
        if low and first is None:
            first = i
        if not low and first is not None:
            item = {'start_s': t[first], 'end_s': t[i - 1],
                    'duration_s': t[i - 1] - t[first]}
            if best is None or item['duration_s'] > best['duration_s']:
                best = item
            first = None
    return best


def threshold_crossings(t, values, threshold, after, marker):
    up, down = [], []
    for i in range(max(1, bisect_right(t, after)), len(t)):
        if values[i - 1] < threshold <= values[i]:
            up.append(t[i])
        elif values[i - 1] >= threshold > values[i]:
            down.append(t[i])
    first, last = (up[0], up[-1]) if up else (None, None)
    return {
        'threshold_v': threshold, 'up_crossings_s': up, 'down_crossings_s': down,
        'first_up_s': first, 'final_up_s': last,
        'first_to_pd0_ms': (marker - first) * 1000 if marker is not None and first is not None else None,
        'final_to_pd0_ms': (marker - last) * 1000 if marker is not None and last is not None else None,
        'final_crossing_sustained_to_end': last is not None and not any(x > last for x in down),
    }


def inspect_run(label, added_bytes, folder, minimum_off_s):
    result = {'label': label, 'added_image_bytes': added_bytes, 'folder': str(folder),
              'passed': False, 'status': 'incomplete_or_invalid_capture', 'metrics': {}}
    files = [folder / name for name in ('capture-config.json', 'independent-review.json',
                                       'analog.csv', 'digital.csv', 'boot.sal', 'cycle-outcome.json')]
    try:
        before = {path.name: stamp(path) for path in files}
        if any(size == 0 for size, _ in before.values()):
            raise ValueError('A required capture artifact is empty')
        config = load_json(files[0])
        previous = load_json(files[1])
        previous_timing = previous.get('timing') or {}
        outcome = load_json(files[5])
        if outcome.get('passed') is not True:
            raise ValueError('cycle-outcome.json does not report a passed, completed cycle')
        t, v = read_csv(files[2])
        dt, dv = read_csv(files[3], digital=True)
        has_main = config.get('channel_map', {}).get('5') == 'main-vddio'
        edges = {ch: [(dt[i], int(dv[ch][i])) for i in range(1, len(dt))
                      if dv[ch][i] != dv[ch][i - 1]] for ch in (0, 1, 2)}
        rises = {ch: [ts for ts, level in edge if level] for ch, edge in edges.items()}
        markers = {ch: x[0] if len(x) == 1 else None for ch, x in rises.items()}
        nrst, pd0, pe0 = [markers[ch] for ch in (0, 1, 2)]
        anchor = nrst if nrst is not None else min(t[-1], pd0 or t[-1])
        lower = max((ts for edge in edges.values() for ts, level in edge
                     if not level and ts < anchor), default=t[0])
        channels = (3, 4, 5) if has_main else (3, 4)
        common = longest_low(t, v, channels, lower, anchor)
        ramp_start = common['end_s'] if common else lower
        rails = {name: threshold_crossings(t, v[ch], threshold, ramp_start, pd0)
                 for name, ch, threshold in [('target_0_5v', 4, 0.5),
                                              ('target_4_5v', 4, 4.5),
                                              ('aux_2_97v', 3, 2.97)]}
        if has_main:
            rails['main_vddio_2_97v'] = threshold_crossings(t, v[5], 2.97, ramp_start, pd0)
        final_start = max(t[0], t[-1] - 2.0, pe0 + 0.001 if pe0 is not None else t[0])
        final = {}
        for ch in range(6):
            samples = v[ch][bisect_left(t, final_start):]
            final[str(ch)] = {'min_v': min(samples), 'max_v': max(samples),
                              'median_v': statistics.median(samples)} if samples else None
        spacing = statistics.median(t[i] - t[i - 1] for i in range(1, min(len(t), 4097)))
        largest_gap = max(t[i] - t[i - 1] for i in range(1, len(t)))
        rate = config.get('analog_sample_rate')
        drate = config.get('digital_sample_rate')
        if common:
            a, b = bisect_left(t, common['start_s']), bisect_right(t, common['end_s'])
            off_max = {str(ch): max(v[ch][a:b]) for ch in range(6)}
        else:
            off_max = {}
        ranges = {0: (2.7, 3.6), 1: (2.7, 3.6), 2: (2.7, 3.6),
                  3: (2.97, 3.6), 4: (4.5, 5.5)}
        if has_main:
            ranges[5] = (2.97, 3.6)
        checks = {
            'cycle_outcome_passed': outcome.get('passed') is True
                and all(outcome.get(key) == 0 for key in
                        ('cycle_returncode', 'capture_returncode', 'inspection_returncode')),
            'existing_independent_review_passed': previous.get('passed') is True,
            'ch5_explicitly_main_vddio': has_main,
            'exactly_one_rise_per_reset_and_marker': all(len(x) == 1 for x in rises.values()),
            'ordered_markers': nrst is not None and pd0 is not None and pe0 is not None
                               and nrst < pd0 <= pe0 and pe0 - pd0 < 10e-6,
            'no_reset_or_marker_fall_after_rise': all(markers[ch] is not None
                and not any(ts > markers[ch] and level == 0 for ts, level in edges[ch]) for ch in (0, 1, 2)),
            'all_three_rails_continuously_below_0_1v': has_main and common is not None
                                                       and common['duration_s'] >= minimum_off_s,
            'reset_and_markers_low_during_off': bool(common)
                and all(off_max[str(ch)] < 0.5 for ch in (0, 1, 2)),
            'final_plateau_at_least_0_5s': pe0 is not None and t[-1] - final_start >= 0.5,
            'final_levels_in_range': all(final[str(ch)] is not None
                and lo <= final[str(ch)]['min_v'] <= final[str(ch)]['max_v'] <= hi
                for ch, (lo, hi) in ranges.items()),
            'final_rail_crossings_sustained': all(x['final_crossing_sustained_to_end'] for x in rails.values()),
            'analog_continuous_and_rate_matches': rate is not None and rate > 0
                and abs(spacing * rate - 1) < 0.01 and largest_gap <= spacing * 1.1,
            'digital_rate_available': drate is not None and drate > 0,
            'exports_cover_same_interval': abs(t[0] - dt[0]) <= spacing * 2
                                           and abs(t[-1] - dt[-1]) <= spacing * 2,
            'existing_marker_timing_matches_raw': all(previous_timing.get(name) == value
                for name, value in [('nrst_rise_s', nrst), ('pd0_rise_s', pd0), ('pe0_rise_s', pe0)]),
            'files_unchanged_during_analysis': all(stamp(path) == before[path.name] for path in files),
        }
        result.update({
            'passed': all(checks.values()), 'status': 'complete', 'checks': checks,
            'failed_checks': [name for name, passed in checks.items() if not passed],
            'independent_review_failed_checks': previous.get('failed_checks', []),
            'independent_review_sha256': hashlib.sha256(files[1].read_bytes()).hexdigest(),
            'channel_map': config.get('channel_map'), 'duration_s': t[-1] - t[0],
            'analog_spacing_us': spacing * 1e6,
            'digital_spacing_us': 1e6 / drate if drate and drate > 0 else None,
            'common_off_below_0_1v': common, 'off_maxima_v': off_max,
            'individual_off_below_0_1v': {str(ch): longest_low(t, v, (ch,), lower, anchor) for ch in channels},
            'final_levels': final, 'crossings': rails,
            'marker_times_s': {'nrst': nrst, 'pd0': pd0, 'pe0': pe0},
            'metrics': {
                'target_0_5v_first_to_pd0_ms': rails['target_0_5v']['first_to_pd0_ms'],
                'target_0_5v_final_to_pd0_ms': rails['target_0_5v']['final_to_pd0_ms'],
                'nrst_to_pd0_ms': (pd0 - nrst) * 1000 if pd0 is not None and nrst is not None else None,
                'main_vddio_2_97v_first_to_pd0_ms': rails.get('main_vddio_2_97v', {}).get('first_to_pd0_ms'),
                'main_vddio_2_97v_final_to_pd0_ms': rails.get('main_vddio_2_97v', {}).get('final_to_pd0_ms'),
                'pd0_to_pe0_us': (pe0 - pd0) * 1e6 if pd0 is not None and pe0 is not None else None,
            },
        })
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result['error'] = str(exc)
    return result


def fit_metric(runs, metric, expected_hz):
    selected = [x for x in runs if x['passed'] and 'tiny' not in x['label'].lower()
                and x['added_image_bytes'] >= 0 and x['metrics'].get(metric) is not None]
    result = {'metric': metric, 'labels': [x['label'] for x in selected],
              'status': 'insufficient_distinct_payload_sizes'}
    if len({x['added_image_bytes'] for x in selected}) < 2:
        return result
    xs = [x['added_image_bytes'] for x in selected]
    ys = [x['metrics'][metric] for x in selected]
    xbar, ybar = statistics.mean(xs), statistics.mean(ys)
    slope = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / sum((x - xbar) ** 2 for x in xs)
    intercept = ybar - slope * xbar
    residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    baseline = [x['metrics'][metric] for x in selected if x['added_image_bytes'] == 0]
    result.update({'status': 'descriptive_fit', 'intercept_ms': intercept,
                   'slope_ms_per_kib': slope * 1024,
                   'expected_spi_1bit_ms_per_kib': 1024 * 8 / expected_hz * 1000,
                   'effective_bytes_per_second': 1000 / slope if slope > 0 else None,
                   'maximum_absolute_residual_ms': max(abs(x) for x in residuals),
                   'baseline_spread_ms': max(baseline) - min(baseline) if len(baseline) > 1 else None,
                   'delta_from_mean_baseline_ms': {x['label']: x['metrics'][metric] - statistics.mean(baseline)
                       for x in selected} if baseline else None})
    return result


def summarize_groups(runs):
    groups = {}
    for run in runs:
        if not run['passed']:
            continue
        key = 'tiny' if 'tiny' in run['label'].lower() else str(run['added_image_bytes'])
        groups.setdefault(key, []).append(run)
    result = {}
    for key, items in groups.items():
        metrics = {}
        for metric in ('nrst_to_pd0_ms', 'target_0_5v_final_to_pd0_ms', 'main_vddio_2_97v_final_to_pd0_ms'):
            values = [item['metrics'][metric] for item in items]
            metrics[metric] = {'n': len(values), 'mean': statistics.mean(values),
                               'median': statistics.median(values), 'min': min(values),
                               'max': max(values), 'range': max(values) - min(values),
                               'sample_stdev': statistics.stdev(values) if len(values) > 1 else None}
        result[key] = {'labels': [item['label'] for item in items], 'metrics': metrics}
    if '0' in result:
        for key, group in result.items():
            group['mean_minus_baseline_ms'] = {
                metric: values['mean'] - result['0']['metrics'][metric]['mean']
                for metric, values in group['metrics'].items()}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--run', action='append', nargs=3, required=True,
                        metavar=('LABEL', 'ADDED_BYTES', 'DIRECTORY'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--minimum-off-seconds', type=float, default=1.0)
    parser.add_argument('--expected-spi-hz', type=float, default=32_000_000)
    args = parser.parse_args()
    if not all(math.isfinite(x) and x > 0 for x in (args.minimum_off_seconds, args.expected_spi_hz)):
        parser.error('Off duration and expected frequency must be finite and positive')
    if len({row[0] for row in args.run}) != len(args.run):
        parser.error('Run labels must be unique')
    parsed = []
    for label, amount, directory in args.run:
        try:
            parsed.append((label, int(amount), Path(directory).resolve()))
        except ValueError:
            parser.error('ADDED_BYTES must be an integer')
    if args.output and any(args.output.resolve().is_relative_to(folder) for _, _, folder in parsed):
        parser.error('Output must be outside the input capture directories')
    runs = [inspect_run(*row, args.minimum_off_seconds) for row in parsed]
    result = {'passed': all(run['passed'] for run in runs), 'runs': runs,
              'group_statistics': summarize_groups(runs),
              'fits': [fit_metric(runs, metric, args.expected_spi_hz) for metric in
                       ('nrst_to_pd0_ms', 'target_0_5v_final_to_pd0_ms', 'main_vddio_2_97v_final_to_pd0_ms')],
              'expected_spi_hz_assumption': args.expected_spi_hz,
              'expected_8192_byte_increment_ms': 8192 * 8 / args.expected_spi_hz * 1000,
              'expected_32768_byte_increment_ms': 32768 * 8 / args.expected_spi_hz * 1000,
              'limitations': [
                  'Bench thresholds are sampled crossings, not MCU PGOOD or the exact instant of power application.',
                  'Final crossing means the last upward crossing after sustained off, with no later downward crossing.',
                  'First and final crossings are both reported; repeated crossings can shift the chosen reference.',
                  'CH3/4/5 discharge does not establish the state of unprobed core or backup rails.',
                  'Passing waveforms do not establish flash contents, boot mode, or absence of debugger intervention.',
                  'Added byte counts and identical pre-marker code must be verified against build/programming evidence.',
                  'Expected 32 MHz single-bit transfer time is a hypothesis, not a measured bus clock.',
                  'Fits are descriptive, have no confidence interval, and must be compared with baseline drift and sampling resolution.',
                  'Tiny-code runs are excluded from size fits because instructions and payload size both differ.',
                  'Presence of boot.sal is checked, not its application-level integrity.',
              ]}
    text = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding='utf-8')
    print(text)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
