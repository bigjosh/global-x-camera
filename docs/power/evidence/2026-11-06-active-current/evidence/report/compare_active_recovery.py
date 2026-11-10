"""Offline, hash-verified Nov5/Nov6 comparison. No instrument access.

Default requires all three completed Nov6 analyses. A one-run preview may be
requested explicitly; it cannot silently stand in for the complete comparison.
All generated outputs stay in a new subdirectory beneath this report folder.
"""
import argparse
import gc
import importlib.util
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
CAMPAIGN = HERE.parent
HISTORY = CAMPAIGN.parent/'inrush-20261105/c14-removed'
sys.path.insert(0, str(CAMPAIGN.parent/'plot-deps'))
os.environ['MPLCONFIGDIR'] = str(HERE/'.matplotlib')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

spec = importlib.util.spec_from_file_location('comparison_remapping', CAMPAIGN/'analyze_swapped.py')
mapping = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mapping)
analysis = mapping.base
FS = analysis.FS
COLORS = {'Nov5': ['#ad795a', '#ba967b', '#8c6956'],
          'Nov6': ['#007e92', '#2174b8', '#35a396']}


def save_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def mean_curve(signals, onset, duration_ms, bin_ms):
    count = round(duration_ms/1000*FS)
    width = round(bin_ms/1000*FS)
    values = analysis.slice_signal(signals, 'current', onset, onset+count)
    analysis.require(values is not None and np.all(np.isfinite(values)),
                     'Incomplete/nonfinite plotted current interval')
    bins = count//width
    means = values[:bins*width].reshape(bins, width).mean(axis=1, dtype=np.float64)*1000
    return (np.arange(bins)+.5)*bin_ms, means


def check_report(path):
    report = json.loads(path.read_text())
    trace = Path(report['trace'])
    analysis.require(report['source_index_sha256'] == analysis.sha(trace/'chunks.jsonl'),
                     'Analysis references changed chunk index: '+str(path))
    analysis.require(report['result_sha256'] == analysis.sha(trace/'result.json'),
                     'Analysis references changed recorder result: '+str(path))
    signals, checks, result = analysis.load_trace(trace)
    for name, check in checks.items():
        for key in ('sha256', 'first_sample_id', 'analyzed_end_exclusive'):
            analysis.require(check[key] == report['checks'][name][key],
                             'Saved analysis mismatch: '+name+'/'+key)
    analysis.require(result['on_range'] == report['recorded_on_range'] == 1,
                     'Comparison requires recorded fixed10A')
    onset, _ = analysis.select_onset(signals)
    analysis.require(onset == report['current_onset']['sample_id'], 'Onset changed')
    analysis.require(report.get('gpio_interpretation', {}).get('explicit_remapping') is True,
                     'Explicit physical GPI mapping is required')
    logical = dict(signals)
    logical['gpi0'], logical['gpi1'] = signals['gpi1'], signals['gpi0']
    markers = analysis.decode_markers(logical, onset, '11')
    analysis.require(markers['unique_complete_train'], 'Need unique11-marker train')
    analysis.require(markers['events'] == report['marker_decode']['events'], 'Marker decode changed')
    exposure = mapping.exposure_evidence(logical, markers, onset)
    analysis.require(exposure == report['external_exposure_mirror'], 'Exposure evidence changed')
    cycle = analysis.cycle_metrics(logical, markers, onset)
    analysis.require(cycle['plateau_available'] and cycle['post5ms_to_plateau']['valid'],
                     'Missing valid cycle/plateau')
    analysis.require(cycle['plateau_sample_id'] == report['cycle']['plateau_sample_id'],
                     'Plateau time changed')
    for key in ('current_mean_mA', 'energy_mJ'):
        analysis.require(np.isclose(cycle['post5ms_to_plateau'][key],
                                    report['cycle']['post5ms_to_plateau'][key], rtol=1e-12),
                         'Cycle '+key+' changed')
    return report, signals, checks, onset, markers, exposure, cycle


