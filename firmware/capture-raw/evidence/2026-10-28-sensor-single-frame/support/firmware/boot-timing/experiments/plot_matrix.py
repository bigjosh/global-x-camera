"""Plot measured analyze_matrix.py output as PNG and SVG, offline.

Usage: python firmware/boot-timing/experiments/plot_matrix.py INPUT.json OUTPUT.png
Uses the existing ignored tmp/bringup/plot-deps Matplotlib installation.
Failed/incomplete runs are omitted and identified in the figure footnote.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tmp/bringup/plot-deps'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('analysis', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    data = json.loads(args.analysis.read_text(encoding='utf-8-sig'))
    runs = [run for run in data['runs'] if run['passed']]
    if not runs:
        parser.error('No passed runs to plot')
    plt.rcParams.update({'font.size': 10, 'axes.spines.top': False,
                         'axes.spines.right': False, 'svg.fonttype': 'none',
                         'svg.hashsalt': 'global-x-camera-boot-matrix-v1'})
    tiny_runs = [run for run in runs if 'tiny' in run['label'].lower()]
    if tiny_runs:
        fig, (left, right, tiny_ax) = plt.subplots(1, 3, figsize=(16, 6),
            gridspec_kw={'width_ratios': [1.5, 1.1, .8]})
    else:
        fig, (left, right) = plt.subplots(1, 2, figsize=(13, 5.6), gridspec_kw={'width_ratios': [1.2, 1]})
        tiny_ax = None
    fig.subplots_adjust(top=.78, bottom=.26, left=.065, right=.97, wspace=.36)
    fig.suptitle('STM32N6 first-GPIO boot timing', x=.065, ha='left', y=.97,
                 fontsize=19, fontweight='bold')
    fig.text(.065, .885, 'Autonomous CN8 power cycles · identical marker code for baseline and padded images',
             fontsize=11, color='#455466')
    x = list(range(len(runs)))
    series = [('target_0_5v_final_to_pd0_ms', 'Target 5 V ≥0.5 V', '#00826b'),
              ('nrst_to_pd0_ms', 'NRST rising edge', '#225ea8'),
              ('main_vddio_2_97v_final_to_pd0_ms', 'Main VDDIO ≥2.97 V', '#9a551b')]
    for metric, label, color in series:
        ys = [run['metrics'][metric] for run in runs]
        left.plot(x, ys, 'o-', color=color, label=label, linewidth=1.6, markersize=5)
    left.set_xticks(x, [run['label'] for run in runs], rotation=30, ha='right', fontsize=8.5)
    left.set_xlim(-.25, len(runs) - .75 if len(runs) > 1 else .25)
    left.set_ylim(bottom=0)
    left.set_ylabel('Time to PD0 rising edge (ms)')
    left.set_title('Recorded sequence', loc='left', fontsize=12, pad=12)
    left.grid(axis='y', alpha=.18)
    left.legend(loc='lower left', frameon=False, fontsize=9)
    for index, run in enumerate(runs):
        if 'tiny' in run['label'].lower():
            left.axvspan(index - .3, index + .3, color='#d4dbe3', alpha=.3, zorder=0)
    comparable = [run for run in runs if 'tiny' not in run['label'].lower() and run['added_image_bytes'] >= 0]
    baselines = [run['metrics']['nrst_to_pd0_ms'] for run in comparable if run['added_image_bytes'] == 0]
    if baselines and len({run['added_image_bytes'] for run in comparable}) >= 2:
        baseline = statistics.mean(baselines)
        max_kib = max(run['added_image_bytes'] for run in comparable) / 1024
        expected = 1024 * 8 / data['expected_spi_hz_assumption'] * 1000
        right.plot([0, max_kib], [0, max_kib * expected], '--', color='#8796a7', linewidth=1.5,
                   label=f"{data['expected_spi_hz_assumption']/1e6:g} MHz SPI prediction: {expected:.3f} ms/KiB")
        size_groups = {}
        for run in comparable:
            kib = run['added_image_bytes'] / 1024
            delta = run['metrics']['nrst_to_pd0_ms'] - baseline
            right.scatter(kib, delta, color='#225ea8', s=35, zorder=3)
            size_groups.setdefault(kib, []).append(delta)
        for kib, values in size_groups.items():
            name = 'baseline' if kib == 0 else f'+{kib:g} KiB'
            right.annotate(f'{name} (n={len(values)})', (kib, max(values)),
                           xytext=(6, 9), textcoords='offset points', fontsize=8)
        fit = next((fit for fit in data['fits'] if fit['metric'] == 'nrst_to_pd0_ms'
                    and fit['status'] == 'descriptive_fit'), None)
        if fit:
            right.plot([0, max_kib], [fit['intercept_ms'] - baseline,
                       fit['intercept_ms'] - baseline + max_kib * fit['slope_ms_per_kib']],
                       color='#225ea8', linewidth=1, alpha=.6,
                       label=f"Measured fit: {fit['slope_ms_per_kib']:.3f} ms/KiB")
        right.set_xlim(-1, max_kib * 1.12 + 1)
        right.axhspan(min(baselines) - baseline, max(baselines) - baseline,
                      color='#225ea8', alpha=.09, label='Observed baseline range')
        right.set_xlabel('Added boot-image data (KiB)')
        right.set_ylabel('NRST-to-PD0 increase vs mean baseline (ms)')
        right.xaxis.set_major_locator(MaxNLocator(integer=True))
        right.legend(loc='upper left', frameon=False, fontsize=9)
    else:
        right.text(.5, .5, 'Awaiting comparable size variants', ha='center', va='center', transform=right.transAxes)
    right.set_title('Dependence on image size', loc='left', fontsize=12, pad=12)
    right.grid(alpha=.18)
    if tiny_ax is not None and baselines:
        tiny = [run['metrics']['nrst_to_pd0_ms'] for run in tiny_runs]
        tiny_ax.axhspan(min(baselines), max(baselines), color='#225ea8', alpha=.09)
        for xpos, values, color in [(0, baselines, '#225ea8'), (1, tiny, '#8b4a9e')]:
            jitter = [(i - (len(values) - 1) / 2) * .07 for i in range(len(values))]
            tiny_ax.scatter([xpos + j for j in jitter], values, color=color, s=35, zorder=3)
            mean = statistics.mean(values)
            tiny_ax.plot([xpos - .2, xpos + .2], [mean, mean], color=color, linewidth=2)
        tiny_ax.set_xlim(-.5, 1.5)
        tiny_ax.set_ylim(min(baselines + tiny) - .2, max(baselines + tiny) + .25)
        tiny_ax.set_xticks([0, 1], [f'Baseline\nn={len(baselines)}', f'Tiny code\nn={len(tiny)}'])
        tiny_ax.set_ylabel('NRST-to-PD0 time (ms)')
        tiny_ax.set_title('Repeat variation', loc='left', fontsize=12, pad=12)
        tiny_ax.grid(axis='y', alpha=.18)
        tiny_ax.text(.03, .97, 'Points: each cycle\nLines: group means\nBand: baseline range',
                     transform=tiny_ax.transAxes, va='top', fontsize=8, color='#455466')
    omitted = [run['label'] for run in data['runs'] if not run['passed']]
    analog = max(run['analog_spacing_us'] for run in runs)
    digital = max(run['digital_spacing_us'] for run in runs)
    footer = f'Analog spacing {analog:g} µs; digital spacing {digital:g} µs. Voltage thresholds are bench references, not PGOOD.\n'
    footer += 'All plotted cycles pass sustained measured-rail discharge and stable-final-level checks. Tiny code is excluded from the size fit.\n'
    footer += 'Small bench sample; fitted slope is descriptive, with no confidence interval.'
    if omitted:
        footer += '\nOmitted failed/incomplete runs: ' + ', '.join(omitted)
    fig.text(.065, .045, footer, fontsize=8.5, color='#455466', va='bottom', linespacing=1.5)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=180, facecolor='white')
    svg = args.output.with_suffix('.svg')
    fig.savefig(svg, facecolor='white', metadata={'Date': None})
    def identity(path):
        payload = path.read_bytes()
        return {'path': str(path.resolve()), 'bytes': len(payload),
                'sha256': hashlib.sha256(payload).hexdigest()}
    provenance = {'generated_utc': datetime.now(timezone.utc).isoformat(),
                  'analysis': identity(args.analysis),
                  'plot_script': identity(Path(__file__)),
                  'analysis_script': identity(Path(__file__).with_name('analyze_matrix.py')),
                  'matplotlib_version': matplotlib.__version__,
                  'plotted_labels': [run['label'] for run in runs],
                  'omitted_labels': omitted,
                  'outputs': [identity(args.output), identity(svg)]}
    sidecar = args.output.with_suffix('.provenance.json')
    sidecar.write_text(json.dumps(provenance, indent=2) + '\n', encoding='utf-8')
    print(args.output)
    print(svg)
    print(sidecar)


if __name__ == '__main__':
    main()
