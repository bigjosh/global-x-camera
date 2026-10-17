"""Plot one measured boot from the raw Logic CSV and boot-summary.json."""
import argparse
import csv
import json
from pathlib import Path
import sys

repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo / 'tmp/bringup/plot-deps'))
sys.path.insert(0, str(repo / 'firmware/bringup'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from probe_capture import columns, read_digital

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('capture', type=Path)
p.add_argument('output', type=Path)
args = p.parse_args()
data = json.loads((args.capture / 'boot-summary.json').read_text())
cycle = data['cycles'][0]
t0 = cycle['target_5v_4_5v_crossing_s']
t_reset = (cycle['nrst_rise_s'] - t0) * 1000
t_gpio = cycle['target_5v_to_pd0_ms']
times, rails = [], {3: [], 4: []}
with (args.capture / 'analog.csv').open(newline='', encoding='utf-8-sig') as f:
    rows = csv.DictReader(f)
    tc, names = columns(rows.fieldnames)
    for row in rows:
        t = (float(row[tc]) - t0) * 1000
        if t < -3:
            continue
        if t > 70:
            break
        times.append(t)
        for ch in rails:
            rails[ch].append(float(row[names[ch]]))

plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
                     'axes.spines.top': False, 'axes.spines.right': False})
fig, axes = plt.subplots(3, 1, figsize=(10, 6), sharex=True,
                         gridspec_kw={'height_ratios': [2, 1, 1]}, layout='constrained')
fig.suptitle(f'First GPIO after board power-up — {t_gpio:.2f} ms', fontsize=18, fontweight='bold')
axes[0].plot(times, rails[4], color='#c76313', label='Target 5 V')
axes[0].plot(times, rails[3], color='#008578', label='Auxiliary 3.3 V')
axes[0].set(ylabel='Voltage (V)', ylim=(-.3, 5.5))
axes[0].legend(loc='lower right', frameon=False, ncol=2)
signals = read_digital(args.capture / 'digital.csv')['channels']
for ax, ch, title, color in [(axes[1], 0, 'NRST', '#526074'), (axes[2], 1, 'PD0', '#2365b7')]:
    signal = signals[ch]
    level = signal['initial']
    xs, ys = [-3], [level]
    for t, value in signal['edges']:
        x = (t - t0) * 1000
        if x < -3:
            ys[0] = value
        elif x <= 70:
            xs.append(x)
            ys.append(value)
    xs.append(70)
    ys.append(ys[-1])
    ax.step(xs, ys, where='post', color=color, linewidth=2)
    ax.set(ylim=(-.25, 1.4), yticks=[0, 1], yticklabels=['Low', 'High'], ylabel=title)
for ax in axes:
    ax.set_xlim(-3, 70)
    ax.grid(axis='x', alpha=.16)
    ax.axvline(0, color='#9a9a9a', linewidth=1, linestyle=':')
    ax.axvline(t_reset, color='#526074', linewidth=1, linestyle=':')
    ax.axvline(t_gpio, color='#2365b7', linewidth=1, linestyle=':')
axes[1].annotate('', xy=(t_reset, 1.21), xytext=(0, 1.21),
                 arrowprops={'arrowstyle': '<->', 'color': '#526074'})
axes[1].text(t_reset / 2, 1.24, f'Reset held low: {t_reset:.2f} ms', ha='center', va='bottom', color='#526074')
axes[2].annotate('', xy=(t_gpio, 1.21), xytext=(t_reset, 1.21),
                 arrowprops={'arrowstyle': '<->', 'color': '#2365b7'})
axes[2].text((t_reset + t_gpio) / 2, 1.24, f'{t_gpio - t_reset:.2f} ms', ha='center', va='bottom', color='#2365b7')
axes[2].set_xlabel('Time from target 5 V reaching 4.50 V (ms)')
fig.text(.01, -.025, 'NUCLEO-N657X0-Q · 256-byte boot payload · USB power cycle · 16 Oct 2026\n'
         'Voltage reference is a measured board rail, not an MCU PGOOD pin. Camera initialization is not included.',
         fontsize=9, color='#526074')
args.output.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(args.output, dpi=160, bbox_inches='tight')
svg_path = args.output.with_suffix('.svg')
fig.savefig(svg_path, bbox_inches='tight')
svg_path.write_text('\n'.join(line.rstrip() for line in svg_path.read_text().splitlines()) + '\n')
print(args.output.resolve())
