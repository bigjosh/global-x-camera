"""Build a matched, offline staged sensor timing sweep from a frozen harness."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

from build import HERE, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture-source', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    frozen = out / 'frozen_capture.c'
    frozen.write_bytes(args.capture_source.read_bytes())
    common = ['--capture-source', str(frozen), '--minimal-system-init', '--rom-clocks',
              '--strobe', '1', '--i2c-hz', '1000000', '--i2c-timing', '0x10831A27',
              '--newest-only', '--poll-us', '50', '--reset-us', '100', '--fix-dphy-irq',
              '--direct-clocks', '--lto', '--stage2', '--phy-testclk-us', '1',
              '--batch-config', '--receiver-before-ready', '--clock-diagnostics']
    variants = [('base', 1428, 4336, False), ('coarse650', 650, 4336, False),
                ('coarse1301', 1301, 4336, False), ('frame2168', 1428, 2168, False),
                ('frame8666', 1428, 8666, False), ('pll1', 1428, 4336, True)]

    def build_variant(variant):
        name, coarse, frame, pll1 = variant
        stage2, combined = out / (name + '-stage2'), out / (name + '-staged')
        command = [sys.executable, str(HERE / 'build.py'), '--output', str(stage2),
                   *common, '--coarse-lines', str(coarse), '--frame-lines', str(frame)]
        if pll1:
            command += ['--pll-prediv1']
        with (out / (name + '-build.log')).open('wb') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
            subprocess.run([sys.executable, str(HERE / 'build_staged.py'), '--stage2', str(stage2),
                            '--snapshot', str(args.snapshot.resolve()), '--output', str(combined)],
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        manifest = json.loads((combined / 'manifest.json').read_text())
        return {'variant': name, 'coarse_lines': coarse, 'frame_lines': frame,
                'pll_prediv1': pll1, 'image': str(combined / 'capture_sector_0.bin'),
                'program_sha256': manifest['program_sha256'],
                'stage2_bytes': manifest['stage2_bytes'],
                'harness_sha256': sha((stage2 / 'capture.c').read_bytes()),
                'manifest': str(combined / 'manifest.json')}

    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(build_variant, variants))
    assert len({r['harness_sha256'] for r in results}) == 1, 'Sweep harness drifted between variants'
    manifest = {'hardware_status': 'untested', 'frozen_input_sha256': sha(frozen.read_bytes()),
                'common_flags': common, 'variants': results}
    (out / 'sweep_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
