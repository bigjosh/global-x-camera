"""Root-owned, bounded JS110 startup recorder; no firmware or SD commands.

Adapted from power-ablation-20261028/fixed_range_cold.py. Mutating modes need
--execute, a fresh exact current-firmware park proof, and measured awake-park
current bounds. VCP BREAK asserts this bench's NRST, not PE6 (recovery_gpio
README, October 20 qualification). Actual reset waveform is not measured here.
Cold-recovery sends C0 UART traffic across power-on without a BREAK command.
This variant starts C0 in the final 60 ms of a cold powered-reset hold,
then releases BREAK into recovery; the four-second train starts after OFF dwell.

Cleanup never changes OFF to ON. A failed held-reset experiment attempts OFF
before releasing BREAK; an unverified OFF is explicitly a cleanup failure.
Raw signal sample IDs/time maps are preserved. JS voltage is source-side;
startup amplitudes and full target-rail discharge remain unqualified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import queue
import sys
import threading
import time
from datetime import datetime, timezone

import numpy as np

CAMPAIGN = Path(__file__).resolve().parent
ROOT = CAMPAIGN.parents[2]
DEVICE = 'u/js110/000163'
PREFIX = '6378483a91b560ffc6b31d74a9dd1205996a14c8030447ffddf7deddc9d23874'
MODES = ('observe', 'cold-normal', 'cold-recovery', 'cold-reset-held',
         'warm-normal', 'warm-recovery')
RANGE = 's/i/range/select'
STREAMS = {'s/i/!data': 'current', 's/v/!data': 'voltage', 's/p/!data': 'power',
           's/gpi/0/!data': 'gpi0', 's/gpi/1/!data': 'gpi1',
           's/i/range/!data': 'current_range'}
SETTINGS = {'h/fs': 2000000, 's/extio/voltage': 3300,
            's/i/lsb_src': 2, 's/v/lsb_src': 3,
            's/i/ctrl': 1, 's/v/ctrl': 1, 's/p/ctrl': 1,
            's/gpi/0/ctrl': 1, 's/gpi/1/ctrl': 1, 's/i/range/ctrl': 1}
MEASUREMENT_TOPICS = (RANGE, 's/v/range/select', 's/i/range/mode',
                      's/i/range/pre', 's/i/range/win', 's/i/range/win_sz',
                      's/i/range/post', 's/i/lsb_src', 's/v/lsb_src')
EXTENSIONS = {'current': '.f32', 'voltage': '.f32', 'power': '.f32',
              'gpi0': '.u1', 'gpi1': '.u1', 'current_range': '.u8'}


def stamp():
    return {'utc': datetime.now(timezone.utc).isoformat(),
            'monotonic': time.monotonic()}


def clean(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: clean(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(val) for val in value]
    return value


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--mode', choices=MODES, default='observe')
    p.add_argument('--execute', action='store_true')
    p.add_argument('--park-proof', type=Path)
    p.add_argument('--park-current-min-ma', type=float)
    p.add_argument('--park-current-max-ma', type=float)
    p.add_argument('--on-range', type=int, choices=(1, 128), default=128,
                   help='Control setting 1=fixed10A,128=auto; stream codes differ')
    p.add_argument('--off-seconds', type=float, default=15)
    p.add_argument('--post-seconds', type=float, default=6)
    p.add_argument('--reset-hold-seconds', type=float, default=0.5)
    p.add_argument('--max-mib', type=int, default=768)
    a = p.parse_args(argv)
    a.out = a.out.resolve()
    a.out.relative_to(CAMPAIGN)
    if not 0.05 <= a.off_seconds <= 60:
        p.error('--off-seconds must be 0.05..60')
    if not 0.5 <= a.post_seconds <= 12:
        p.error('--post-seconds must be 0.5..12')
    if not 0.05 <= a.reset_hold_seconds <= 3:
        p.error('--reset-hold-seconds must be 0.05..3')
    if not 64 <= a.max_mib <= 2048:
        p.error('--max-mib must be 64..2048')
    if a.mode != 'observe':
        if not a.execute or not a.park_proof:
            p.error('Mutations require --execute and --park-proof')
        lo, hi = a.park_current_min_ma, a.park_current_max_ma
        if lo is None or hi is None or not 0 < lo < hi <= 500:
            p.error('Supply measured awake-park bounds: 0 < min < max <= 500 mA')
    elif a.execute or a.park_proof or a.on_range != 128:
        p.error('observe changes no target power/reset; omit execute/proof/on-range')
    if (a.mode.endswith('recovery') or a.mode == 'cold-reset-held') and a.post_seconds < 3:
        p.error('Recovery recording needs at least 3 post-seconds')
    # Native streams total about26.5MB/s. Include setup and restoration margin.
    seconds = 2 + a.post_seconds + 1.5
    if a.mode.startswith('cold-'):
        seconds += a.off_seconds
    if a.mode in ('cold-reset-held', 'warm-normal', 'warm-recovery'):
        seconds += a.reset_hold_seconds
    if seconds * 26500000 > a.max_mib * 1024**2:
        p.error('Recording exceeds raw byte budget; shorten dwell or raise max-mib')
    return a


def validate_proof(path, now=None):
    now = time.time() if now is None else now
    p = json.loads(path.read_bytes())
    age = now - path.stat().st_mtime
    if not (p.get('passed') is True and p.get('prefix_sha256') == PREFIX and
            p.get('context', {}).get('PC') == 0x3418078C and
            p.get('halt_requested') is True and p.get('ram_writes') is False and
            p.get('nor_commands') is False and 0 <= age < 600):
        raise ValueError('Exact current-firmware park proof failed identity/freshness')
    return {'path': str(path.resolve()), 'sha256': sha(path), 'age_seconds': age,
            'prefix_sha256': PREFIX, 'PC': p['context']['PC']}


def cleanup_range(initial, current):
    """Never restore power through an OFF output, including aborted OFF holds."""
    if current == 0:
        return 0
    if current is None:
        return None  # Unknown state is not permission to switch it.
    return initial if initial > 0 else current


def restore_range(dev, initial, event):
    """Query first. A failed query performs no power command; OFF stays OFF."""
    current = dev.query(RANGE, timeout=5)
    target = cleanup_range(initial, current)
    if target != current and target is not None:
        dev.publish(RANGE, target, timeout=5)
    final = dev.query(RANGE, timeout=5)
    if final != target:
        raise RuntimeError('Cleanup range readback mismatch')
    event('cleanup_power_state', initial=initial, before=current, final=final,
          retained_off=final == 0, rule='Never re-enable an OFF output during cleanup')
    return final


def wants_uart(mode):
    return mode in ('cold-recovery', 'cold-reset-held', 'warm-normal', 'warm-recovery')


def wants_train(mode):
    return mode in ('cold-recovery', 'warm-recovery')


class UART:
    """Finite VCP train and explicit BREAK; lazy import keeps offline tests offline."""
    def __init__(self, event):
        sys.path.insert(0, str(ROOT/'tmp/bringup/vcp-deps'))
        import serial
        from serial.tools import list_ports
        ports = [p for p in list_ports.comports()
                 if p.vid == 0x0483 and p.pid == 0x3754 and
                 p.serial_number == '002100203335511035383531']
        if len(ports) != 1:
            raise RuntimeError('Expected exact ST-LINK VCP, found '+repr(ports))
        self.event = event
        self.serial = serial.Serial()
        self.serial.port = ports[0].device
        self.serial.baudrate = 1000000
        self.serial.timeout = 0.2
        self.serial.write_timeout = 1
        self.serial.rts = False
        self.serial.dtr = False
        self.break_held = False
        self.stop = threading.Event()
        self.thread = None
        self.state = {'bytes': 0}
        self.serial.open()
        event('uart_opened', port=ports[0].device, baud=1000000,
              rts=False, dtr=False, usb_identity='0483:3754/002100203335511035383531')

    def set_break(self, level, reason):
        self.serial.break_condition = level
        self.break_held = level
        self.event('break_asserted' if level else 'break_released',
                   reason=reason, interpretation='Historical bench BREAK-to-NRST qualification; no current NRST probe')

    def start_train(self):
        def tx():
            try:
                deadline = time.monotonic() + 4
                while not self.stop.is_set() and time.monotonic() < deadline:
                    n = self.serial.write(bytes([0xC0])*4096)
                    if n != 4096:
                        raise RuntimeError('Short UART transmit')
                    self.state['bytes'] += n
            except Exception as ex:
                if not self.stop.is_set():
                    self.state['error'] = repr(ex)
        self.thread = threading.Thread(target=tx, name='bounded-recovery-uart')
        self.thread.start()
        self.event('uart_train_started', pattern='C0', deadline_seconds=4)

    def check(self):
        if 'error' in self.state:
            raise RuntimeError('UART train failed: '+self.state['error'])

    def close(self):
        failures = []
        self.stop.set()
        if self.serial.is_open:
            try:
                self.serial.cancel_write()
            except Exception as ex:
                failures.append(['cancel_write', repr(ex)])
        if self.thread:
            self.thread.join(2)
            if self.thread.is_alive():
                failures.append(['thread', 'UART transmitter did not stop'])
        if self.break_held:
            try:
                self.set_break(False, 'cleanup release; see reset-protection OFF result')
            except Exception as ex:
                failures.append(['break_release', repr(ex)])
        if self.serial.is_open:
            try:
                self.serial.reset_output_buffer()
            except Exception as ex:
                failures.append(['reset_output_buffer', repr(ex)])
            try:
                self.serial.close()
            except Exception as ex:
                failures.append(['close', repr(ex)])
        self.event('uart_closed', cleanup_failures=failures, **self.state)
        if failures:
            raise RuntimeError('UART cleanup failures: '+repr(failures))


def run(a):
    proof = validate_proof(a.park_proof) if a.mode != 'observe' else None
    a.out.mkdir(parents=True, exist_ok=False)
    q = queue.Queue(1024)
    errors, cleanup_errors, latest, recent = [], [], {}, []
    lock = threading.Lock()
    chunks = (a.out/'chunks.jsonl').open('x', encoding='utf-8')
    events = (a.out/'events.jsonl').open('x', encoding='utf-8')
    files = {s: (a.out/(s+EXTENSIONS[s])).open('xb') for s in STREAMS.values()}
    offsets = {s: 0 for s in files}
    hashes = {s: hashlib.sha256() for s in files}
    counts = {s: 0 for s in files}

    def event(name, **kw):
        row = dict(event=name, **stamp(), **clean(kw))
        events.write(json.dumps(row, allow_nan=False)+'\n')
        events.flush()
        print(json.dumps(row, allow_nan=False), flush=True)

    def callback(topic, value):
        try:
            val = dict(value)
            val['data'] = np.array(value['data'], copy=True)
            q.put_nowait((topic.removeprefix(DEVICE+'/'), val, time.monotonic()))
        except Exception as ex:
            errors.append('callback: '+repr(ex))

    def worker():
        try:
            while True:
                item = q.get()
                if item is None:
                    break
                topic, val, received = item
                signal = STREAMS[topic]
                data = val.pop('data')
                if signal.startswith('gpi') or signal == 'current_range':
                    if data.dtype != np.dtype('uint8'):
                        raise ValueError('Unexpected digital/range dtype')
                    if signal == 'current_range' and len(data) and int(data.max()) > 15:
                        raise ValueError('Invalid uint4 range data')
                    payload = data.tobytes()
                else:
                    if data.dtype.kind != 'f' or data.dtype.itemsize != 4:
                        raise ValueError('Unexpected analog dtype')
                    payload = data.astype('<f4', copy=False).tobytes()
                if sum(offsets.values()) + len(payload) > a.max_mib*1024**2:
                    raise RuntimeError('Raw byte budget exceeded')
                row = dict(signal=signal, byte_offset=offsets[signal], byte_count=len(payload),
                           dtype=str(data.dtype), received_monotonic=received, **clean(val))
                if signal.startswith('gpi'):
                    row['packed_bits'] = 'little; terminal padding unresolved until next sample_id'
                elif signal == 'current_range':
                    row['encoding'] = 'source uint4 expanded to uint8; one byte per sample'
                    row['delivered_samples'] = len(data)
                    row['value_counts'] = {str(int(v)): int(n)
                                           for v, n in zip(*np.unique(data, return_counts=True))}
                else:
                    good = data[np.isfinite(data)]
                    row.update(nonfinite=int(len(data)-len(good)),
                               mean=float(np.mean(good, dtype=np.float64)) if len(good) else None,
                               min=float(np.min(good)) if len(good) else None,
                               max=float(np.max(good)) if len(good) else None)
                if files[signal].write(payload) != len(payload):
                    raise OSError('Short sample write')
                offsets[signal] += len(payload)
                hashes[signal].update(payload)
                counts[signal] += 1
                chunks.write(json.dumps(row, allow_nan=False)+'\n')
                with lock:
                    latest[signal] = row
                    if signal == 'current':
                        recent.append(row)
                        del recent[:-40]
        except Exception as ex:
            errors.append('worker: '+repr(ex))

    thread = threading.Thread(target=worker, name='raw-stream-writer')
    thread.start()
    initial, restored, changed, subscriptions = {}, {}, [], []
    uart = None
    complete = False
    final_power = None
    sys.path.insert(0, str(ROOT/'tmp/bringup/joulescope-deps'))
    try:
        from pyjoulescope_driver import Driver, __version__
        with Driver() as driver:
            if DEVICE not in driver.device_paths():
                raise RuntimeError('Expected JS110 absent')
            with driver.open(DEVICE, mode='restore', timeout=5) as dev:
                try:
                    for topic in dict.fromkeys([*MEASUREMENT_TOPICS, *SETTINGS]):
                        initial[topic] = dev.query(topic, timeout=5)
                    if a.mode != 'observe' and initial[RANGE] != 128:
                        raise RuntimeError('Mutations require starting auto range128')
                    event('opened', driver=__version__, mode=a.mode,
                          initial=initial, proof=proof, on_range=a.on_range,
                          boundary='Root must verify direct bench5V -> JS -> CN5.5/GND CN5.6; GPI0 PD12/GPI1 PD0')
                    for topic in STREAMS:
                        driver.subscribe(DEVICE+'/'+topic, 'pub', callback)
                        subscriptions.append(DEVICE+'/'+topic)
                    for topic, value in SETTINGS.items():
                        if initial[topic] != value:
                            changed.append(topic)
                            dev.publish(topic, value, timeout=5)
                            if dev.query(topic, timeout=5) != value:
                                raise RuntimeError('Setting mismatch '+topic)

                    def observations():
                        if errors:
                            raise RuntimeError(str(errors))
                        if uart:
                            uart.check()
                        with lock:
                            rows = dict(latest)
                        for signal in STREAMS.values():
                            row = rows.get(signal, {})
                            if not row.get('byte_count') or time.monotonic()-row['received_monotonic'] > 1:
                                raise RuntimeError('Missing/stale '+signal)
                        for signal in ('current', 'voltage'):
                            row = rows[signal]
                            if row.get('mean') is None or row['nonfinite']:
                                raise RuntimeError('Nonfinite '+signal)
                        if not 4.5 < rows['voltage']['mean'] < 5.5:
                            raise RuntimeError('Source outside5V range')
                        return rows

                    def wait(seconds):
                        until = time.monotonic()+seconds
                        while time.monotonic() < until:
                            observations()
                            time.sleep(min(0.025, max(0, until-time.monotonic())))

                    def power(value, reason):
                        event('power_command_begin', value=value, reason=reason)
                        dev.publish(RANGE, value, timeout=5)
                        actual = dev.query(RANGE, timeout=5)
                        event('power_command_readback', value=actual, reason=reason)
                        if actual != value:
                            raise RuntimeError('Power/range setting readback failed')

                    # Initial callbacks may contain transient NaNs before steady stream starts.
                    time.sleep(2)
                    rows = observations()
                    event('ready', means={s: rows[s].get('mean') for s in rows}, counts=counts)
                    if a.mode == 'observe':
                        wait(a.post_seconds)
                    else:
                        proof = validate_proof(a.park_proof)
                        current_ma = rows['current']['mean']*1000
                        if not a.park_current_min_ma < current_ma < a.park_current_max_ma:
                            raise RuntimeError('Awake-park current outside supplied measured bounds')
                        event('mutation_gate_pass', proof=proof, park_current_ma=current_ma,
                              accepted_bounds_ma=[a.park_current_min_ma, a.park_current_max_ma])
                        if wants_uart(a.mode):
                            uart = UART(event)
                        if a.mode.startswith('cold-'):
                            if a.mode == 'cold-reset-held':
                                uart.set_break(True, 'hold MCU reset across cold supply startup')
                            power(0, 'cold OFF')
                            off_start = time.monotonic()
                            event('power_off')
                            wait(a.off_seconds)
                            with lock:
                                tail = [r for r in recent if r['received_monotonic'] >=
                                        off_start + max(0, a.off_seconds-0.25)]
                            if not tail or any(r['nonfinite'] or r['mean'] is None or
                                               abs(r['mean']) >= .0001 for r in tail):
                                raise RuntimeError('No verified near-zero OFF-current interval')
                            event('off_verified', seconds=time.monotonic()-off_start,
                                  mean_a=tail[-1]['mean'], observed_chunks=len(tail),
                                  limitation='Current only; target rail discharge unmeasured')
                            if wants_train(a.mode):
                                uart.start_train()
                                wait(.06)
                                if not uart.state['bytes']:
                                    raise RuntimeError('No UART bytes delivered before power-on')
                            power(a.on_range, 'cold ON')
                            event('power_on', on_range=a.on_range)
                            if a.mode == 'cold-reset-held':
                                # Start late: preserve the powered hold duration and do not
                                # spend the finite four-second train during the OFF dwell.
                                train_lead = min(.06, a.reset_hold_seconds)
                                wait(a.reset_hold_seconds - train_lead)
                                uart.start_train()
                                wait(train_lead)
                                if not uart.state['bytes']:
                                    raise RuntimeError('No UART bytes delivered before held reset release')
                                event('reset_hold_observation_complete',
                                      recovery_train_lead_seconds=train_lead)
                                uart.set_break(False, 'planned reset release into UART recovery after powered hold')
                            wait(a.post_seconds)
                        else:
                            if a.on_range != initial[RANGE]:
                                power(a.on_range, 'warm test measurement range')
                                wait(.2)
                            if wants_train(a.mode):
                                uart.start_train()
                                wait(.06)
                                if not uart.state['bytes']:
                                    raise RuntimeError('No UART bytes delivered before warm reset')
                            uart.set_break(True, 'warm reset')
                            wait(a.reset_hold_seconds)
                            uart.set_break(False, 'planned warm reset release')
                            wait(a.post_seconds)
                    event('observation_end', means={s: r.get('mean')
                          for s, r in observations().items()}, counts=counts)
                    complete = True
                finally:
                    # If an experiment fails while BREAK holds a powered MCU,
                    # cut output before releasing reset; never introduce a cleanup boot.
                    if uart and uart.break_held and not complete:
                        try:
                            dev.publish(RANGE, 0, timeout=5)
                            if dev.query(RANGE, timeout=5) != 0:
                                raise RuntimeError('Could not power OFF before cleanup reset release')
                            event('cleanup_reset_protection_off')
                        except Exception as ex:
                            cleanup_errors.append(['reset_protection_off', repr(ex)])
                            event('cleanup_reset_release_unqualified',
                                  note='OFF could not be proven; BREAK cleanup may permit an unrecorded boot')
                    if uart:
                        try:
                            uart.close()
                        except Exception as ex:
                            cleanup_errors.append(['uart_close', repr(ex)])
                    try:
                        if RANGE in initial:
                            final_power = restore_range(dev, initial[RANGE], event)
                    except Exception as ex:
                        cleanup_errors.append(['range_cleanup', repr(ex)])
                    for topic in reversed(changed):
                        try:
                            dev.publish(topic, initial[topic], timeout=5)
                            if dev.query(topic, timeout=5) != initial[topic]:
                                raise RuntimeError('Restore mismatch')
                        except Exception as ex:
                            cleanup_errors.append([topic, repr(ex)])
                    for topic, value in initial.items():
                        try:
                            restored[topic] = dev.query(topic, timeout=5)
                            permitted = final_power if topic == RANGE else value
                            if restored[topic] != permitted:
                                raise RuntimeError('Final setting differs from intended cleanup')
                        except Exception as ex:
                            cleanup_errors.append([topic, repr(ex)])
                    for topic in subscriptions:
                        try:
                            driver.unsubscribe(topic, callback)
                        except Exception as ex:
                            cleanup_errors.append([topic, repr(ex)])
    except Exception as ex:
        errors.append(repr(ex))
        event('error', error=repr(ex))
    finally:
        if thread.is_alive():
            try:
                q.put(None, timeout=3)
            except queue.Full:
                errors.append('Writer stop sentinel queue full')
        thread.join(timeout=10)
        if thread.is_alive():
            raise RuntimeError('Writer did not stop; no completion claim')
        for f in files.values():
            f.close()
        chunks.close()
        result = dict(success=complete and not errors and not cleanup_errors, **stamp(),
                      mode=a.mode, on_range=a.on_range, off_seconds=a.off_seconds,
                      post_seconds=a.post_seconds, reset_hold_seconds=a.reset_hold_seconds,
                      errors=errors, cleanup_errors=cleanup_errors, proof=proof,
                      source_sha256=sha(__file__), initial_settings=initial,
                      restored_settings=restored, final_power_range=final_power,
                      counts=counts, bytes=offsets,
                      sha256={s: h.hexdigest() for s, h in hashes.items()},
                      uart_state=uart.state if uart else None,
                      scope='Raw startup/reset observation only. No fresh final recovery, target rail, image readback or Standby proof. Source-side voltage and startup physical amplitude remain unqualified.')
        (a.out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
        event('closed', success=result['success'], errors=errors,
              cleanup_errors=cleanup_errors, final_power_range=final_power)
        events.close()
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(run(parse_args()))
