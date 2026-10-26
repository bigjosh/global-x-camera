"""Root-owned 20-image RAM campaign; plan-only unless --execute is explicit.

Runs 1-8 and 13-20 use ram25-scene; runs 9-12 use ram25-long. Every
capture is followed by trace retrieval and a full same-build 25 MHz readback
compared to the original downloaded camera RAM. Existing attempts are never
overwritten. A failed stage stops the batch; there is no automatic retry.

Resume only at a new run after a completed run, with its exact final READ
proof and build explicitly supplied. Changing builds uses a fresh old-build
terminal gate, one UART request, and a fresh exact installed-prefix park.
No NOR write, erase, power switch, or automatic recovery after failure.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import traceback

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
INSTALLED = ROOT / 'tmp/bringup/sd50-reviewed-20261026/flash-reviewed125-startup-standby/staged'
PREFIX_SHA = '4ef99d3b0b8ac7b790265cd1994428a5804dd3a20ad5587dd1585d2544a74b0b'
IDENTITY_KEYS = ('sector_count', 'cid0', 'cid1', 'cid2', 'cid3')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bound(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': sha(path)}


def save_new(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write('\n')


def replace_progress(path, value):
    temp = path.with_suffix('.pending.json')
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temp.replace(path)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def selected_build(number):
    return BASE / ('ram25-long' if 9 <= number <= 12 else 'ram25-scene')


def checked_profiles():
    bench = load('campaign_raw_bench', ROOT / 'firmware/capture-raw/bench.py')
    profiles = {}
    for name, exposure, diagnostics in [('ram25-scene', 1428, False), ('ram25-long', 30000, True)]:
        path = BASE / name
        manifest = read(path / 'manifest.json')
        bench.checked_build(path, manifest['binary_sha256'])  # Offline hashes/layout only.
        expected = dict(pattern=0, flash=False, standby=False, transport='idma',
            sd_bus_width=4, sd_clock_hz=25000000, sd_gpio_speed=3,
            sd_clock_negedge=True, sd_clock_negedge_init=True,
            sd_review_profile=True, sd_startup_opt=True, sd_early_run_clock=False,
            sd_high_speed=False, sd_idma_read=False, sd_fixed_compensation=False,
            sd_compensation_modified=False, sd_high_speed_mixed_slew=False,
            sd_high_speed_fixed_compensation=False, sd_high_speed_combined_electrical=False,
            magic_format=True, line_stream=True, async_stop=True, dma_sleep=False,
            raw_dma_tail_wait=False, whole_image_preerase=False, preinit=False,
            line_snapshots=diagnostics, line_poison=diagnostics,
            exposure_coarse=exposure, chunk_sectors=3730)
        require(all(manifest.get(k) == v and type(manifest.get(k)) is type(v)
                    for k, v in expected.items()), 'Unexpected campaign profile: ' + name)
        require(bool(manifest.get('cycle_trace')), 'Missing cycle trace: ' + name)
        profiles[str(path.resolve())] = manifest
    return bench, profiles


def adopt_manual_first_cycle(folder, bench, profiles):
    """Offline-only adoption of root's already completed cycle01, never retry it."""
    build = selected_build(1).resolve()
    m = profiles[str(build)]
    capture = folder / 'capture/verified.json'
    v = read(capture)
    require(v.get('passed') is True and v['binary_sha256'] == m['binary_sha256'],
            'Manual first capture has wrong identity or did not pass')
    bench.validate(v['proof'], m, v['request_words'])
    identity = {k: v['card'][k] for k in IDENTITY_KEYS}
    chunks = []
    for offset in range(0, 3730, 512):
        dest = folder / f'readback/payload-{offset:04d}'
        p = read(dest / 'verified.json')
        require(p.get('passed') is True and p['binary_sha256'] == m['binary_sha256'],
                'Manual readback identity/result differs')
        bench.validate(p['proof'], m, p['request_words'])
        require(p['proof']['operation'] == 3 and
                p['proof']['read_lba'] == v['proof']['slot'] * 3730 + offset and
                p['proof']['read_count'] == min(512, 3730-offset) and
                {k: p['card'][k] for k in IDENTITY_KEYS} == identity and
                p['card']['clock_hz'] == 25000000 and
                p['card']['bus_width_proof']['configured_clkcr'] == 0x34003,
                'Manual readback scope/card/clock differs')
        data = (dest / 'sectors.bin').read_bytes()
        require(hashlib.sha256(data).hexdigest() == p['read_sha256'], 'Manual read bytes changed')
        chunks.append(data)
    require(b''.join(chunks) == (folder / 'readback/slot.bin').read_bytes(), 'Manual slot assembly differs')
    require((folder / 'readback/scene.png').is_file(), 'Manual PNG missing')
    reader = load('campaign_manual_reader', ROOT / 'tmp/bringup/sd-fourbit-20261024/magic_readback.py')
    validation = reader.validate(folder / 'readback', v['proof']['slot'],
        read(folder / 'readback/scr-source.json'), folder / 'capture/frame.bin', 'sensor-ram')
    require(validation['passed'] and validation['original_sensor_frame_comparison'],
            'Manual full source/image comparison failed')
    trace = read(folder / 'trace/cycle-trace.json')
    require(trace['status'] == 'complete' and trace['result'] == 0, 'Manual trace incomplete')
    return dict(schema=1, passed=True, run=1, build=str(build),
        binary_sha256=m['binary_sha256'], card_identity=identity,
        slot_index=v['proof']['slot'], exposure_coarse=m['exposure_coarse'],
        capture_proof=bound(capture), readback_validation=bound(folder / 'readback/readback-validation.json'),
        final_proof=bound(folder / 'readback/payload-3584/verified.json'),
        frame=bound(folder / 'capture/frame.bin'), slot=bound(folder / 'readback/slot.bin'),
        trace=bound(folder / 'trace/cycle-trace.json'), adopted_manual_cycle=True)


