"""Offline comparison of 2.2-ohm recordings with C17-removed controls.

No instrument imports or commands. Requires three completed, explicitly GPI-
remapped analysis.json files in each group and rechecks their raw stream hashes,
continuity, range, markers, exposure envelope, onset and cycle metrics using the
already qualified C17 comparison reader. New outputs never overwrite evidence.
"""
import argparse
import gc
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASELINE = HERE.parent / 'c17-removed-20261106'
REFERENCE = BASELINE / 'report' / 'compare_c17.py'
spec = importlib.util.spec_from_file_location('verified_c17_comparison', REFERENCE)
ref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ref)
np, plt, core = ref.np, ref.plt, ref.analysis


def prepare(path, group, run, resistance):
    report, signals, checks, onset, markers, exposure, cycle = ref.check_report(path)
    first = core.metrics(signals, onset, onset + round(.00025 * core.FS), onset)
    second = core.metrics(signals, onset + round(.00025 * core.FS),
                          onset + round(.005 * core.FS), onset)
    post = cycle['post5ms_to_plateau']
    total = cycle['onset_to_plateau_raw_unqualified']
    for window in (first, second, post, total):
        core.require(window['valid'], 'Invalid required current/power interval')
    current = core.slice_signal(signals, 'current', post['start_sample_id'],
                                post['end_sample_id_exclusive'])
    core.require(current is not None and np.all(np.isfinite(current)),
                 'Incomplete/nonfinite I-squared integration window')
    current = np.asarray(current, dtype=np.float64)
    i2 = float(np.sum(current * current) / core.FS)
    full = ref.mean_curve(ref.samples(signals, onset, np.ceil(total['end_ms']) + 50), 1)
    valid_bins = (full[0] - .5 >= 5) & (full[0] + .5 <= total['end_ms'])
    core.require(np.any(valid_bins), 'Missing full one-ms post-startup bins')
    phase = cycle['phase_windows_overlapping_not_additive']
    row = {
        'group': group, 'run': run,
        'first_250us_peak_A': first['current_max'],
        'first_250us_peak_time_us': first['native_peak_unqualified']['time_from_onset_us'],
        'first_250us_signed_charge_mC': first['charge_mC'],
        'secondary_250us_to_5ms_peak_A': second['current_max'],
        'secondary_peak_time_ms': second['native_peak_unqualified']['time_from_onset_us'] / 1000,
        'full_cycle_energy_mJ_unqualified_startup': total['energy_mJ'],
        'post5ms_energy_mJ': post['energy_mJ'],
        'post5ms_mean_current_mA': post['current_mean_mA'],
        'post5ms_peak_1ms_mean_mA': float(np.max(full[1][valid_bins])),
        'onset_to_plateau_ms': total['end_ms'],
        'first_exposure_mirror_ms': exposure['rise_ms'],
        'exposure_duration_ms': exposure['duration_ms'],
        'source_mean_voltage_post5ms_V': post['voltage_mean'],
        'fixed10A_plateau_mean_mA': cycle['low_plateau_100ms']['current_mean_mA'],
        'post5ms_I_squared_integral_A2_s': i2,
        'post5ms_nominal_R_heat_mJ': 1000 * resistance * i2,
        'nominal_R_ohms_for_heat_projection': resistance,
        'eleven_phase_markers': True, 'one_exposure_mirror': True,
        'phases_overlapping_not_additive': {
            name: {key: value[key] for key in ('start_ms', 'end_ms', 'duration_ms',
                  'energy_mJ', 'current_mean_mA')} for name, value in phase.items()
        },
    }
    source = {
        'analysis_path': str(path.resolve()), 'analysis_sha256': core.sha(path),
        'trace': report['trace'], 'checks_reverified': checks,
        'index_sha256': report['source_index_sha256'],
        'result_sha256': report['result_sha256'],
        'onset_sample_id': onset, 'recorded_on_range': report['recorded_on_range'],
        'first_250us_raw_unqualified': first,
        'secondary_250us_to_5ms_raw_unqualified': second,
        'post5ms_to_plateau': post, 'full_cycle_raw_unqualified': total,
        'marker_decode': markers, 'external_exposure_mirror': exposure,
        'gpio_interpretation': report['gpio_interpretation'],
    }
    return row, source, {'early': ref.samples(signals, onset, 5), 'full': full}


