"""RAM-only knob test launcher and local ST-LINK readout. No reset or flash API.

The launch path requires the exact installed UART recovery park. The existing
reviewed SRAM bridge establishes the uncached 400 MHz execution environment.
The console reads telemetry without halting. Closing it does not cut power.
"""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import secrets
import struct
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'firmware/boot-timing'))
import nor_bench


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def checked(build, expected):
    m = json.loads((build / 'manifest.json').read_text())
    code = (build / 'control.bin').read_bytes()
    if hashlib.sha256(code).hexdigest() != expected or m['sha256'] != expected:
        raise ValueError('Diagnostic binary identity differs')
    exact = dict(kind='exposure-knob-adc-ram', load=0x34300000,
                 proof=0x343C2000, proof_words=64, request=0x343C1F00,
                 request_words=8, stack=0x343B0000, stack_floor=0x343AF000,
                 sd_commands=False, nor_commands=False, camera_commands=False,
                 reset=False, power_switch=False, resolution_bits=12)
    if m['schema'] not in (1, 2) or any(m.get(k) != v for k, v in exact.items()):
        raise ValueError('Unexpected diagnostic layout or capabilities')
    if not (m['bytes'] == len(code) < 65536 and
            m['load'] <= m['entry'] - 1 < m['load'] + len(code) and
            m['load'] + len(code) <= m['bss_start'] <= m['bss_end'] < 0x34310000):
        raise ValueError('Invalid code/BSS layout')
    offset = m['park'] - m['load']
    if code[offset:offset+2] != b'\xfe\xe7':
        raise ValueError('Expected explicit awake terminal park')
    for name, digest in m['sources'].items():
        if hashlib.sha256((build / name).read_bytes()).hexdigest() != digest:
            raise ValueError('Frozen source differs: ' + name)
    return m, code


def replace(args):
    """Stop this exact ADC-only helper, then replace it in uncached SRAM."""
    session = json.loads(args.session.read_text())
    old, old_code = checked(Path(session['build']), session['sha256'])
    m, code = checked(args.build, args.sha256)
    args.out.mkdir(parents=True, exist_ok=False)
    b = nor_bench.Bench(args.out / 'replace')
    if b.upload(old['load'], len(old_code), 'old-code.bin') != old_code:
        raise ValueError('Prior RAM code changed')
    status = read_status(b, old, session['nonce'], 'old-status.bin')
    if status['STATE'] not in (4, 8) or status['ERROR_CODE']:
        raise ValueError('Prior ADC test is not running or cleanly stopped')
    if status['STATE'] == 4:
        # This exact program has no storage or power-switch operations. Halt
        # only after its identity and fresh sampling state have been checked.
        b.call('-halt', '-coreReg')
        stop = b.output / 'stop.bin'
        stop.write_bytes(struct.pack('<I', old['stop_magic']))
        b.call('-halt', '-w', stop, hex(old['request']+28), '-v', '-run', success='Core run')
        time.sleep(0.2)
    status = read_status(b, old, session['nonce'], 'stopped-status.bin')
    if status['STATE'] != 8 or status['ERROR_CODE'] or status['TERMINAL'] != 0x454E4F44:
        raise ValueError('Prior helper did not stop cleanly; no replacement')
    bridge = load_module('control_replace_bridge', ROOT/'firmware/capture-sd/low_power/readback_recovery/run.py')
    bridge.sd.context_proof(b, {old['park']}, 'stopped-context')
    if any(struct.unpack('<II', b.upload(0xE000ED28, 8, 'stopped-faults.bin'))):
        raise ValueError('Fault flags set; no replacement')
    b.call('-halt', '-w', args.build/'control.bin', hex(m['load']), '-v', success='Download verified successfully')
    if b.upload(m['load'], len(code), 'new-code-readback.bin') != code:
        raise ValueError('New code readback differs')
    nonce = secrets.randbelow(0xFFFFFFFF)+1
    request = struct.pack('<8I', m['request_magic'], nonce, args.samples, 100, 0, 0, 0, 0)
    (b.output/'request.bin').write_bytes(request)
    (b.output/'clear.bin').write_bytes(bytes(256))
    b.call('-halt', '-w', b.output/'request.bin', hex(m['request']), '-v',
           '-w', b.output/'clear.bin', hex(m['proof']), '-v', success='Download verified successfully')
    if b.upload(m['request'], 32, 'request-readback.bin') != request:
        raise ValueError('New request differs')
    save(args.out/'session.json', dict(build=str(args.build), sha256=m['sha256'], nonce=nonce,
         cli=str(nor_bench.CLI), manifest=m, request_words=list(struct.unpack('<8I', request)),
         prior_session=str(args.session), started_utc=datetime.now(timezone.utc).isoformat()))
    b.call('-halt', '-coreReg', f"PC={hex(m['entry'])}", 'XPSR=0x01000000', '-run', success='Core run')
    print('RAM ADC diagnostic replaced; session:', args.out/'session.json', flush=True)


