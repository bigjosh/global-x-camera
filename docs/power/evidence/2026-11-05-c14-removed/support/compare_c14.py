"""Offline C14-removal comparison; reads sealed traces and never operates bench.

Default: three fresh run01/trace..run03/trace recordings versus two historical
October28 recordings. Output must be a new directory beneath this folder.
No percentage delta is claimed to isolate C14, because hardware/time differ.
"""
from pathlib import Path
import argparse
import csv
import importlib.util
import json
import os
import sys

HERE = Path(__file__).resolve().parent
CAMPAIGN = HERE.parent
sys.path.insert(0, str(CAMPAIGN.parent / 'plot-deps'))
os.environ['MPLCONFIGDIR'] = str(HERE / '.matplotlib')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

SOURCE = CAMPAIGN / 'analyze_inrush.py'
spec = importlib.util.spec_from_file_location('offline_inrush_analysis', SOURCE)
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)
FS = analysis.FS
COLORS = ['#147d92', '#2764bc', '#d36a19']
HISTORY = CAMPAIGN.parent / 'power-ablation-20261028'


def save_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def definitions(runs, historical_only):
    items = [dict(name='historical_fixed10a01', label='Oct28 fixed10A (historical)',
                  trace=HISTORY / 'fixed10a01', group='historical', color='#777777', style='--'),
             dict(name='historical_auto01', label='Oct28 auto (historical)',
                  trace=HISTORY / 'auto01', group='historical', color='#aaaaaa', style=':')]
    if not historical_only:
        for index, name in enumerate(runs):
            items.append(dict(name=name, label='C14 removed: ' + name, trace=HERE / name / 'trace',
                              group='c14_removed', color=COLORS[index % len(COLORS)], style='-'))
    return items


def summary_row(item, report):
    row = dict(run=item['name'], group=item['group'], trace=str(item['trace'].resolve()),
               onset_sample=report['current_onset']['sample_id'],
               on_range_control=report['recorded_on_range'],
               complete_marker_train=report['marker_decode']['unique_complete_train'],
               marker_ids=','.join(str(e['id']) for e in report['marker_decode']['events']),
               explicit_gpio_remapping=bool(report.get('gpio_interpretation', {}).get('explicit_remapping')))
    for key, window in report['startup_windows_raw_unqualified'].items():
        row[key + '_valid'] = window['valid']
        for field in ('charge_mC', 'positive_charge_mC', 'negative_charge_mC', 'energy_mJ',
                      'current_max', 'voltage_min', 'voltage_max'):
            row[key + '_' + field] = window.get(field)
        peak = window.get('native_peak_unqualified', {})
        row[key + '_peak_time_us'] = peak.get('time_from_onset_us')
        row[key + '_peak_range_code'] = peak.get('range_code')
    first = report['startup_windows_raw_unqualified']['5ms']
    for limit in ('1', '3', '5', '7'):
        threshold = first.get('current_above_A', {}).get(limit, {})
        row['duration_above_' + limit + 'A_us'] = threshold.get('duration_us')
    cycle = report['cycle']
    row['cycle_available'] = cycle['available']
    row['post5ms_to_plateau_energy_mJ'] = cycle.get('post5ms_to_plateau', {}).get('energy_mJ')
    row['onset_to_plateau_ms'] = cycle.get('onset_to_plateau_raw_unqualified', {}).get('duration_ms')
    row['plateau_current_mA'] = cycle.get('low_plateau_100ms', {}).get('current_mean_mA')
    events = {event['id']: event for event in report['marker_decode']['events']}
    row['first_strobe_ms'] = events.get(2, {}).get('time_ms')
    return row


def valid_samples(signals, name, start, end):
    values = analysis.slice_signal(signals, name, start, end)
    if values is None or not np.all(np.isfinite(values)):
        return None
    return values