def summary(rows, labels):
    keys = [k for k, v in rows[0].items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)]
    groups = {}
    for label in labels:
        selected = [r for r in rows if r['group'] == label]
        groups[label] = {'count': len(selected)}
        for key in keys:
            values = [r[key] for r in selected]
            groups[label][key] = {'min': min(values), 'median': float(np.median(values)),
                                  'max': max(values)}
    difference = {}
    for key in keys:
        a, b = [groups[label][key]['median'] for label in labels]
        difference[key] = {'absolute': b-a, 'percent': (b/a-1)*100 if a else None}
    return {'groups': groups, 'candidate_minus_baseline_median': difference}


def draw(rows, curves, labels, out):
    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    colors = ['#987b67', '#b1947d', '#7e7269', '#087e8b', '#287eb7', '#2e9c86']
    for row, curve, color in zip(rows, curves, colors):
        label = f"{row['group']} {row['run'][-2:]}"
        style = '--' if row['group'] == labels[0] else '-'
        t = np.arange(len(curve['early'])) * 1000 / core.FS
        for ax, mask in ((axes[0, 0], t < .25), (axes[0, 1], t >= .25)):
            ax.plot(t[mask], curve['early'][mask], style, color=color, lw=1.2, label=label)
        axes[1, 0].plot(*curve['full'], style, color=color, lw=1.2)
    axes[0, 0].set(title='Initial charging: first 250 us', xlabel='Time from current onset (ms)', ylabel='Native sampled current (A)')
    axes[0, 1].set(title='Secondary startup: 0.25-5 ms', xlabel='Time from current onset (ms)', ylabel='Native sampled current (A)')
    axes[1, 0].set(title='Capture cycle: 1 ms mean current', xlabel='Time from current onset (ms)', ylabel='Current (mA)')
    names = [f"{r['group']}\n{r['run'][-2:]}" for r in rows]
    axes[1, 1].bar(names, [r['post5ms_energy_mJ'] for r in rows], color=colors)
    axes[1, 1].set(title='Energy from 5 ms to low-current plateau', ylabel='Measured source-side energy (mJ)')
    axes[1, 1].tick_params(axis='x', labelsize=8)
    for ax in axes.flat:
        ax.grid(alpha=.22)
        ax.set_axisbelow(True)
    fig.suptitle(f'{labels[0]} versus {labels[1]}: measured current and energy', fontweight='bold')
    fig.legend(*axes[0, 0].get_legend_handles_labels(), loc='upper center', bbox_to_anchor=(.5, .95), ncol=3, frameon=False, fontsize=8)
    fig.text(.06, .025, 'Fixed 10 A JS recordings; startup peaks are instrument observations. Voltage is upstream: no DUT rail/ramp qualification.', fontsize=8)
    fig.text(.06, .008, 'SD latency can change whole-cycle energy independently of the resistor. Image verification is separate from this analysis.', fontsize=8)
    fig.subplots_adjust(top=.83, bottom=.12, hspace=.37, wspace=.24)
    fig.savefig(out/'comparison.png', dpi=180)
    fig.savefig(out/'comparison.svg')
    plt.close(fig)