def prepare(args):
    m, code = checked(args.build, args.sha256)
    args.out.mkdir(parents=True, exist_ok=False)
    bridge = load_module('control_bridge', ROOT / 'firmware/capture-sd/low_power/readback_recovery/run.py')
    guard = load_module('control_guard', ROOT / 'firmware/capture-timing/recovery_gpio/check_park.py')
    identity = bridge.checked_recovery(args.recovery_build)
    guard_out = args.out / 'early-guard'
    old_argv = sys.argv
    buffer = io.StringIO()
    try:
        sys.argv = ['check_park', '--build', str(args.recovery_build), '--out', str(guard_out)]
        with contextlib.redirect_stdout(buffer):
            guard.main()
    finally:
        sys.argv = old_argv
        (args.out / 'early-guard.log').write_text(buffer.getvalue(), encoding='utf-8')
    result = json.loads((guard_out / 'result.json').read_text())
    bridge.checked_recovery_result(result, identity)
    bridge_path = ROOT / 'tmp/bringup/capture-sleep-20261020/recovery-read-bridge-v1'
    _, boot_code = bridge.checked_bridge(bridge_path)
    b = nor_bench.Bench(args.out / 'launch')
    nonce = secrets.randbelow(0xFFFFFFFF) + 1
    request = struct.pack('<4I', 0x52425231, nonce, 0, 0)
    (b.output / 'bridge-request.bin').write_bytes(request)
    (b.output / 'bridge-clear.bin').write_bytes(bytes(92))
    b.call('-halt', '-w', bridge_path / 'boot.bin', hex(bridge.LOAD), '-v',
           success='Download verified successfully')
    if b.upload(bridge.LOAD, len(boot_code), 'bridge-readback.bin') != boot_code:
        raise ValueError('Bridge readback differs')
    b.call('-halt', '-w', b.output / 'bridge-clear.bin', hex(bridge.BOOT_PROOF), '-v',
           '-w', b.output / 'bridge-request.bin', hex(bridge.BOOT_REQUEST), '-v',
           success='Download verified successfully')
    if b.upload(bridge.BOOT_REQUEST, 16, 'bridge-request-readback.bin') != request:
        raise ValueError('Bridge request differs')
    b.call('-halt', '-coreReg', 'PC=0x341E0001', 'XPSR=0x01000000', '-run', success='Core run')
    proof = bridge.wait_boot(b, nonce)
    bridge.sd.context_proof(b, {bridge.BOOT_PARK}, 'bridge-final')
    if struct.unpack_from('<2I', b.upload(0x341F5000, 128, 'memory-proof.bin')) != (0x5231304D, 0):
        raise ValueError('SRAM initialization failed')
    save(args.out / 'bridge-proof.json', proof)
    b.call('-halt', '-w', args.build / 'control.bin', hex(m['load']), '-v',
           success='Download verified successfully')
    if b.upload(m['load'], len(code), 'control-readback.bin') != code:
        raise ValueError('ADC program readback differs')
    nonce = secrets.randbelow(0xFFFFFFFF) + 1
    request = struct.pack('<8I', m['request_magic'], nonce, args.samples, 100, 0, 0, 0, 0)
    (b.output / 'control-request.bin').write_bytes(request)
    (b.output / 'control-clear.bin').write_bytes(bytes(256))
    b.call('-halt', '-w', b.output / 'control-request.bin', hex(m['request']), '-v',
           '-w', b.output / 'control-clear.bin', hex(m['proof']), '-v',
           success='Download verified successfully')
    if b.upload(m['request'], 32, 'control-request-readback.bin') != request:
        raise ValueError('ADC request differs')
    session = dict(build=str(args.build), sha256=m['sha256'], nonce=nonce,
                   cli=str(nor_bench.CLI), request_words=list(struct.unpack('<8I', request)),
                   manifest=m, started_utc=datetime.now(timezone.utc).isoformat())
    save(args.out / 'session.json', session)
    b.call('-halt', '-coreReg', f"PC={hex(m['entry'])}", 'XPSR=0x01000000', '-run', success='Core run')
    print('ADC test started; session:', args.out / 'session.json', flush=True)