def draw_startup(items, reports, arrays, out, first_us=500):
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))
    title = ('Startup after C14 removal — current and accumulated charge' if any(item['group'] == 'c14_removed' for item in items)
             else 'Historical startup references — renderer self-check only')
    fig.suptitle(title, fontsize=16, fontweight='bold', y=.98)
    for index, (duration_ms, time_scale, unit) in enumerate(((first_us / 1000, 1e6, 'µs'), (5, 1000, 'ms'))):
        count = round(duration_ms / 1000 * FS)
        for item, report, signals in zip(items, reports, arrays):
            onset = report['current_onset']['sample_id']
            current = valid_samples(signals, 'current', onset, onset + count)
            if current is None:
                continue
            time = np.arange(count) / FS * time_scale
            kwargs = dict(color=item['color'], linestyle=item['style'], linewidth=1.5,
                          alpha=.85 if item['group'] == 'historical' else 1, label=item['label'])
            axes[index, 0].plot(time, current, **kwargs)
            # Signed integral: retain the negative transient, do not rectify it.
            charge = np.r_[0., np.cumsum(current, dtype=np.float64) / FS * 1000]
            axes[index, 1].plot(np.arange(count + 1) / FS * time_scale, charge, **kwargs)
        axes[index, 0].set_ylabel('Current (A)')
        axes[index, 1].set_ylabel('Signed accumulated charge (mC)')
        for axis in axes[index]:
            axis.set_xlabel('Time from measured current onset (' + unit + ')')
            axis.set_xlim(0, duration_ms / 1000 * time_scale)
            axis.grid(color='#dce2e8', linewidth=.7)
            axis.axhline(0, color='#84919c', linewidth=.6)
        axes[index, 0].set_title('First ' + (str(first_us) + ' µs' if index == 0 else '5 ms'))
        axes[index, 1].set_title('Integral of the same native current samples')
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', bbox_to_anchor=(.5, .944), ncol=min(3, len(labels)), frameon=False, fontsize=9)
    fig.text(.06, .035, 'Historical controls differ in U42 population, date/firmware, and unqualified LED/card history; deltas do not isolate C14.', fontsize=9)
    fig.text(.06, .016, 'Native peaks and initial5ms remain unqualified. Current onset is a trace threshold; JS voltage is upstream of the DUT.', fontsize=9)
    fig.subplots_adjust(left=.08, right=.98, top=.83, bottom=.11, hspace=.34, wspace=.23)
    stem = 'startup-current-charge' if first_us == 500 else 'startup-' + str(first_us) + 'us-current-charge'
    fig.savefig(out / (stem + '.png'), dpi=170)
    fig.savefig(out / (stem + '.svg'))
    plt.close(fig)


def draw_source_voltage(items, reports, arrays, out):
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    for axis, duration_ms in zip(axes, (.5, 5)):
        count = round(duration_ms / 1000 * FS)
        for item, report, signals in zip(items, reports, arrays):
            onset = report['current_onset']['sample_id']
            voltage = valid_samples(signals, 'voltage', onset, onset + count)
            if voltage is not None:
                axis.plot(np.arange(count) / FS * 1000, voltage, color=item['color'],
                          linestyle=item['style'], linewidth=1.2, label=item['label'])
        axis.set(xlim=(0, duration_ms), xlabel='Milliseconds from current onset', ylabel='JS IN voltage (V)')
        axis.grid(color='#dce2e8')
    fig.suptitle('Measured source-side voltage — this is not the target rail', fontsize=15, fontweight='bold')
    fig.legend(*axes[0].get_legend_handles_labels(), loc='lower center', ncol=3, frameon=False, fontsize=8)
    fig.subplots_adjust(top=.85, bottom=.24, left=.07, right=.98, wspace=.18)
    fig.savefig(out / 'startup-source-voltage.png', dpi=170)
    plt.close(fig)