def markdown(rows, totals, labels):
    lines = ['# Series-resistor comparison', '',
             'Offline reanalysis of completed recordings; no hardware operations.', '',
             '| Run | First peak (A) | Secondary peak (A) | Secondary time (ms) | Exposure (ms) | Cycle (ms) | Energy after 5 ms (mJ) | Full energy incl. unqualified startup (mJ) |',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        values = [r[k] for k in ('first_250us_peak_A', 'secondary_250us_to_5ms_peak_A',
                  'secondary_peak_time_ms', 'first_exposure_mirror_ms', 'onset_to_plateau_ms',
                  'post5ms_energy_mJ', 'full_cycle_energy_mJ_unqualified_startup')]
        lines.append('| '+r['group']+' '+r['run'][-2:]+' | '+' | '.join(f'{v:.4f}' for v in values)+' |')
    lines += ['', 'All six runs must have a unique eleven-marker train and one bounded exposure mirror. No image-readback claim is made here.', '',
              '| Median metric | '+labels[0]+' | '+labels[1]+' | Change |', '|---|---:|---:|---:|']
    for key in ('first_250us_peak_A', 'secondary_250us_to_5ms_peak_A', 'post5ms_energy_mJ',
                'full_cycle_energy_mJ_unqualified_startup', 'onset_to_plateau_ms',
                'first_exposure_mirror_ms', 'post5ms_peak_1ms_mean_mA', 'post5ms_nominal_R_heat_mJ'):
        a,b=[totals['groups'][label][key]['median'] for label in labels]
        percent=totals['candidate_minus_baseline_median'][key]['percent']
        lines.append(f'| {key} | {a:.5f} | {b:.5f} | {percent:+.2f}% |')
    lines += ['', 'Phase windows overlap and must not be added. Per-run phase timings/energies and sample identities are in summary.json.', '',
              'Nominal I²R heat is calculated from recorded current, not independently measured resistor temperature/power or added source energy. The baseline value is counterfactual. Converter behavior and LDO losses can change.', '',
              'Source-side voltage does not measure DUT input after the resistor or downstream MCU rails. This analysis cannot qualify rail droop/rise times, minimum boot voltage, or physical unclipped startup extrema.', '',
              'No LiPo/LTC/battery loss is included. SD service-time variation prevents assigning total-energy differences solely to the resistor.', '']
    return '\n'.join(lines)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', type=Path, default=BASELINE)
    p.add_argument('--candidate', type=Path, default=HERE)
    p.add_argument('--baseline-label', default='No resistor')
    p.add_argument('--candidate-label', default='2.2 ohms')
    p.add_argument('--resistance', type=float, default=2.2)
    p.add_argument('--out', type=Path, default=HERE/'comparison-report')
    args=p.parse_args()
    out=args.out.resolve(); out.relative_to(HERE)
    core.require(not out.exists(), 'Output already exists; select a new output directory')
    core.require(args.resistance > 0, 'Resistance must be positive')
    labels=(args.baseline_label,args.candidate_label)
    core.require(labels[0] != labels[1], 'Group labels must differ')
    inputs=[(folder/f'cold-normal{n:02d}'/'analysis.json',label,f'cold-normal{n:02d}')
            for folder,label in ((args.baseline,labels[0]),(args.candidate,labels[1]))
            for n in range(1,4)]
    for path,_,_ in inputs: core.require(path.is_file(),'Missing completed analysis: '+str(path))
    rows=[]; sources=[]; curves=[]
    for path,label,run in inputs:
        row,source,curve=prepare(path,label,run,args.resistance)
        rows.append(row); sources.append(source); curves.append(curve)
        gc.collect(); print('Verified '+label+' '+run,flush=True)
    totals=summary(rows,labels)
    out.mkdir(parents=True)
    report={'kind':'offline comparison of six fixed-range cold recordings',
            'source_script_sha256':core.sha(__file__), 'verifier_sha256':core.sha(REFERENCE),
            'groups':labels,'rows':rows,'summary':totals,'sources':sources,
            'first5ms_independently_qualified':False,'DUT_voltage_measured':False,
            'image_readback_verified_by_this_script':False,
            'boundary':'Measured JS upstream voltage/current; no downstream rail/ramp or battery efficiency qualification.'}
    ref.save_json(out/'summary.json',report)
    (out/'summary.md').write_text(markdown(rows,totals,labels),encoding='utf-8')
    draw(rows,curves,labels,out)
    print(json.dumps({'complete':True,'output':str(out),'summary':totals},indent=2))


if __name__=='__main__': main()