def completed_history(out, first, prior, prior_build, bench, profiles):
    records = []
    for number in range(1, first):
        folder = out / f'cycle{number:02d}'
        if number == 1 and not (folder / 'summary.json').exists():
            record = adopt_manual_first_cycle(folder, bench, profiles)
        else:
            record = read(folder / 'summary.json')
        require(record.get('passed') is True and record['run'] == number,
                'Cannot resume after incomplete/failed run ' + str(number))
        require(Path(record['build']).resolve() == selected_build(number).resolve(),
                'Prior run used the wrong scheduled build')
        for key in ('final_proof', 'capture_proof', 'readback_validation', 'frame', 'slot'):
            item = record[key]
            require(sha(item['path']) == item['sha256'], 'Prior run artifact changed: ' + key)
        records.append(record)
    if records:
        last = records[-1]
        require(prior is not None and prior_build is not None, 'Resume needs --prior and --prior-build')
        require(prior.resolve() == Path(last['final_proof']['path']).resolve() and
                prior_build.resolve() == Path(last['build']).resolve(),
                'Resume must name the preceding completed run\'s exact final READ and build')
    return records


def admission(a):
    require(1 <= a.first <= a.last <= 20, 'Run range must be within 1..20')
    require(bool(a.prior) == bool(a.prior_build), '--prior and --prior-build are a pair')
    require(bool(a.prior) != bool(a.park_proof), 'Supply one initial source: prior/build or --park-proof')
    require(a.first == 1 or a.park_proof is None, 'Only run 1 may start from a supplied recovery park')
    bench, profiles = checked_profiles()
    records = completed_history(a.out, a.first, a.prior, a.prior_build, bench, profiles)
    for number in range(a.first, a.last + 1):
        require(not (a.out / f'cycle{number:02d}').exists(), 'Refusing existing attempt/run ' + str(number))
    if a.prior:
        p = read(a.prior)
        m, _ = bench.checked_build(a.prior_build, p['binary_sha256'])
        bench.validate(p['proof'], m, p['request_words'])
        require(p.get('passed') is True, 'Prior proof did not pass')
        if records:
            require(p['proof']['operation'] == 3, 'Resume requires the completed final READ')
    else:
        park = read(a.park_proof)
        require(park.get('passed') is True and park.get('prefix_sha256') == PREFIX_SHA,
                'Initial park proof is not the exact installed reviewed prefix')
    return profiles, records


