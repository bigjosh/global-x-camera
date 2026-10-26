"""Two explicit sensor-pattern captures and one preservation reread after20.

Plan-only unless --execute is supplied. Uses established guarded helpers,
stops on the first failed stage, never overwrites a stage/attempt, and has no
automatic retry, card erase, NOR command, or power-switch operation.
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
PATTERN_SHA = '1f7d3b157e058068f17fc42243ee3c6179b1b737d9909edb8550e4ff24583933'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bound(path):
    return dict(path=str(Path(path).resolve()), sha256=sha(path))


def save_new(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign-summary', type=Path,
                        default=BASE/'invocation-02-20/summary.json')
    parser.add_argument('--build', type=Path, default=BASE/'ram25-pattern')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    build = args.build.resolve()
    manifest = read(build/'manifest.json')
    spec = importlib.util.spec_from_file_location('supplement_bench', ROOT/'firmware/capture-raw/bench.py')
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    bench.checked_build(build, manifest['binary_sha256'])  # Offline identity checks only.
    require(manifest['binary_sha256'] == PATTERN_SHA, 'Pattern executable is not the reviewed frozen build')
    expected = dict(flash=False, standby=False, pattern=1, sd_bus_width=4,
        sd_clock_hz=25000000, sd_clock_negedge=True, sd_clock_negedge_init=True,
        sd_review_profile=True, sd_startup_opt=True, sd_gpio_speed=3,
        sd_early_run_clock=False, sd_high_speed=False, sd_idma_read=False,
        sd_fixed_compensation=False, sd_compensation_modified=False,
        raw_dma_tail_wait=False, dma_sleep=False, preinit=False,
        line_snapshots=False, line_poison=False, exposure_coarse=1428,
        magic_format=True, line_stream=True, async_stop=True, transport='idma')
    require(all(manifest.get(k) == v and type(manifest.get(k)) is type(v)
                for k, v in expected.items()) and bool(manifest.get('cycle_trace')),
            'Supplement pattern profile differs')
    # Digest is supplied by the actual frozen build; no mutable source is compiled here.
    campaign = read(args.campaign_summary)
    require(campaign.get('passed') is True and campaign.get('campaign_complete') is True
            and campaign['completed_runs'] == list(range(1, 21)), 'Primary20 are not complete')
    require(len(campaign['records']) == 20, 'Primary campaign records incomplete')
    for record in campaign['records']:
        require(record['passed'] is True, 'A primary run did not pass')
        for key in ('final_proof', 'capture_proof', 'readback_validation', 'frame', 'slot'):
            item = record[key]
            require(sha(item['path']) == item['sha256'], 'Primary evidence changed: '+key)
    prior = (BASE/'cycle20/readback/payload-3584/verified.json').resolve()
    old_build = (BASE/'ram25-scene').resolve()
    require(Path(campaign['final_proof']['path']).resolve() == prior
            and sha(prior) == campaign['final_proof']['sha256']
            and Path(campaign['final_build']).resolve() == old_build, 'Primary final terminal differs')
    first = read(BASE/'cycle01/capture/verified.json')
    require(first.get('passed') is True and first['proof']['slot'] == 24, 'Expected preservation slot24 differs')
    identity_keys = ('sector_count', 'cid0', 'cid1', 'cid2', 'cid3')
    identity = {key: first['card'][key] for key in identity_keys}
    used_slots = {record['slot_index'] for record in campaign['records']}
    require(len(used_slots) == 20, 'Primary campaign reused a slot')
    targets = [BASE/name for name in ('pattern01', 'pattern02', 'preservation01',
        'supplement-plan.json', 'supplement-events.jsonl', 'supplement-progress.json',
        'supplement-summary.json', 'supplement-failed.json',
        'pattern01-host.log', 'pattern02-host.log', 'preservation01-host.log')]
    require(not any(p.exists() for p in targets), 'Refusing an existing supplementary attempt')
    plan = dict(schema=1, execute=args.execute, primary_summary=bound(args.campaign_summary),
        build=str(build), binary_sha256=manifest['binary_sha256'],
        initial_prior=bound(prior), initial_build=str(old_build),
        planned_captures=['pattern01', 'pattern02'], preservation_slot=24,
        preservation_reference=bound(BASE/'cycle01/capture/frame.bin'),
        nor_write=False, erase=False, power_switch=False, automatic_retry=False)
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return
    save_new(BASE/'supplement-plan.json', plan)
    stage = 'not_started'
    completed = []

    def event(status, **extra):
        record = dict(utc=datetime.now(timezone.utc).isoformat(), stage=stage, status=status, **extra)
        with (BASE/'supplement-events.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(record, allow_nan=False)+'\n')
        pending = BASE/'supplement-progress.pending.json'
        pending.write_text(json.dumps(dict(current=record, completed=completed), indent=2)+'\n', encoding='utf-8')
        pending.replace(BASE/'supplement-progress.json')
        print(json.dumps(record, allow_nan=False), flush=True)

    def execute(name, *command):
        nonlocal stage
        stage = name
        event('started')
        with (BASE/(name+'-host.log')).open('x', encoding='utf-8') as log:
            subprocess.run([sys.executable, *map(str, command)], cwd=ROOT,
                           stdout=log, stderr=subprocess.STDOUT, check=True)

    try:
        for label in ('pattern01', 'pattern02'):
            folder = BASE/label
            execute(label, ROOT/'tmp/bringup/sd-early-clock-20261026/run_one.py',
                    build, old_build, prior, folder)
            v = read(folder/'capture/verified.json')
            validation = read(folder/'readback/readback-validation.json')
            require(v.get('passed') is True and v['proof']['pattern'] == 1
                    and v['binary_sha256'] == manifest['binary_sha256']
                    and validation.get('passed') is True
                    and validation['original_sensor_frame_comparison'] is True,
                    'Pattern full source comparison did not pass')
            require({key: v['card'][key] for key in identity_keys} == identity,
                    'Card identity differs from primary campaign')
            require(v['proof']['slot'] not in used_slots,
                    'Supplement reused an already captured slot')
            used_slots.add(v['proof']['slot'])
            prior = (folder/'readback/payload-3584/verified.json').resolve()
            old_build = build
            completed.append(dict(label=label, slot=v['proof']['slot'],
                capture=bound(folder/'capture/verified.json'),
                verification=bound(folder/'readback/readback-validation.json'),
                final_proof=bound(prior)))
            event('complete', slot=v['proof']['slot'])
        folder = BASE/'preservation01'
        folder.mkdir(exist_ok=False)
        execute('preservation01', ROOT/'tmp/bringup/sd-fourbit-20261024/magic_readback.py',
                'read-slots', '--build', build, '--prior', prior,
                '--scr-proof', BASE/'cycle01/capture/verified.json', '--slot', 24,
                '--reference', BASE/'cycle01/capture/frame.bin', '--reference-kind', 'preservation',
                '--out', folder/'readback', '--execute')
        validation = read(folder/'readback/readback-validation.json')
        require(validation.get('passed') is True and
                validation['source_reference_comparison']['bytes_equal'] is True and
                (folder/'readback/slot.bin').read_bytes() == (BASE/'cycle01/readback/slot.bin').read_bytes(),
                'Preservation full slot comparison failed')
        prior = (folder/'readback/payload-3584/verified.json').resolve()
        completed.append(dict(label='preservation01', slot=24,
            verification=bound(folder/'readback/readback-validation.json'), final_proof=bound(prior)))
        event('complete', slot=24)
        save_new(BASE/'supplement-summary.json', dict(passed=True, completed=completed,
            final_proof=bound(prior), final_build=str(build), automatic_retry=False,
            pattern_repeat_equal=(BASE/'pattern01/capture/frame.bin').read_bytes() ==
                                 (BASE/'pattern02/capture/frame.bin').read_bytes(),
            counts_toward_primary_twenty=False))
    except BaseException:
        error = traceback.format_exc()
        event('failed', error=error)
        save_new(BASE/'supplement-failed.json', dict(passed=False, stage=stage,
            error=error, completed=completed, automatic_retry=False,
            failed_stage_is_not_idle_proof=True))
        raise


if __name__ == '__main__':
    main()