def draw_cycles(items, reports, arrays, out):
    selected = [(i, r, s) for i, r, s in zip(items, reports, arrays)
                if i['group'] == 'c14_removed' and r['cycle']['available']]
    if not selected:
        return False
    fig, axes = plt.subplots(len(selected), 2, figsize=(13, 3.6 * len(selected)), squeeze=False,
                             gridspec_kw={'width_ratios': [1.5, 1]})
    for row, (item, report, signals) in enumerate(selected):
        onset = report['current_onset']['sample_id']
        events = {event['id']: event for event in report['marker_decode']['events']}
        cycle = report['cycle']
        end = cycle.get('plateau_sample_id', events[10]['sample_id'])
        current_start = onset + FS // 200
        current_end = end + FS // 20
        stop = min(origin + len(data) for key, (origin, data) in signals.items() if key in ('current', 'voltage', 'power'))
        current_end = min(current_end, stop)
        bins = (current_end - current_start) // 2000
        current = valid_samples(signals, 'current', current_start, current_start + bins * 2000)
        ax, phases = axes[row]
        if current is not None:
            means = current.reshape(bins, 2000).mean(axis=1, dtype=np.float64) * 1000
            time = (current_start - onset) / FS * 1000 + np.arange(bins) + .5
            ax.plot(time, means, color=item['color'], linewidth=1.3)
        total = cycle.get('post5ms_to_plateau', {}).get('energy_mJ')
        energy_text = 'post5ms energy ' + (f'{total:.2f} mJ' if total is not None else 'not bounded by plateau')
        ax.set_title(item['name'] + ' · ' + energy_text, loc='left', fontsize=11)
        ax.set(xlabel='Milliseconds from current onset', ylabel='1 ms mean current (mA)', xlim=(0, (current_end - onset) / FS * 1000))
        ax.grid(color='#e2e6eb')
        for marker in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11):
            if marker in events:
                when = events[marker]['time_ms']
                ax.axvline(when, color='#88939c', linewidth=.6, linestyle=':', alpha=.8)
        lanes = [('Capture: strobe→frame', 2, 3, '#4a89c2'),
                 ('SD initialization', 4, 5, '#e4ad39'),
                 ('SD slot transport', 6, 7, '#29a372'),
                 ('Save cleanup', 7, 10, '#84939f')]
        for lane, (label, first, last, color) in enumerate(lanes):
            start, endtime = events[first]['time_ms'], events[last]['time_ms']
            phases.broken_barh([(start, endtime - start)], (lane - .32, .64), facecolors=color)
        phases.set(yticks=range(len(lanes)), yticklabels=[lane[0] for lane in lanes],
                   xlabel='Milliseconds from current onset', xlim=ax.get_xlim(), ylim=(3.6, -.6))
        phases.grid(axis='x', color='#e2e6eb')
        phases.set_title('Overlapping intervals, not additive', fontsize=10)
    fig.suptitle('C14 removed: complete-cycle observations', fontsize=16, fontweight='bold', y=.99)
    fig.text(.06, .012, 'First5ms excluded here. Markers show firmware observations; they do not prove image integrity, MCU Standby or component-only power.', fontsize=9)
    fig.tight_layout(rect=(.02, .045, .995, .955), w_pad=2.5, h_pad=2.5)
    fig.savefig(out / 'new-cycles-current-phases.png', dpi=170)
    fig.savefig(out / 'new-cycles-current-phases.svg')
    plt.close(fig)
    return True


