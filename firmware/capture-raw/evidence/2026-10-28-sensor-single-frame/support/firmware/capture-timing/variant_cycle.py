"""Run one checked staged-image update and physically observed cold capture.

Root bench owner only. Requires a completed capture, an exact current sector,
and a live restore-on-exit power session. Each subprocess must finish cleanly
before the next operation is started; failures stop rather than power cycling.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BOOT = HERE.parent / 'boot-timing'
REPO = HERE.parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--current', type=Path, required=True)
    p.add_argument('--current-layout', choices=('raw8', 'raw10'), default='raw8')
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--sequence', type=int, required=True)
    p.add_argument('--control', type=Path, required=True)
    p.add_argument('--response', type=Path, required=True)
    a = p.parse_args()
    manifest = json.loads((a.candidate / 'manifest.json').read_text())
    desired = a.candidate / 'capture_sector_0.bin'
    if hashlib.sha256(desired.read_bytes()).hexdigest() != manifest['program_sha256']:
        raise ValueError('Candidate image does not match manifest')
    stage2 = (Path(manifest['stage2_build_manifest']).parent
              if 'stage2_build_manifest' in manifest else a.candidate)
    a.out.mkdir(parents=True, exist_ok=False)
    def run(name, script, *args):
        with (a.out / (name + '.log')).open('w', encoding='utf-8') as log:
            subprocess.run([sys.executable, str(script), *map(str, args)],
                           stdout=log, stderr=subprocess.STDOUT, check=True,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        print(name + ' complete', flush=True)
    run('maintenance', HERE / 'prepare_maintenance.py', '--out', a.out / 'maintenance',
        '--layout', a.current_layout)
    build = REPO / 'tmp/bringup/rom-nor-programmer-20261017'
    run('info', BOOT / 'nor_bench.py', 'info', '--build', build,
        '--out', a.out / 'info', '--sequence', a.sequence)
    run('write', BOOT / 'nor_bench.py', 'write', '--build', build,
        '--out', a.out / 'write', '--sequence', a.sequence + 1,
        '--current', a.current, '--desired', desired)
    (a.out / 'programmed-image.json').write_text(json.dumps({
        'path': str(desired.resolve()), 'sha256': manifest['program_sha256']}, indent=2))
    run('cold', HERE / 'cold_experiment.py', '--build', stage2,
        '--out', a.out / 'cold', '--control', a.control, '--response', a.response)
    print((a.out / 'cold.log').read_text(), flush=True)


if __name__ == '__main__':
    main()
