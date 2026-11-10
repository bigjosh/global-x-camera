"""Offline C17-removal comparison: three latest LOW baseline runs vs three new runs.

Never imports instrument drivers or operates the bench. Requires completed,
hash-bound analyses, then rereads every raw stream and recomputes timing and
window metrics. Writes only new outputs under this report directory.
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
BASELINE = CAMPAIGN.parent/'active-current-20261106'
sys.path.insert(0, str(CAMPAIGN.parent/'plot-deps'))
os.environ['MPLCONFIGDIR'] = str(HERE/'.matplotlib')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

spec = importlib.util.spec_from_file_location('c17_remapping', CAMPAIGN/'analyze_swapped.py')
mapping = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mapping)
analysis = mapping.base
FS = analysis.FS
GROUPS = ('C17 fitted', 'C17 removed')
COLORS = {'C17 fitted': ['#a27b62', '#b69c85', '#7f7167'],
          'C17 removed': ['#007e92', '#2174b8', '#35a396']}
WINDOWS = {'0.25ms': .25, '1ms': 1.0, '5ms': 5.0}
OUTPUTS = ('summary.json', 'summary.md', 'current-comparison.png',
           'current-comparison.svg', 'startup-current-charge.png',
           'startup-current-charge.svg')


def save_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def check_report(path):
    report = json.loads(path.read_text())
    trace = Path(report['trace'])
    analysis.require(report['source_index_sha256'] == analysis.sha(trace/'chunks.jsonl'),
                     'Changed chunk index: '+str(path))
    analysis.require(report['result_sha256'] == analysis.sha(trace/'result.json'),
                     'Changed recorder result: '+str(path))
    signals, checks, result = analysis.load_trace(trace)
    for name, check in checks.items():
        for key in ('sha256', 'first_sample_id', 'analyzed_end_exclusive'):
            analysis.require(check[key] == report['checks'][name][key],
                             'Saved analysis mismatch: '+name+'/'+key)
    analysis.require(result['on_range'] == report['recorded_on_range'] == 1,
                     'Require fixed 10 A recording')
    onset, _ = analysis.select_onset(signals)
    analysis.require(onset == report['current_onset']['sample_id'], 'Onset changed')
    analysis.require(report.get('gpio_interpretation', {}).get('explicit_remapping') is True,
                     'Explicit physical GPI mapping required')
    logical = dict(signals)
    logical['gpi0'], logical['gpi1'] = signals['gpi1'], signals['gpi0']
    markers = analysis.decode_markers(logical, onset, '11')
    analysis.require(markers['unique_complete_train'], 'Need unique 11-marker train')
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


def samples(signals, onset, duration_ms):
    count = round(duration_ms/1000*FS)
    values = analysis.slice_signal(signals, 'current', onset, onset+count)
    analysis.require(values is not None and np.all(np.isfinite(values)),
                     'Incomplete/nonfinite plotted current interval')
    return np.array(values, copy=True)


def mean_curve(current, bin_ms):
    width = round(bin_ms/1000*FS)
    bins = len(current)//width
    means = current[:bins*width].reshape(bins, width).mean(axis=1, dtype=np.float64)*1000
    return (np.arange(bins)+.5)*bin_ms, means


def prepare(path, group, run):
    report, signals, checks, onset, markers, exposure, cycle = check_report(path)
    fixed = analysis.metrics(signals, onset+FS//200, onset+FS//100, onset)
    analysis.require(fixed['valid'], 'Invalid 5–10 ms interval')
    startup = {}
    for name, duration in WINDOWS.items():
        metrics = analysis.metrics(signals, onset, onset+round(duration/1000*FS), onset)
        analysis.require(metrics['valid'], 'Invalid startup window '+name)
        previous = report['startup_windows_raw_unqualified'][name]
        for key in ('charge_mC', 'positive_charge_mC', 'negative_charge_mC', 'energy_mJ', 'current_max'):
            analysis.require(np.isclose(metrics[key], previous[key], rtol=1e-12),
                             'Startup analysis differs: '+name+'/'+key)
        analysis.require(metrics['native_peak_unqualified'] == previous['native_peak_unqualified'],
                         'Startup peak differs: '+name)
        analysis.require(metrics['current_above_A'] == previous['current_above_A'],
                         'Startup threshold durations differ: '+name)
        startup[name] = metrics
    post = cycle['post5ms_to_plateau']
    duration = float(np.ceil(post['end_ms'])+100)
    full = mean_curve(samples(signals, onset, duration), 1)
    early = samples(signals, onset, 5)
    binned10 = mean_curve(samples(signals, onset, 10), .25)
    qualified_bins = (full[0] >= 5) & (full[0]+.5 <= post['end_ms'])
    row = dict(group=group, run=run, label=group+' '+run[-2:],
               first_strobe_ms=next(e['time_ms'] for e in markers['events'] if e['id'] == 2),
               exposure_mirror_ms=exposure['duration_ms'],
               current_5_to_10ms_mA=fixed['current_mean_mA'],
               post5ms_to_plateau_mean_mA=post['current_mean_mA'],
               post5ms_to_plateau_energy_mJ=post['energy_mJ'],
               plateau_from_onset_ms=post['end_ms'],
               plateau_current_mA_fixed10A=cycle['low_plateau_100ms']['current_mean_mA'],
               post5ms_peak_1ms_mean_mA=float(np.max(full[1][qualified_bins])),
               source_mean_V=post['voltage_mean'], eleven_markers=True, one_exposure_mirror=True)
    for name, metrics in startup.items():
        for key in ('charge_mC', 'positive_charge_mC', 'negative_charge_mC', 'energy_mJ'):
            row[name+'_'+key] = metrics[key]
        peak = metrics['native_peak_unqualified']
        row[name+'_peak_A'] = peak['current_A']
        row[name+'_peak_time_us'] = peak['time_from_onset_us']
        row[name+'_peak_range_code'] = peak['range_code']
        for threshold, event in metrics['current_above_A'].items():
            row[name+'_above_'+threshold+'A_us'] = event['duration_us']
            row[name+'_longest_above_'+threshold+'A_us'] = event['longest_contiguous_us']
    source = dict(analysis=str(path.resolve()), analysis_sha256=analysis.sha(path),
                  trace=report['trace'], checks=checks,
                  index_sha256=report['source_index_sha256'], result_sha256=report['result_sha256'],
                  mapping=report['gpio_interpretation'], onset_sample_id=onset,
                  startup_windows_raw_unqualified=startup, current_5_to_10ms=fixed,
                  post5ms_to_plateau=post, marker_decode=markers, external_exposure_mirror=exposure)
    return row, source, dict(full=full, early=early, first10ms=binned10)


def summarize(rows):
    fields = [key for key, value in rows[0].items()
              if isinstance(value, (float, int)) and not isinstance(value, bool)]
    out = {}
    for group in GROUPS:
        selected = [row for row in rows if row['group'] == group]
        out[group] = {'count': len(selected)}
        for field in fields:
            values = [row[field] for row in selected]
            out[group][field] = dict(min=min(values), median=float(np.median(values)), max=max(values))
    out['removed_minus_fitted_median'] = {}
    for field in fields:
        baseline = out[GROUPS[0]][field]['median']
        new = out[GROUPS[1]][field]['median']
        out['removed_minus_fitted_median'][field] = dict(
            absolute=new-baseline, percent=None if baseline == 0 else (new/baseline-1)*100)
    return out


def tables(rows, summary):
    lines = ['C17 removed: three new cold cycles versus the latest three low-current controls', '',
             'Direct regulated 5 V through JS110; no LiPo/LTC/battery losses are included.',
             'All startup values below are raw, unqualified instrument observations, not guaranteed physical inrush.', '',
             '| Run | Peak, first 250 µs (A) | Peak time (µs) | Net Q 250 µs (mC) | Net Q 1 ms (mC) | Net Q 5 ms (mC) |',
             '|---|---:|---:|---:|---:|---:|']
    for row in rows:
        lines.append('| {} | {:.4f} | {:.1f} | {:.6f} | {:.6f} | {:.6f} |'.format(
            row['label'], row['0.25ms_peak_A'], row['0.25ms_peak_time_us'],
            row['0.25ms_charge_mC'], row['1ms_charge_mC'], row['5ms_charge_mC']))
    lines.extend(['', 'Time above thresholds within the first 5 ms (sum of all native sample intervals):', '',
                  '| Run | >1 A (µs) | >3 A (µs) | >5 A (µs) | >7 A (µs) |',
                  '|---|---:|---:|---:|---:|'])
    for row in rows:
        lines.append('| {} | {:.1f} | {:.1f} | {:.1f} | {:.1f} |'.format(
            row['label'], *(row['5ms_above_'+str(threshold)+'A_us'] for threshold in (1, 3, 5, 7))))
    lines.extend(['', 'Active metrics exclude the first 5 ms and end at the detected low plateau:', '',
                  '| Run | 5–10 ms (mA) | Active mean (mA) | Energy (mJ) | Low plateau begins (ms) | First strobe (ms) |',
                  '|---|---:|---:|---:|---:|---:|'])
    for row in rows:
        lines.append('| {label} | {current_5_to_10ms_mA:.2f} | {post5ms_to_plateau_mean_mA:.2f} | '
                     '{post5ms_to_plateau_energy_mJ:.2f} | {plateau_from_onset_ms:.2f} | '
                     '{first_strobe_ms:.3f} |'.format(**row))
    lines.extend(['', 'All six source records passed raw hashes, sample continuity, eleven markers and one exposure mirror.',
                  'Current onset is a threshold, not proven target power-good. JS voltage is upstream of the DUT.',
                  'Net charge retains negative samples; positive/negative charge, window peaks and all thresholds are in summary.json.',
                  'Fixed 10 A low-current averages do not supersede a separate auto-range sleep measurement.',
                  'SD history and elapsed time vary. These measurements do not establish target-rail stability or C17-only causality.',
                  'The power-trace analysis does not itself verify saved images or independently prove MCU Standby.'])
    return '\n'.join(lines)+'\n'


def draw(rows, curves, out):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.8), gridspec_kw={'width_ratios': [1.8, 1]})
    fig2, startup_axes = plt.subplots(2, 2, figsize=(13, 8.5))
    for row, curve in zip(rows, curves):
        index = int(row['run'][-2:])-1
        kw = dict(label=row['label'], color=COLORS[row['group']][index], linewidth=1.3,
                  linestyle='--' if row['group'] == GROUPS[0] else '-', alpha=.9)
        for axis, name in zip(axes, ('full', 'first10ms')):
            axis.plot(*curve[name], **kw)
        for index, duration in enumerate((.25, 5)):
            current = curve['early'][:round(duration/1000*FS)]
            scale = 1e6 if index == 0 else 1e3
            time = np.arange(len(current))/FS*scale
            startup_axes[index, 0].plot(time, current, **kw)
            charge = np.r_[0., np.cumsum(current, dtype=np.float64)/FS*1000]
            startup_axes[index, 1].plot(np.arange(len(charge))/FS*scale, charge, **kw)
    for axis in axes:
        axis.axvspan(0, 5, color='#ded9ce', alpha=.6, zorder=-1)
        axis.set(xlabel='Milliseconds from measured current onset', ylabel='Current (mA)')
        axis.grid(color='#e0e5e9', linewidth=.7)
    axes[0].set(xlim=(0, max(max(curve['full'][0]) for curve in curves)),
                title='Capture → save → low plateau · 1 ms means')
    axes[1].set(xlim=(0, 10), title='First 10 ms · 0.25 ms means')
    axes[1].text(.02, .96, 'Shaded 0–5 ms: startup amplitude unqualified',
                 transform=axes[1].transAxes, va='top', fontsize=8.5, color='#665c4e')
    fig.suptitle('C17 removal: whole-board current before and after', fontsize=16, fontweight='bold')
    fig.legend(*axes[0].get_legend_handles_labels(), loc='upper center', bbox_to_anchor=(.5, .91),
               ncol=3, frameon=False, fontsize=9)
    fig.text(.06, .065, 'Latest low-current controls; direct regulated 5 V input, fixed 10 A range, unchanged normal firmware. C14 remains removed.', fontsize=9)
    fig.text(.06, .035, 'First 5 ms remains unqualified; JS voltage is source-side. Card timing varies; saved-image verification is a separate check.', fontsize=9)
    fig.subplots_adjust(left=.065, right=.985, top=.75, bottom=.2, wspace=.22)
    fig.savefig(out/'current-comparison.png', dpi=180)
    fig.savefig(out/'current-comparison.svg')
    plt.close(fig)
    for index, (duration, scale, units) in enumerate(((.25, 1e3, 'µs'), (5, 1, 'ms'))):
        startup_axes[index, 0].set_ylabel('Native sampled current (A)')
        startup_axes[index, 1].set_ylabel('Net accumulated charge (mC)')
        startup_axes[index, 0].set_title('First '+('250 µs' if index == 0 else '5 ms'))
        startup_axes[index, 1].set_title('Signed integral of the same current samples')
        for axis in startup_axes[index]:
            axis.set(xlim=(0, duration*scale), xlabel='Time from measured current onset ('+units+')')
            axis.grid(color='#e0e5e9', linewidth=.7)
            axis.axhline(0, color='#84919c', linewidth=.6)
    fig2.suptitle('C17 removal: initial current and charge — unqualified startup observations', fontsize=15, fontweight='bold')
    fig2.legend(*startup_axes[0, 0].get_legend_handles_labels(), loc='upper center', bbox_to_anchor=(.5, .94),
                ncol=3, frameon=False, fontsize=9)
    fig2.text(.065, .035, 'Direct regulated 5 V, fixed 10 A recording; source-side voltage only. Native peaks, clipping and target rail response are not independently qualified.', fontsize=8.5)
    fig2.text(.065, .014, 'Current onset is a threshold. The negative transient is retained in net charge, not silently rectified. Both groups use the latest low-current state.', fontsize=8.5)
    fig2.subplots_adjust(left=.08, right=.985, top=.83, bottom=.1, hspace=.38, wspace=.22)
    fig2.savefig(out/'startup-current-charge.png', dpi=180)
    fig2.savefig(out/'startup-current-charge.svg')
    plt.close(fig2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=HERE)
    args = parser.parse_args()
    out = args.out.resolve()
    out.relative_to(HERE)
    for name in OUTPUTS:
        analysis.require(not (out/name).exists(), 'Do not overwrite existing output: '+name)
    paths = [(folder/('cold-normal%02d'%index)/'analysis.json', group, 'cold-normal%02d'%index)
             for folder, group in ((BASELINE, GROUPS[0]), (CAMPAIGN, GROUPS[1]))
             for index in range(1, 4)]
    for path, *_ in paths:
        analysis.require(path.is_file(), 'Required completed analysis missing: '+str(path))
    rows, proofs, curves = [], [], []
    for path, group, run in paths:
        row, proof, curve = prepare(path, group, run)
        rows.append(row); proofs.append(proof); curves.append(curve)
        gc.collect()
        print('Verified '+row['label'], flush=True)
    summary = summarize(rows)
    out.mkdir(parents=True, exist_ok=True)
    report = dict(complete_three_new_runs=True, source_script_sha256=analysis.sha(__file__),
                  analyzer_sha256=analysis.sha(CAMPAIGN/'analyze_inrush.py'),
                  remapping_sha256=analysis.sha(CAMPAIGN/'analyze_swapped.py'),
                  rows=rows, group_summary=summary, sources=proofs,
                  boundary='Direct regulated 5 V input. JS voltage is source-side; no LiPo/LTC/battery loss included.',
                  first5ms_qualified=False, clipping_independently_qualified=False,
                  causal_component_isolation=False, independent_image_verification_in_this_report=False)
    save_json(out/'summary.json', report)
    (out/'summary.md').write_text(tables(rows, summary), encoding='utf-8')
    draw(rows, curves, out)
    print(json.dumps(dict(output=str(out), complete=True, summary=summary), indent=2))


if __name__ == '__main__':
    main()