def prepare(path, group, run, index):
    report, signals, checks, onset, markers, exposure, cycle = check_report(path)
    fixed = analysis.metrics(signals, onset+FS//200, onset+FS//100, onset)
    analysis.require(fixed['valid'], 'Invalid5–10ms interval')
    post = cycle['post5ms_to_plateau']
    # Plot through a full 100 ms after the end of the active cycle.
    duration = np.ceil((cycle['plateau_sample_id']-onset)/FS*1000)+100
    full = mean_curve(signals, onset, float(duration), 1)
    early = mean_curve(signals, onset, 10, .25)
    qualified_bins = (full[0] >= 5) & (full[0]+.5 <= post['end_ms'])
    row = dict(group=group, run=run, label=group+' '+run,
               first_strobe_ms=next(e['time_ms'] for e in markers['events'] if e['id'] == 2),
               exposure_mirror_ms=exposure['duration_ms'],
               current_5_to_10ms_mA=fixed['current_mean_mA'],
               post5ms_to_plateau_mean_mA=post['current_mean_mA'],
               post5ms_to_plateau_energy_mJ=post['energy_mJ'],
               plateau_from_onset_ms=post['end_ms'],
               plateau_current_mA=cycle['low_plateau_100ms']['current_mean_mA'],
               post5ms_peak_1ms_mean_mA=float(np.max(full[1][qualified_bins])),
               source_mean_V=post['voltage_mean'],
               eleven_markers=True, one_exposure_mirror=True)
    source = dict(analysis=str(path.resolve()), analysis_sha256=analysis.sha(path),
                  trace=report['trace'], checks=checks,
                  index_sha256=report['source_index_sha256'], result_sha256=report['result_sha256'],
                  mapping=report['gpio_interpretation'], onset_sample_id=onset,
                  current_5_to_10ms=fixed, post5ms_to_plateau=post)
    return row, source, (full, early), COLORS[group][index]


def group_summary(rows):
    fields = ('current_5_to_10ms_mA', 'post5ms_to_plateau_mean_mA',
              'post5ms_to_plateau_energy_mJ', 'plateau_from_onset_ms',
              'plateau_current_mA', 'post5ms_peak_1ms_mean_mA', 'first_strobe_ms')
    summary = {}
    for group in ('Nov5', 'Nov6'):
        subset = [row for row in rows if row['group'] == group]
        summary[group] = {'count': len(subset)}
        for field in fields:
            values = [row[field] for row in subset]
            summary[group][field] = dict(min=min(values), median=float(np.median(values)), max=max(values))
    summary['new_minus_previous_median_mA'] = (
        summary['Nov6']['post5ms_to_plateau_mean_mA']['median']-
        summary['Nov5']['post5ms_to_plateau_mean_mA']['median'])
    summary['new_minus_previous_5_to_10ms_median_mA'] = (
        summary['Nov6']['current_5_to_10ms_mA']['median']-
        summary['Nov5']['current_5_to_10ms_mA']['median'])
    return summary


def table(rows, summary, complete):
    lines = ['Three-run comparison' if complete else 'INCOMPLETE PREVIEW — only selected new runs', '',
             '5 V whole-board input current through JS110; first5ms excluded from energy/active means.', '',
             '| Run | 5–10ms (mA) | Active mean (mA) | Energy (mJ) | Low plateau begins (ms) | Plateau (mA) |',
             '|---|---:|---:|---:|---:|---:|']
    for row in rows:
        lines.append('| {label} | {current_5_to_10ms_mA:.2f} | {post5ms_to_plateau_mean_mA:.2f} | '
                     '{post5ms_to_plateau_energy_mJ:.2f} | {plateau_from_onset_ms:.2f} | '
                     '{plateau_current_mA:.2f} |'.format(**row))
    lines.extend(['', 'Active mean and energy integrate5ms after current onset to the detected low plateau.',
                  'All included traces independently recheck eleven phase markers and one exposure mirror.',
                  'This report does not verify SD image contents or independently prove MCU Standby.',
                  'Current onset is a measured threshold, not target power-good. Voltage is measured upstream of the DUT.',
                  'The user reports finding/fixing a suspected short; these traces do not establish its physical cause.',
                  'No component-level attribution or isolated C14 effect is claimed. SD timing/history vary.', '',
                  'Median active-current change: {:.2f}mA; fixed5–10ms change: {:.2f}mA.'.format(
                      summary['new_minus_previous_median_mA'],
                      summary['new_minus_previous_5_to_10ms_median_mA'])])
    return '\n'.join(lines)+'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--new-runs', nargs='+', default=['cold-normal01', 'cold-normal02', 'cold-normal03'])
    parser.add_argument('--out', type=Path, default=HERE/'comparison-three')
    args = parser.parse_args()
    output = args.out.resolve()
    output.relative_to(HERE)
    analysis.require(not output.exists(), 'Output must not already exist')
    analysis.require(len(set(args.new_runs)) == len(args.new_runs) and
                     set(args.new_runs) <= {'cold-normal01', 'cold-normal02', 'cold-normal03'},
                     'Select distinct expected new runs only')
    sources = [(HISTORY/'comparison-three-remapped'/('run%02d-analysis.json'%i), 'Nov5', 'run%02d'%i, i-1)
               for i in range(1, 4)]
    sources += [(CAMPAIGN/run/'analysis.json', 'Nov6', run, int(run[-2:])-1) for run in args.new_runs]
    for path, *_ in sources:
        analysis.require(path.is_file(), 'Required completed analysis missing: '+str(path))
    complete = set(args.new_runs) == {'cold-normal01', 'cold-normal02', 'cold-normal03'}
    rows, proofs, curves = [], [], []
    for path, group, run, index in sources:
        row, proof, curve, color = prepare(path, group, run, index)
        rows.append(row); proofs.append(proof); curves.append((row, curve, color))
        gc.collect()
        print('Verified '+row['label'], flush=True)
    summary = group_summary(rows)
    output.mkdir()
    report = dict(complete_three_new_runs=complete, source_script_sha256=analysis.sha(__file__),
                  analyzer_sha256=analysis.sha(CAMPAIGN/'analyze_inrush.py'),
                  remapping_sha256=analysis.sha(CAMPAIGN/'analyze_swapped.py'),
                  rows=rows, group_summary=summary, sources=proofs,
                  boundary='Direct5V input; JS source voltage is upstream of DUT; no LTC/battery losses.',
                  first5ms_qualified=False, physical_cause_established=False,
                  user_report='User suspects an inadvertent short and reports fixing it; no physical localization proven.')
    save_json(output/'comparison.json', report)
    (output/'summary.md').write_text(table(rows, summary, complete), encoding='utf-8')
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.8), gridspec_kw={'width_ratios': [1.8, 1]})
    for row, curve, color in curves:
        for axis, (x, y) in zip(axes, curve):
            axis.plot(x, y, label=row['label'], color=color, linewidth=1.35,
                      linestyle='--' if row['group'] == 'Nov5' else '-', alpha=.9)
    for axis in axes:
        axis.axvspan(0, 5, color='#ded9ce', alpha=.6, zorder=-1)
        axis.set(xlabel='Milliseconds from measured current onset', ylabel='Current (mA)')
        axis.grid(color='#e0e5e9', linewidth=.7)
    axes[0].set(xlim=(0, max(max(curve[0][0]) for _, curve, _ in curves)), ylim=(0, 450),
                title='Capture → save → low plateau · 1ms means')
    axes[0].text(.015, .96, 'Initial inrush omitted from this vertical scale',
                 transform=axes[0].transAxes, va='top', fontsize=8.5, color='#665c4e')
    axes[1].set(xlim=(0, 10), title='First10ms · 0.25ms means')
    axes[1].text(.02, .96, 'Shaded0–5ms: startup amplitude unqualified',
                 transform=axes[1].transAxes, va='top', fontsize=8.5, color='#665c4e')
    fig.suptitle('Whole-board current: prior high-current runs versus current runs'+
                 ('' if complete else ' — incomplete preview'), fontsize=15, fontweight='bold')
    fig.legend(*axes[0].get_legend_handles_labels(), loc='upper center', bbox_to_anchor=(.5, .91),
               ncol=3, frameon=False, fontsize=9)
    fig.text(.06, .065, 'Both groups: C14 removed, unchanged normal single-frame firmware, fixed10A recording; 5V source-side measurement boundary.', fontsize=9)
    fig.text(.06, .035, 'The suspected short is user-reported. These traces establish the current change, not its physical cause; SD timing/history also vary.', fontsize=9)
    fig.subplots_adjust(left=.065, right=.985, top=.75, bottom=.2, wspace=.22)
    fig.savefig(output/'current-comparison.png', dpi=180)
    fig.savefig(output/'current-comparison.svg')
    plt.close(fig)
    print(json.dumps(dict(output=str(output), complete=complete, summary=summary), indent=2))


if __name__ == '__main__':
    main()
