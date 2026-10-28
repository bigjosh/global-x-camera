"""Record external GPIOs around one RAM capture experiment; no power/NOR writes."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    logic = a.out / 'logic'
    ram = a.out / 'ram'
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    with (a.out / 'logic.log').open('w') as log:
        capture = subprocess.Popen([sys.executable, str(HERE.parent / 'boot-timing/capture_manual.py'),
                                    str(logic), '--seconds', '90', '--ch5-signal', 'main-vddio'],
                                   stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
        try:
            deadline = time.monotonic() + 15
            while not (logic / 'started').exists():
                if capture.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('Logic capture did not start')
                time.sleep(.1)
            with (a.out / 'bench.log').open('w') as bench_log:
                result = subprocess.run([sys.executable, str(HERE / 'bench.py'), 'run',
                                         '--build', str(a.build), '--out', str(ram)],
                                        stdout=bench_log, stderr=subprocess.STDOUT,
                                        creationflags=flags)
        finally:
            if logic.exists():
                (logic / 'stop').touch()
            capture.wait(timeout=45)
    if result.returncode or capture.returncode:
        raise RuntimeError(f'RAM return={result.returncode}, capture return={capture.returncode}; inspect logs')
    subprocess.run([sys.executable, str(HERE / 'analyze.py'), str(logic / 'digital.csv'),
                    '--result', str(ram / 'capture-result.json'), '--mode', 'ram', '--after-s', '0',
                    '--out', str(a.out / 'timing.json')], check=True, creationflags=flags)
    report = json.loads((ram / 'capture-result.json').read_text())
    print(json.dumps({k: report[k] for k in ['stage', 'frames', 'vsyncs', 'errors', 'camera_error',
                                            'image_integrity_matches', 'host_image']}, indent=2))


if __name__ == '__main__':
    main()