def read_status(b, m, nonce, name):
    raw = b.upload(m['proof'], 256, name)
    p = dict(zip(m['fields'], struct.unpack('<64I', raw)))
    p['SEQUENCE_END'] = struct.unpack_from('<I', raw, 4*m['proof_sequence_end_word'])[0]
    if p['MAGIC'] != 0x31434441 or p['VERSION'] != m['schema'] or p['NONCE'] != nonce:
        raise ValueError('Telemetry identity differs; target left untouched')
    return p


def monitor(args):
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW('Exposure knob A4 - live ADC')
    session = json.loads(args.session.read_text())
    m, code = checked(Path(session['build']), session['sha256'])
    b = nor_bench.Bench(args.out)
    if b.upload(m['load'], len(code), 'live-code.bin') != code:
        raise ValueError('Running code differs from this test')
    print('Exposure knob: A3 = LOW, A4 = wiper, A5 = HIGH', flush=True)
    print('12-bit raw ADC; 4095 is digital full scale, not a calibrated knob endpoint.', flush=True)
    print('Turn the knob to see readings. Ctrl+C closes this console; test has a finite sample limit.', flush=True)
    began = time.monotonic()
    last_count = None
    for n in range(args.polls):
        p = read_status(b, m, session['nonce'], f'status-{n:05d}.bin')
        # Bracket the live data within a single memory transfer. A second CLI
        # invocation would be slower than the 100 ms sample interval.
        seq = p['SEQUENCE_END']
        if seq != p['SEQUENCE'] or seq & 1:
            continue
        p['host_utc'] = datetime.now(timezone.utc).isoformat()
        with (args.out / 'readings.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(p) + '\n')
        save(args.out / 'latest.json', p)
        print(f"{time.monotonic()-began:7.1f}s  A4 raw={p['RAW']:4d}  min={p['MIN_RAW']:4d}  "
              f"max={p['MAX_RAW']:4d}  samples={p['SAMPLE_COUNT']:6d}  "
              f"A3={p['PA2_IDR']} A5={p['PH2_IDR']}  state={p['STATE']} error={p['ERROR_CODE']}", flush=True)
        if m['schema'] >= 2:
            print(f"          endpoint ADC: A3={p['A3_RAW']:4d}  A5={p['A5_RAW']:4d}  A4 digital={p['A4_DIGITAL']}", flush=True)
        if p['ERROR_CODE'] or p['STATE'] == 15:
            raise RuntimeError('ADC diagnostic failed; see latest.json. Target left powered.')
        if p['STATE'] == 8:
            print('Test complete; pot supply LOW, HOLD HIGH, debugger awake.', flush=True)
            return
        if last_count == p['SAMPLE_COUNT']:
            print('Warning: no new ADC sample since last observation.', flush=True)
        last_count = p['SAMPLE_COUNT']
        time.sleep(args.interval)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=['launch', 'replace', 'monitor'])
    p.add_argument('--cli', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--build', type=Path)
    p.add_argument('--sha256')
    p.add_argument('--recovery-build', type=Path, default=ROOT/'tmp/bringup/sensor-autostop-promote-20261028/flash-standby-v1/staged')
    p.add_argument('--samples', type=int, default=36000)
    p.add_argument('--session', type=Path)
    p.add_argument('--polls', type=int, default=10000)
    p.add_argument('--interval', type=float, default=0.4)
    a = p.parse_args()
    if not a.cli.is_file():
        p.error('Programmer executable not found')
    nor_bench.CLI = a.cli.resolve()
    a.out = a.out.resolve()
    if a.operation in ('launch', 'replace'):
        if not a.build or not a.sha256 or not 1 <= a.samples <= 36000:
            p.error('Launch requires build, explicit SHA256 and bounded sample count')
        a.build = a.build.resolve()
        if a.operation == 'replace':
            if not a.session:
                p.error('Replacement requires prior ADC session')
            replace(a)
        else:
            prepare(a)
    else:
        if not a.session or a.polls < 1 or a.interval < 0.1:
            p.error('Monitor requires a session and positive polling bounds')
        monitor(a)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nConsole closed; no reset or power change issued.')