def comparison(rows):
    old = next(row for row in rows if row['run'] == 'historical_fixed10a01')
    fresh = [row for row in rows if row['group'] == 'c14_removed']
    if not fresh:
        return None
    fields = ['0.25ms_charge_mC', '1ms_charge_mC', '5ms_charge_mC', '5ms_energy_mJ',
              '5ms_current_max', 'duration_above_1A_us', 'duration_above_3A_us', 'duration_above_5A_us']
    result = {'historical_reference': old['run'], 'interpretation': 'Descriptive only; changed hardware and time prevent isolated C14 attribution', 'metrics': {}}
    for field in fields:
        values = [row[field] for row in fresh if row.get(field) is not None]
        if len(values) != len(fresh) or old.get(field) is None:
            continue
        median = float(np.median(values))
        result['metrics'][field] = dict(historical=old[field], new_count=len(values),
            new_min=min(values), new_max=max(values), new_median=median,
            new_median_minus_historical=median - old[field],
            descriptive_reduction_percent=100 * (1 - median / old[field]) if old[field] else None)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='New output directory beneath c14-removed')
    parser.add_argument('--runs', nargs='+', default=['run01', 'run02', 'run03'])
    parser.add_argument('--historical-only', action='store_true', help='Render/validate old inputs only; no new measurements claimed')
    parser.add_argument('--swap-new-gpi', action='store_true', help='Explicitly qualify phase on physical IN1 and exposure on IN0 for NEW runs only')
    args = parser.parse_args()
    out = args.out.resolve()
    out.relative_to(HERE)
    analysis.require(not out.exists(), 'Output directory already exists')
    items = definitions(args.runs, args.historical_only)
    reports, arrays = [], []
    remap = None
    if args.swap_new_gpi:
        remap_spec = importlib.util.spec_from_file_location('explicit_inrush_gpio_mapping', HERE / 'analyze_swapped.py')
        remap = importlib.util.module_from_spec(remap_spec)
        remap_spec.loader.exec_module(remap)
    for item in items:
        if remap is not None and item['group'] == 'c14_removed':
            report, _, signals = remap.analyze(item['trace'])
        else:
            report, _ = analysis.analyze(item['trace'], markers='11' if item['group'] == 'c14_removed' else '10')
            signals, _, _ = analysis.load_trace(item['trace'])
        report.update(run=item['name'], comparison_group=item['group'])
        if item['group'] == 'c14_removed':
            done = json.loads((item['trace'] / 'result.json').read_text())
            analysis.require(done.get('mode') == 'cold-normal', 'New run is not recorder cold-normal: ' + item['name'])
            analysis.require(done.get('on_range') == 1, 'New run is not fixed10A: ' + item['name'])
        reports.append(report)
        arrays.append(signals)
    # Nothing written until every requested recording passed the offline loader.
    out.mkdir(parents=True)
    rows = [summary_row(item, report) for item, report in zip(items, reports)]
    for item, report in zip(items, reports):
        save_json(out / (item['name'] + '-analysis.json'), report)
    report = dict(schema=1, historical_only=args.historical_only, rows=rows, comparison=comparison(rows),
        explicit_new_gpio_remapping=args.swap_new_gpi,
        source_sha256={str(Path(__file__)): analysis.sha(Path(__file__)), str(SOURCE): analysis.sha(SOURCE)},
        new_hardware='User reports C14 removed; U42 and SD carrier LED already removed. Exact physical state is not proved by this analysis.',
        historical_hardware='October28 controls predate confirmed U42 removal; SD LED population/removal timing not independently established for those exact recordings.',
        limitations=['Historical controls differ in time, U42/LED population or uncertainty, firmware and card history. They are not an isolated C14 A/B experiment.',
            'Whole-cycle energy differs with exposure, card init/write timing and scan depth; do not attribute it wholly to capacitance.',
            'Initial5ms/physical native peaks/source-voltage transients remain unqualified, even with fixed10A range.',
            'Image verification is a separate root-owned evidence record; no image-integrity claim is made here.',
            'Power-on is measured current threshold, not directly observed target voltage or reset release.'])
    save_json(out / 'comparison.json', report)
    with (out / 'comparison.csv').open('x', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    draw_startup(items, reports, arrays, out)
    draw_startup(items, reports, arrays, out, first_us=250)
    draw_source_voltage(items, reports, arrays, out)
    cycle_plot = draw_cycles(items, reports, arrays, out)
    print(json.dumps(dict(output=str(out), rows=rows, comparison=report['comparison'], cycle_plot=cycle_plot), indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