def run(a):
    a.out = a.out.resolve()
    profiles, records = admission(a)
    plan = dict(schema=1, execute=a.execute, first=a.first, last=a.last,
        initial_prior=str(a.prior.resolve()) if a.prior else None,
        initial_prior_build=str(a.prior_build.resolve()) if a.prior_build else None,
        initial_park=bound(a.park_proof) if a.park_proof else None,
        runs=[dict(run=n, build=str(selected_build(n).resolve()),
                   binary_sha256=profiles[str(selected_build(n).resolve())]['binary_sha256'])
              for n in range(a.first, a.last + 1)],
        nor_write=False, erase=False, power_switch=False, automatic_retry=False,
        build_transition='Fresh exact terminal, one UART request, exact installed park')
    if not a.execute:
        print(json.dumps(plan, indent=2))
        return plan
    a.out.mkdir(parents=True, exist_ok=True)
    invocation = a.out / f'invocation-{a.first:02d}-{a.last:02d}'
    invocation.mkdir(exist_ok=False)
    save_new(invocation / 'plan.json', plan)
    save_new(invocation / 'prior-completed-runs.json', records)
    prior = a.prior.resolve() if a.prior else None
    old_build = a.prior_build.resolve() if a.prior_build else None
    identity = records[0]['card_identity'] if records else None
    stage = 'not_started'
    active = None

    def event(status, **extra):
        record = dict(utc=datetime.now(timezone.utc).isoformat(), run=active,
                      stage=stage, status=status, **extra)
        with (invocation / 'events.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(record, allow_nan=False) + '\n')
        replace_progress(invocation / 'progress.json', dict(current=record,
            completed_runs=[r['run'] for r in records],
            last_completed_proof=records[-1]['final_proof'] if records else None))
        print(json.dumps(record, allow_nan=False), flush=True)

    def execute(label, *args):
        nonlocal stage
        stage = label
        event('started')
        with (folder / (label + '.log')).open('x', encoding='utf-8') as log:
            subprocess.run([sys.executable, *map(str, args)], cwd=ROOT,
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        event('complete')

    try:
        for number in range(a.first, a.last + 1):
            active = number
            folder = a.out / f'cycle{number:02d}'
            folder.mkdir(exist_ok=False)
            build = selected_build(number).resolve()
            manifest = profiles[str(build)]
            save_new(folder / 'plan.json', dict(run=number, build=str(build),
                binary_sha256=manifest['binary_sha256'], prior=str(prior) if prior else None,
                prior_build=str(old_build) if old_build else None))
            if prior is None:
                execute('park', ROOT / 'firmware/capture-timing/recovery_gpio/check_park.py',
                        '--build', INSTALLED, '--out', folder / 'park')
            elif old_build != build:
                execute('idle', ROOT / 'tmp/bringup/sd-early-clock-20261026/fresh_idle.py',
                        old_build, prior, folder / 'idle')
                execute('recovery', ROOT / 'tmp/bringup/sd125-negedge-20261026/uart_recover.py',
                        folder / 'recovery')
                execute('park', ROOT / 'firmware/capture-timing/recovery_gpio/check_park.py',
                        '--build', INSTALLED, '--out', folder / 'park')
                prior = None
            capture_args = ['capture', '--build', build, '--expected-sha', manifest['binary_sha256'],
                '--out', folder / 'capture', '--execute', '--download-frame']
            capture_args += ['--prior', prior] if prior else ['--recovery-build', INSTALLED]
            execute('capture', ROOT / 'firmware/capture-raw/bench.py', *capture_args)
            capture_proof = folder / 'capture/verified.json'
            v = read(capture_proof)
            current_identity = {k: v['card'][k] for k in IDENTITY_KEYS}
            if identity is None:
                identity = current_identity
            require(identity == current_identity, 'Card changed during campaign')
            require(v['proof']['slot'] not in [r['slot_index'] for r in records], 'Slot reused within campaign')
            execute('trace', ROOT / 'tmp/bringup/sd50-reviewed-20261026/read_trace.py',
                    build, capture_proof, folder / 'trace')
            if manifest['line_snapshots']:
                stage = 'long_snapshot_comparison'
                event('started')
                decoder = load('campaign_producer_decoder', ROOT / 'firmware/capture-raw/verify_producer.py')
                comparator = load('campaign_snapshot_comparator',
                    ROOT / 'tmp/bringup/sd25-crc-20261025/long_scene_snapshot_report.py')
                count, hashes = comparator.compare_snapshots(
                    decoder.decode((folder / 'capture/producer.bin').read_bytes()),
                    (folder / 'capture/snapshots.bin').read_bytes(),
                    (folder / 'capture/frame.bin').read_bytes())
                require(count == 20, 'Long capture did not retain all twenty published tails')
                save_new(folder / 'long-snapshots.json', dict(passed=True, count=count,
                    bytes_compared=count*512, snapshots=hashes,
                    binary_sha256=manifest['binary_sha256'], original_frame=bound(folder / 'capture/frame.bin'),
                    comparator=bound(ROOT / 'tmp/bringup/sd25-crc-20261025/long_scene_snapshot_report.py'),
                    old_profile_gate_used=False))
                event('complete', snapshot_count=count)
            execute('readback', ROOT / 'tmp/bringup/sd-fourbit-20261024/magic_readback.py',
                    'read-slots', '--build', build, '--prior', capture_proof,
                    '--scr-proof', capture_proof, '--slot', v['proof']['slot'],
                    '--reference', folder / 'capture/frame.bin', '--reference-kind', 'sensor-ram',
                    '--out', folder / 'readback', '--execute')
            stage = 'verify_saved_artifacts'
            event('started')
            validation_path = folder / 'readback/readback-validation.json'
            validation = read(validation_path)
            require(validation.get('passed') is True and validation['original_sensor_frame_comparison'] is True
                    and validation['source_reference_comparison']['bytes_equal'] is True
                    and validation['png_samples_match_read_raw'] is True,
                    'Full camera-RAM/SD/PNG verification failed')
            final = Path(read(folder / 'readback/summary.json')['prior']).resolve()
            require(final == (folder / 'readback/payload-3584/verified.json').resolve(),
                    'Final readback proof path differs')
            record = dict(schema=1, passed=True, run=number, build=str(build),
                binary_sha256=manifest['binary_sha256'], card_identity=identity,
                slot_index=v['proof']['slot'], exposure_coarse=manifest['exposure_coarse'],
                capture_proof=bound(capture_proof), readback_validation=bound(validation_path),
                final_proof=bound(final), frame=bound(folder / 'capture/frame.bin'),
                slot=bound(folder / 'readback/slot.bin'), trace=bound(folder / 'trace/cycle-trace.json'))
            save_new(folder / 'summary.json', record)
            records.append(record)
            prior, old_build = final, build
            event('complete', slot=v['proof']['slot'])
        result = dict(schema=1, passed=True, requested_range_complete=True,
            campaign_complete=len(records) == 20, completed_runs=[r['run'] for r in records],
            final_proof=bound(prior), final_build=str(old_build), card_identity=identity,
            records=records, automatic_retry=False, nor_write=False, erase=False, power_switch=False)
        save_new(invocation / 'summary.json', result)
        return result
    except BaseException:
        error = traceback.format_exc()
        event('failed', error=error)
        save_new(invocation / 'failed.json', dict(passed=False, run=active, stage=stage,
            error=error, completed_runs=[r['run'] for r in records],
            last_completed_proof=records[-1]['final_proof'] if records else None,
            automatic_retry=False, failed_stage_is_not_idle_proof=True))
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, default=BASE)
    p.add_argument('--first', type=int, default=1)
    p.add_argument('--last', type=int, default=20)
    p.add_argument('--prior', type=Path)
    p.add_argument('--prior-build', type=Path)
    p.add_argument('--park-proof', '--initial-park', type=Path)
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    result = run(a)
    if a.execute:
        print(json.dumps({k: v for k, v in result.items() if k != 'records'}, indent=2))


if __name__ == '__main__':
    main()
