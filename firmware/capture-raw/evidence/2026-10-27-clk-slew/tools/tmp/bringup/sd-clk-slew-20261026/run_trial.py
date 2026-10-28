"""One root-owned CLK-only trial, plan-only unless --execute is explicit.

No UART stimulus, reset, power switch, NOR command, erase, or automatic retry.
The caller supplies either a successful same-build prior terminal or the
currently installed exact recovery build, already in its early park. Any
failure/timeout leaves artifacts intact and requires separate root diagnosis.
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

ROOT = Path(__file__).resolve().parents[3]
TIMEOUTS = dict(park=90, capture=180, trace=60, readback=900, final_idle=90)
IDENTITY_KEYS = ('sector_count', 'cid0', 'cid1', 'cid2', 'cid3')
FRAME_BYTES = 1909600
SECTORS = 3730


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bound(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=sha(path))


def save_new(path, value):
    with Path(path).open('x', encoding='utf-8') as file:
        json.dump(value, file, indent=2, allow_nan=False)
        file.write('\n')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def admission(args):
    require(not args.out.exists(), 'Refusing an existing trial/output path')
    require(bool(args.prior) != bool(args.recovery_build),
            'Select exactly one same-build --prior or current --recovery-build')
    manifest = read(args.build / 'manifest.json')
    bench = load('clk_trial_bench', ROOT / 'firmware/capture-raw/bench.py')
    bench.checked_build(args.build, manifest['binary_sha256'])  # Offline only.
    expected = dict(flash=False, standby=False, transport='idma',
        sd_bus_width=4, sd_clock_hz=25000000, sd_gpio_speed=3,
        sd_clock_negedge=True, sd_clock_negedge_init=True,
        sd_review_profile=True, sd_startup_opt=True, sd_early_run_clock=False,
        sd_high_speed=False, sd_idma_read=False, sd_fixed_compensation=False,
        sd_compensation_modified=False, sd_high_speed_mixed_slew=False,
        sd_high_speed_fixed_compensation=False, sd_high_speed_combined_electrical=False,
        magic_format=True, line_stream=True, async_stop=True, dma_sleep=False,
        raw_dma_tail_wait=False, whole_image_preerase=False, preinit=False,
        chunk_sectors=SECTORS)
    require(all(manifest.get(key) == value and type(manifest.get(key)) is type(value)
                for key, value in expected.items()), 'Unexpected CLK-only trial profile')
    require(type(manifest.get('sd_clk_gpio_speed')) is int and
            manifest['sd_clk_gpio_speed'] in (1, 2, 3) and
            manifest.get('sd_clk_gpio_proof_bytes') == 48,
            'Explicit admitted CLK-only speed/proof required')
    if args.prior:
        prior = read(args.prior)
        require(prior.get('passed') is True and
                prior.get('binary_sha256') == manifest['binary_sha256'],
                'Prior must be a successful terminal of this exact build')
        bench.validate(prior['proof'], manifest, prior['request_words'])
    else:
        require((args.recovery_build / 'manifest.json').is_file(),
                'Missing explicit current recovery-build manifest')
    return manifest, bench


def check_operation(proof, manifest, bench, identity=None):
    require(proof.get('passed') is True and
            proof.get('binary_sha256') == manifest['binary_sha256'],
            'Operation failed or executable identity changed')
    bench.validate(proof['proof'], manifest, proof['request_words'])
    p, card = proof['proof'], proof['card']
    for item in (p, card):
        require(item['media_idle'] == 1 and
                all(item[key] == 0 for key in ('initialized', 'controller_owned', 'cleanup_error')),
                'Operation lacks clean ownership/idle proof')
    require(card['error'] == 0 and p['result'] == 0 and card['clock_hz'] == 25000000,
            'Operation/card clock or error differs')
    width = card['bus_width_proof']
    require(width['negotiated_width'] == 4 and width['configured_clkcr'] == 0x34003,
            'Four-bit divider/launch phase differs')
    current = {key: card[key] for key in IDENTITY_KEYS}
    require(identity is None or current == identity, 'Card changed during trial')
    gpio = card['clk_gpio_speed_proof']
    speed = manifest['sd_clk_gpio_speed']
    require((gpio['magic'],gpio['version'],gpio['requested_speed'],gpio['clk_mask'],
             gpio['c_mask'],gpio['e_mask'],gpio['applied']) ==
            (0x314B4C43,1,speed,0x30,0xFF3,0x300,1) and
            gpio['c_configured']&0xFF3 == 0xFF3 and
            gpio['c_after']&0xFF3 == (0xFF3&~0x30)|(speed<<4) and
            gpio['e_after']&0x300 == 0x300 and
            (gpio['c_before']^gpio['c_configured'])&~0xFF3 == 0 and
            (gpio['c_configured']^gpio['c_after'])&~0x30 == 0 and
            (gpio['e_before']^gpio['e_after'])&~0x300 == 0,
            'CLK-only GPIO proof differs or unrelated pin fields changed')
    return current


def verify_artifacts(folder, manifest, bench):
    capture_path = folder / 'capture/verified.json'
    capture = read(capture_path)
    identity = check_operation(capture, manifest, bench)
    require(capture['proof']['operation'] == 1, 'Not a capture operation')
    slot = capture['proof']['slot']
    frame = folder / 'capture/frame.bin'
    require(frame.stat().st_size == FRAME_BYTES and sha(frame) == capture['frame_sha256'],
            'Original frame is missing, incomplete or changed')
    parts, read_proofs = [], []
    for offset in range(0, SECTORS, 512):
        part = folder / f'readback/payload-{offset:04d}'
        proof_path = part / 'verified.json'
        proof = read(proof_path)
        check_operation(proof, manifest, bench, identity)
        count = min(512, SECTORS-offset)
        require(proof['proof']['operation'] == 3 and
                proof['proof']['read_lba'] == slot*SECTORS+offset and
                proof['proof']['read_count'] == count, 'Readback coverage differs')
        data = (part / 'sectors.bin').read_bytes()
        require(len(data) == count*512 and sha(part/'sectors.bin') == proof['read_sha256'],
                'Readback chunk changed or is incomplete')
        parts.append(data)
        read_proofs.append(bound(proof_path))
    slot_path = folder / 'readback/slot.bin'
    actual = slot_path.read_bytes()
    require(actual == b''.join(parts), 'Assembled slot differs from complete read chunks')
    expected = b'GXR2' + bytes(152) + frame.read_bytes() + b'GXRE'
    require(actual == expected, 'Entire stored object differs from original frame/header/metadata/trailer')
    reader = load('clk_trial_readback', ROOT/'tmp/bringup/sd-fourbit-20261024/magic_readback.py')
    validation = reader.validate(folder/'readback', slot,
        read(folder/'readback/scr-source.json'), frame, 'sensor-ram')
    require(validation.get('passed') is True and validation['original_sensor_frame_comparison'] is True and
            validation['source_reference_comparison']['bytes_equal'] is True and
            validation['png_samples_match_read_raw'] is True, 'Source/PNG verification failed')
    final = folder / 'readback/payload-3584/verified.json'
    require(Path(read(folder/'readback/summary.json')['prior']).resolve() == final.resolve(),
            'Final READ terminal differs')
    return dict(schema=1, passed=True, slot=slot, card_identity=identity,
        clk_gpio_speed=manifest['sd_clk_gpio_speed'], clock_hz=25000000, bus_width=4,
        entire_object_equal=True, object_bytes=len(expected), original_frame_bytes=FRAME_BYTES,
        metadata_zero=True, image_and_png_equal=True,
        binary_sha256=manifest['binary_sha256'],
        capture=bound(capture_path), frame=bound(frame), slot_file=bound(slot_path),
        png=bound(folder/'readback/scene.png'), read_proofs=read_proofs,
        readback_validation=bound(folder/'readback/readback-validation.json'), final_proof=bound(final),
        automatic_retry=False, nor_write=False, erase=False, power_switch=False)


def run(args):
    args.build, args.out = args.build.resolve(), args.out.resolve()
    if args.prior:
        args.prior = args.prior.resolve()
    if args.recovery_build:
        args.recovery_build = args.recovery_build.resolve()
    manifest, bench = admission(args)
    plan = dict(schema=1, execute=args.execute, build=str(args.build),
        binary_sha256=manifest['binary_sha256'], clk_gpio_speed=manifest['sd_clk_gpio_speed'],
        prior=bound(args.prior) if args.prior else None,
        recovery_build=str(args.recovery_build) if args.recovery_build else None,
        subprocess_timeouts_seconds=TIMEOUTS, automatic_retry=False,
        uart_stimulus=False, reset=False, power_switch=False, nor_write=False, erase=False)
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return plan
    args.out.mkdir(parents=True, exist_ok=False)
    save_new(args.out/'plan.json', plan)
    stage = 'not_started'

    def event(status, **extra):
        record = dict(utc=datetime.now(timezone.utc).isoformat(), stage=stage, status=status, **extra)
        with (args.out/'events.jsonl').open('a', encoding='utf-8') as file:
            file.write(json.dumps(record, allow_nan=False)+'\n')
        print(json.dumps(record, allow_nan=False), flush=True)

    def execute(label, *command):
        nonlocal stage
        stage = label
        event('started')
        with (args.out/(label+'.log')).open('x', encoding='utf-8') as log:
            subprocess.run([sys.executable, *map(str, command)], cwd=ROOT,
                stdout=log, stderr=subprocess.STDOUT, timeout=TIMEOUTS[label], check=True)
        event('complete')

    try:
        if args.recovery_build:
            execute('park', ROOT/'firmware/capture-timing/recovery_gpio/check_park.py',
                '--build', args.recovery_build, '--out', args.out/'park')
        capture_args = ['capture', '--build', args.build, '--expected-sha', manifest['binary_sha256'],
            '--out', args.out/'capture', '--execute', '--download-frame']
        capture_args += ['--prior', args.prior] if args.prior else ['--recovery-build', args.recovery_build]
        execute('capture', ROOT/'firmware/capture-raw/bench.py', *capture_args)
        capture_path = args.out/'capture/verified.json'
        capture = read(capture_path)
        check_operation(capture, manifest, bench)
        if manifest.get('cycle_trace'):
            execute('trace', ROOT/'tmp/bringup/sd50-reviewed-20261026/read_trace.py',
                args.build, capture_path, args.out/'trace')
        execute('readback', ROOT/'tmp/bringup/sd-fourbit-20261024/magic_readback.py',
            'read-slots', '--build', args.build, '--prior', capture_path, '--scr-proof', capture_path,
            '--slot', capture['proof']['slot'], '--reference', args.out/'capture/frame.bin',
            '--reference-kind', 'sensor-ram', '--out', args.out/'readback', '--execute')
        stage = 'verify_artifacts'
        event('started')
        summary = verify_artifacts(args.out, manifest, bench)
        summary['build'] = str(args.build)
        event('complete')
        execute('final_idle', ROOT/'tmp/bringup/sd-early-clock-20261026/fresh_idle.py',
            args.build, args.out/'readback/payload-3584/verified.json', args.out/'final-idle')
        summary['fresh_final_idle'] = bound(args.out/'final-idle/verified.json')
        save_new(args.out/'summary.json', summary)
        return summary
    except BaseException:
        error = traceback.format_exc()
        event('failed', error=error)
        frame = args.out/'capture/frame.bin'
        save_new(args.out/'failed.json', dict(passed=False, stage=stage, error=error,
            automatic_retry=False, failed_stage_is_not_idle_proof=True,
            target_state='Unverified after failure; root diagnosis required before further operation',
            original_frame=bound(frame) if frame.is_file() else None,
            missing_frame_reason=None if frame.is_file() else
                'Capture helper did not finish frame download; no unguarded memory read attempted',
            artifacts_preserved=True, timeout_may_leave_child_programmer=True))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--prior', type=Path)
    source.add_argument('--recovery-build', type=Path)
    parser.add_argument('--execute', action='store_true')
    result = run(parser.parse_args())
    if result.get('passed'):
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
