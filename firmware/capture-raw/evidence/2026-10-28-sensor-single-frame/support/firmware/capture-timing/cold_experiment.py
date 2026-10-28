"""Measure one autonomous capture after a physically observed JS110 cold cycle.

Uses the existing power helper's bounded restore-on-exit procedure. No debugger
traffic occurs until that helper finishes its post-power-on settling interval.
The calling bench owner must establish that no flash operation is active.
"""
import argparse
from bisect import bisect_left
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
BOOT = HERE.parent / 'boot-timing'
sys.path.insert(0, str(BOOT))
from capture_cycle import wait_for_cycle
from inspect_cycle import read_csv


def rails(logic):
    t, v = read_csv(logic / 'analog.csv')
    longest = 0
    start = None
    off_window = None
    for i, stamp in enumerate(t):
        if all(v[ch][i] < .1 for ch in (3, 4, 5)):
            if start is None:
                start = stamp
            if stamp - start > longest:
                longest = stamp - start
                off_window = (start, stamp)
        else:
            start = None
    end = bisect_left(t, t[-1] - .5)
    final = {str(ch): dict(min_v=min(v[ch][end:]), max_v=max(v[ch][end:]),
                           median_v=statistics.median(v[ch][end:])) for ch in (3, 4, 5)}
    good = longest >= 1 and all(final[str(ch)]['min_v'] >= low and final[str(ch)]['max_v'] <= high
                                for ch, low, high in [(3, 3, 3.6), (4, 4.5, 5.5), (5, 3, 3.6)])
    result = dict(passed=good, common_off_s=longest, common_off_window_s=off_window, final=final,
                  limitation='No direct core/always-on rail probe; this proves discharge of the three named rails.')
    (logic / 'rail-validation.json').write_text(json.dumps(result, indent=2) + '\n')
    if not good:
        raise RuntimeError('Physical rail qualification failed')
    # Start correlation during verified discharge. Shutdown threshold bounce
    # is not a new boot; all transitions after this physical boundary remain.
    return sum(off_window) / 2


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--control', type=Path, required=True)
    p.add_argument('--response', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    logic, ram = a.out / 'logic', a.out / 'ram'
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    with (a.out / 'logic.log').open('w') as log:
        cap = subprocess.Popen([sys.executable, str(BOOT / 'capture_manual.py'), str(logic),
                                '--seconds', '120', '--ch5-signal', 'main-vddio'],
                               stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
        try:
            deadline = time.monotonic() + 15
            while not (logic / 'started').exists():
                if cap.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('Logic capture did not start')
                time.sleep(.1)
            with (a.out / 'cycle.log').open('w') as power_log:
                cycle = subprocess.Popen([sys.executable, str(BOOT / 'cycle_once.py'),
                    '--control', str(a.control), '--response', str(a.response), '--off-seconds', '20'],
                    stdout=power_log, stderr=subprocess.STDOUT, creationflags=flags)
                interrupted = []
                wait_for_cycle(cycle, 72, lambda exc: interrupted.append(str(exc)))
                if cycle.returncode or interrupted:
                    raise RuntimeError(f'Power cycle failed/interrupted: {cycle.returncode}, {interrupted}')
            with (a.out / 'bench.log').open('w') as bench_log:
                read = subprocess.run([sys.executable, str(HERE / 'bench.py'), 'read',
                    '--build', str(a.build), '--out', str(ram)], stdout=bench_log,
                    stderr=subprocess.STDOUT, creationflags=flags)
        finally:
            if logic.exists():
                (logic / 'stop').touch()
            cap.wait(timeout=45)
    if read.returncode or cap.returncode:
        raise RuntimeError(f'RAM read={read.returncode}, capture={cap.returncode}; inspect logs')
    after_s = rails(logic)
    subprocess.run([sys.executable, str(HERE / 'analyze.py'), str(logic / 'digital.csv'),
                    '--result', str(ram / 'capture-result.json'), '--mode', 'cold',
                    '--after-s', str(after_s), '--out', str(a.out / 'timing.json')],
                   check=True, creationflags=flags)
    timing = json.loads((a.out / 'timing.json').read_text())
    print(json.dumps([{'id': event['id'], 'after_nrst_us': event.get('after_nrst_us')}
                      for event in timing['events'] if event['id'] in (2, 11, 24, 25, 50, 51, 29, 30, 40)], indent=2))


if __name__ == '__main__':
    main()
