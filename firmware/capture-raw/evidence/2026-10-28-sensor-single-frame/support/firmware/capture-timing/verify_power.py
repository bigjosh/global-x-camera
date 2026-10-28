"""Offline verification that monitored target rails remained powered."""
import argparse
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'boot-timing'))
from inspect_cycle import read_csv

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('folder', type=Path)
a = p.parse_args()
t, v = read_csv(a.folder / 'analog.csv')
dt, dv = read_csv(a.folder / 'digital.csv', digital=True)
stats = {str(ch): dict(min_v=min(v[ch]), max_v=max(v[ch]), mean_v=statistics.mean(v[ch]))
         for ch in (3, 4, 5)}
checks = {f'rail_{ch}': low <= stats[str(ch)]['min_v'] <= stats[str(ch)]['max_v'] <= high
          for ch, low, high in [(3, 2.97, 3.6), (4, 4.5, 5.5), (5, 2.97, 3.6)]}
checks['reset_and_early_marker_remain_high'] = all(min(dv[ch]) == 1 for ch in (0, 1))
result = dict(passed=all(checks.values()), checks=checks, rails=stats, duration_s=t[-1]-t[0],
              limitation='Named rails only; no direct core, AON or camera-rail probe.')
with (a.folder / 'powered-state.json').open('x') as out:
    json.dump(result, out, indent=2)
print(json.dumps(result, indent=2))
if not result['passed']:
    raise SystemExit(1)
