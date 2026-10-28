"""Offline validation of the 128-byte LED phase proof and its frozen sources.

Snapshots establish GPIO register levels at named events, not a continuous
electrical waveform. Sleep-prepared is not proof that the CPU actually slept;
the bench must separately inspect live DHCSR.S_SLEEP and/or the reviewed PC.
"""
import argparse
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build import PROOF_FIELDS, GUARD_SHA, GUARD_HEADER_SHA, led_manifest
sys.path.insert(0, str(HERE.parent))
from build_raw10 import ROOT, sha

MASK = 0x501
MODE_MASK = 0x330003
MODE_OUTPUT = 0x110001


def require(value, message):
    if not value:
        raise ValueError(message)


def source_checks(manifest):
    """Check provenance and the early-memory ordering in frozen source files."""
    files = {}
    for path, digest in manifest['sources'].items():
        source = ROOT/path
        content = source.read_bytes()
        require(sha(content) == digest, f'Frozen source changed: {source}')
        files[source.name] = content
    require('stage1.c' in files, 'Use the staged manifest for prefix source-order verification')
    require(sha(files['recovery_gpio.c']) == GUARD_SHA and sha(files['recovery_gpio.h']) == GUARD_HEADER_SHA,
            'Recovery guard source differs from qualified v41')
    stage = files['stage1.c'].decode('utf-8')
    main = stage.split('void stage1_main(void)\n{', 1)[1]
    require(main.lstrip().startswith('status_led_boot_begin();\n    recovery_gpio_begin();'),
            'Earliest phase must precede unchanged recovery guard')
    before, after = main.split('raw10_memory_init();', 1)
    require('status_led_proof_' not in before and 'STATUS_LED_PROOF' not in before,
            'LED proof touches expanded SRAM before memory initialization')
    require(after.startswith('\n    recovery_gpio_publish();\n    status_led_proof_init();'),
            'LED proof initialization must follow qualified memory initialization')
    header = files['status_leds.h'].decode('utf-8')
    early = header.split('static inline void status_led_boot_begin(void)', 1)[1].split('\n}', 1)[0]
    require('STATUS_LED_PROOF' not in early and 'status_led_proof_' not in early,
            'Early GPIO setup may not use expanded diagnostic memory')
    return dict(frozen_source_hashes_match=True, recovery_sources_identical_to_v41=True,
                no_led_proof_access_before_memory_init=True)


def decode(data, manifest, capture=None):
    require(len(data) == 128, 'Expected exactly 128 bytes / 32 little-endian words')
    require(manifest.get('status_leds') == led_manifest(), 'Unsupported LED proof schema/policy')
    values = struct.unpack('<32I', data)
    words = dict(zip(PROOF_FIELDS, values))
    require((words['magic'], words['schema'], words['words']) == (0x4C454431, 1, 32),
            'Invalid LED proof header')
    require(words['phase'] == 0 and words['sleep_state'] == 1,
            'Capture has not reached all-off/sleep-prepared state')
    expected = {'red': 0x101, 'blue': 0x401, 'off': 0x501, 'sleep': 0x501}
    for phase, level in expected.items():
        for register in ('odr', 'idr'):
            require(words[f'{phase}_{register}'] & MASK == level,
                    f'{phase} {register.upper()} does not match active-low LED phase')
        require(words[f'{phase}_cycle'] != 0, f'Missing {phase} timestamp')
    cycles = [words[f'{phase}_cycle'] for phase in expected]
    require(all(0 < ((b-a) & 0xFFFFFFFF) < 0x80000000 for a, b in zip(cycles, cycles[1:])),
            'LED phase timestamps are not ordered red/blue/off/sleep')
    require(words['moder'] & MODE_MASK == MODE_OUTPUT, 'LED pins are not outputs')
    require(not(words['otyper'] & MASK), 'LED pins are not push-pull')
    require(not(words['ospeedr'] & MODE_MASK) and not(words['pupdr'] & MODE_MASK),
            'LED pins must use low slew and no pulls')
    require(words['ahb4enr'] & (1 << 6), 'GPIOG clock is not enabled')
    require(not(words['scr'] & 0x6), 'Deep sleep or sleep-on-exit unexpectedly selected')
    require(words['primask'] == 1 and words['systick_ctrl'] == 0,
            'Interrupts/SysTick were not disabled before sleep')
    require(words['nvic_enable_or'] == 0 and words['nvic_pending_or'] == 0,
            'NVIC enable or pending bits remain')
    require(not(words['icsr'] & ((1 << 28) | (1 << 26) | 0x1FF)),
            'Pending SysTick/PendSV or active exception at sleep preparation')
    require(words['error_cycle'] == words['error_odr'] == words['error_idr'] == 0,
            'Fatal-error indication recorded')
    capture_checked = False
    if capture is not None:
        receiver_sha = manifest.get('stage2_sha256', manifest.get('raw_sha256'))
        require(capture.get('build_sha256') == receiver_sha, 'Capture belongs to another receiver')
        require(capture.get('completed') and capture.get('image_integrity_matches'),
                'Completed intact image is required')
        require(capture.get('camera_error') == 0 and capture.get('errors') == 0,
                'Capture contains camera errors')
        events = capture.get('events', [])
        def first(event_id):
            found = [(i, event['cycles']) for i, event in enumerate(events) if event['id'] == event_id]
            require(found, f'Missing capture event {event_id}')
            return found[0]
        arm, blue, fall, frame, after_frame, done = (first(i) for i in (22, 50, 51, 30, 31, 40))
        require(arm[0] < blue[0] < fall[0] < frame[0] < after_frame[0] < done[0],
                'First exposure/frame event ordering is invalid')
        require(sum(event['id'] == 50 for event in events[:frame[0]]) == 1,
                'Frame is not associated with the first recorded STROBE')
        require(blue[1] <= words['blue_cycle'] < fall[1],
                'Blue transition does not follow the first exposure marker')
        require(frame[1] <= words['off_cycle'] <= after_frame[1],
                'Off transition does not match the first frame marker')
        require(done[1] <= words['sleep_cycle'], 'Sleep preparation precedes successful completion')
        capture_checked = True
    return dict(schema=1, address='0x343f89c0', valid=True, words=words,
        green_off_in_every_snapshot=True, first_exposure_capture_checked=capture_checked,
        sleep_prepared=True, cpu_sleep_observed=False,
        note='GPIO snapshots are not continuous pin measurements; verify live CPU sleep separately')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True, help='Staged manifest.json')
    parser.add_argument('--capture-result', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
    sources = source_checks(manifest)
    raw = args.input.read_bytes()
    capture = json.loads(args.capture_result.read_text(encoding='utf-8-sig')) if args.capture_result else None
    result = decode(raw, manifest, capture)
    result.update(source_checks=sources, proof_sha256=sha(raw), program_sha256=manifest['program_sha256'])
    text = json.dumps(result, indent=2) + '\n'
    if args.out:
        with args.out.open('x', encoding='utf-8') as output:
            output.write(text)
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
