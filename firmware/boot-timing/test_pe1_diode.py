"""Bounded, opt-in powered PE1/JS110 diode wiring test; no reset or power control.

PE1 (CN15.24) is the diode anode, JS110 OUT0 its cathode. Only PE1 input mode
and weak pulls are changed. IDR observations establish logic behavior, not
analog diode drop, noise margin, zero leakage, or target-off backfeed safety.
The optional supply-off matrix tests whether the *powered* MCU follows its
own pulls with the JS110 shared external-I/O supply disabled. It must not be
described as a target power-off test or assumed to prove a high-impedance pin.

Requires exclusive bench ownership and the exact completed v25 receiver. Saves
and restores PE1 fields and owned JS110 settings; never writes OUT1 or the
current range. Failure after halt leaves the core halted. Only an entirely
successful matrix and restoration resumes it. Importing this module is inert.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys
import time

from js110_session import DEFAULT_DEPS, EXTIO_TOPIC, GPO_TOPICS, RANGE_TOPIC, Statistics, stamp
from nor_bench import Bench

GPIOE = 0x56021000
MODER, PUPDR, IDR = GPIOE, GPIOE + 12, GPIOE + 16
AHB4ENR, AHB4RSTR = 0x5602825C, 0x5602821C
PIN_MASK, FIELD_MASK = 2, 12
V25_RECEIVER_SHA = '85313ae05070d80717c29a8a546bf56976930ac1f47b92e4ae70576ae72c940f'
V25_RECEIVER_BYTES = 11964
ROUTES = ('s/gpi/0/ctrl', 's/gpi/1/ctrl', 's/i/lsb_src', 's/v/lsb_src')
STATS_CTRL, STATS_TOPIC = 's/sstats/ctrl', 's/sstats/value'
ACTIVE_MATRIX = ((1, 0, 0), (1, 1, 1), (2, 1, 0), (2, 0, 0))
OFF_MATRIX = ((1, 0, 1), (2, 0, 0), (1, 1, 1), (2, 1, 0))


def field(value, setting):
    return (value & ~FIELD_MASK) | (setting << 2)


def check_supply(sample):
    if not sample or sample.get('age_s', math.inf) > 2:
        raise ValueError('Fresh JS110 source-voltage statistics unavailable')
    voltage = sample.get('voltage', {})
    values = [voltage.get(name) for name in ('min', 'avg', 'max')]
    if any(type(v) not in (float, int) or not math.isfinite(v) or v < 4.5 for v in values):
        raise ValueError('Require measured JS110 IN+ voltage >=4.5 V throughout statistics window')
    return sample


def check_settings(settings, routes, *, change_supply, other_disconnected):
    if type(settings[EXTIO_TOPIC]) is not int or settings[EXTIO_TOPIC] not in (0, 3300):
        raise ValueError('Shared I/O supply must start at 3300 mV or off')
    for topic in GPO_TOPICS:
        if type(settings[topic]) not in (int, bool) or settings[topic] not in (0, 1):
            raise ValueError('Invalid retained output state')
    if change_supply:
        if not other_disconnected:
            raise ValueError('Changing shared I/O supply requires --other-gpio-disconnected')
        if settings[GPO_TOPICS[1]] != 0 or any(routes.get(topic) != 0 for topic in ROUTES):
            raise ValueError('Shared supply change refused with OUT1 high or another GPIO route active')


def check_receiver(data):
    # The one writable .data word is SystemCoreClock, the final 4 bytes. Its
    # reviewed initialization is 64 MHz and completed v25 runtime is 400 MHz.
    if len(data) != V25_RECEIVER_BYTES or struct.unpack('<I', data[-4:])[0] != 400_000_000:
        raise ValueError('Unexpected live receiver size or SystemCoreClock')
    normalized = data[:-4] + struct.pack('<I', 64_000_000)
    if hashlib.sha256(normalized).hexdigest() != V25_RECEIVER_SHA:
        raise ValueError('Live receiver is not the reviewed v25 code')


def check_trace(data):
    words = struct.unpack('<64I', data)
    if words[0] != 0x43545031 or words[1] != 40 or words[5] != 1:
        raise ValueError('Require one completed v25 capture at stage 40')
    return words


class Target:
    def __init__(self, bench):
        self.bench, self.reads = bench, 0
        self.initial = None
        self.halt_attempted = False
        self.modified = False

    def read(self, address, name):
        self.reads += 1
        return struct.unpack('<I', self.bench.upload(address, 4, f'{self.reads:03d}-{name}.bin'))[0]

    def write_field(self, address, setting, name):
        current = self.read(address, name + '-before')
        desired = field(current, setting)
        self.modified = True  # A failed CLI may still have changed the register.
        self.bench.call('-w32', hex(address), hex(desired))
        if self.read(address, name + '-after') != desired:
            raise RuntimeError(name + ' readback differs')

    def check_and_halt(self):
        check_trace(self.bench.upload(0x343F0000, 256, 'completed-trace.bin'))
        check_receiver(self.bench.upload(0x34300000, V25_RECEIVER_BYTES, 'live-receiver.bin'))
        enabled, reset = self.read(AHB4ENR, 'clock'), self.read(AHB4RSTR, 'reset')
        if not enabled & 16 or reset & 16:
            raise ValueError('GPIOE must already be clocked and released from reset')
        moder, pupdr = self.read(MODER, 'initial-moder'), self.read(PUPDR, 'initial-pupdr')
        if (moder >> 2) & 3 not in (0, 3):
            raise ValueError('PE1 must initially be input or analog; no output contention test')
        self.halt_attempted = True
        text = self.bench.call('-halt', '-coreReg')
        regs = {name: int(value, 16) for name, value in re.findall(
            r'^(PC|XPSR|CONTROL|FAULTMASK)\s*=\s*0x([0-9A-Fa-f]+)', text, re.M)}
        if (not self.read(0xE000EDF0, 'dhcsr') & (1 << 17) or
                regs.get('XPSR', 511) & 511 or regs.get('CONTROL', 3) & ~12 or
                regs.get('FAULTMASK') != 0):
            raise ValueError('Core halt/privileged Thread context was not confirmed')
        check_trace(self.bench.upload(0x343F0000, 256, 'halted-trace.bin'))
        if self.read(MODER, 'halted-moder') != moder or self.read(PUPDR, 'halted-pupdr') != pupdr:
            raise ValueError('GPIO configuration changed during halt; no pin changes made')
        self.initial = {'moder': moder, 'pupdr': pupdr, 'core': regs}
        return self.initial

    def restore(self):
        errors = []
        if self.modified and self.initial is not None:
            # Always remain input while restoring the original weak pull, then
            # restore the original input/analog mode. Only PE1 fields are written.
            for address, setting, name in (
                    (MODER, 0, 'restore-input'),
                    (PUPDR, (self.initial['pupdr'] >> 2) & 3, 'restore-pull'),
                    (MODER, (self.initial['moder'] >> 2) & 3, 'restore-mode')):
                try:
                    self.write_field(address, setting, name)
                except Exception as exc:
                    errors.append(name + ': ' + str(exc))
        return errors


def run_matrix(target, output, supply_check, record, matrix, supply_mv):
    for pull, level, expected in matrix:
        supply_check()
        target.write_field(PUPDR, pull, 'pull-' + str(pull))
        output(GPO_TOPICS[0], level)
        time.sleep(0.002)  # Weak-pull settling; not a boot-time measurement.
        actual = target.read(IDR, 'idr')
        row = {'shared_supply_mv': supply_mv, 'pull': 'up' if pull == 1 else 'down',
               'out0_retained': level, 'idr': actual, 'pe1': int(bool(actual & PIN_MASK)),
               'expected': expected, 'passed': bool(actual & PIN_MASK) == bool(expected)}
        record(row)
        if not row['passed']:
            raise RuntimeError('PE1 diode matrix mismatch; subsequent combinations skipped')


def run(args, driver_factory, driver_version):
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    result = {'passed': False, 'driver_version': driver_version, 'samples': [],
              'limitations': __doc__, 'reset_flash_power_commands': False,
              'core_resumed': False, 'restore_errors': []}
    target = Target(Bench(out / 'swd'))
    stats = Statistics()

    def event(kind, **values):
        with (out / 'events.jsonl').open('a', encoding='utf-8') as log:
            log.write(json.dumps(dict(event=kind, **stamp(), **values), allow_nan=False) + '\n')

    def sample(row):
        result['samples'].append(row)
        event('pin_sample', **row)

    def source():
        previous = stats.snapshot()
        seq = previous['sequence'] if previous else 0
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            latest = stats.snapshot()
            if latest and latest['sequence'] > seq:
                check_supply(latest)
                event('source_voltage', statistics=latest)
                return latest
            time.sleep(0.05)
        raise RuntimeError('No fresh JS110 voltage statistics within 5 seconds')

    try:
        with driver_factory() as driver:
            if args.device not in driver.device_paths():
                raise RuntimeError('Required JS110 is absent')
            with driver.open(args.device, mode='restore', timeout=5.0) as device:
                starting, changed, subscribed = {}, set(), False
                good = False

                def query(topic):
                    return device.query(topic, timeout=5.0)

                def output(topic, value):
                    if topic not in (EXTIO_TOPIC, GPO_TOPICS[0]):
                        raise ValueError('Only OUT0 and shared supply are owned')
                    if query(GPO_TOPICS[1]) != starting[GPO_TOPICS[1]]:
                        raise RuntimeError('OUT1 changed; stop rather than overwrite another owner')
                    if query(RANGE_TOPIC) != starting[RANGE_TOPIC]:
                        raise RuntimeError('Current range changed externally; stop without changing power')
                    changed.add(topic)
                    device.publish(topic, value, timeout=5.0)
                    if query(topic) != value:
                        raise RuntimeError('JS110 retained-setting readback differs')

                try:
                    starting = {topic: query(topic) for topic in
                                (EXTIO_TOPIC, *GPO_TOPICS, RANGE_TOPIC, STATS_CTRL)}
                    routes = {topic: query(topic) for topic in ROUTES}
                    check_settings(starting, routes,
                                   change_supply=args.test_supply_off or starting[EXTIO_TOPIC] == 0,
                                   other_disconnected=args.other_gpio_disconnected)
                    result['starting_js'] = starting
                    device.subscribe(STATS_TOPIC, 'pub', stats.receive)
                    subscribed = True
                    if not starting[STATS_CTRL]:
                        changed.add(STATS_CTRL)
                        device.publish(STATS_CTRL, 1, timeout=5.0)
                    source()  # No GPIO/core mutation before measured source power.
                    result['starting_target'] = target.check_and_halt()
                    source()
                    target.write_field(MODER, 0, 'input-mode')
                    output(GPO_TOPICS[0], 1)  # Diode release before I/O supply enable.
                    if starting[EXTIO_TOPIC] == 0:
                        output(EXTIO_TOPIC, 3300)
                    run_matrix(target, output, source, sample, ACTIVE_MATRIX, 3300)
                    if args.test_supply_off:
                        source()
                        output(EXTIO_TOPIC, 0)
                        run_matrix(target, output, source, sample, OFF_MATRIX, 0)
                    good = True
                except (Exception, KeyboardInterrupt) as exc:
                    result['error'] = type(exc).__name__ + ': ' + str(exc)
                finally:
                    result['restore_errors'].extend(target.restore())
                    # Off first when originally off; release high before an
                    # originally active supply is restored, then original OUT0.
                    restore = []
                    if starting.get(EXTIO_TOPIC) == 0:
                        restore = [(EXTIO_TOPIC, 0), (GPO_TOPICS[0], starting.get(GPO_TOPICS[0]))]
                    elif starting.get(EXTIO_TOPIC) == 3300:
                        if EXTIO_TOPIC in changed:
                            restore = [(GPO_TOPICS[0], 1), (EXTIO_TOPIC, 3300)]
                        restore.append((GPO_TOPICS[0], starting.get(GPO_TOPICS[0])))
                    for topic, value in restore:
                        if topic in changed:
                            try:
                                if topic == EXTIO_TOPIC and query(GPO_TOPICS[1]) != starting[GPO_TOPICS[1]]:
                                    raise RuntimeError('OUT1 changed; refusing shared-voltage restoration')
                                # Restore our owned output even if an external
                                # client changed the current range. Never undo
                                # that range change or write an OUT1 value.
                                device.publish(topic, value, timeout=5.0)
                                if query(topic) != value:
                                    raise RuntimeError('Restored setting readback differs')
                            except Exception as exc:
                                result['restore_errors'].append(topic + ': ' + str(exc))
                    if STATS_CTRL in changed:
                        try:
                            device.publish(STATS_CTRL, starting[STATS_CTRL], timeout=5.0)
                            if query(STATS_CTRL) != starting[STATS_CTRL]:
                                raise RuntimeError('Statistics restore readback differs')
                        except Exception as exc:
                            result['restore_errors'].append('statistics: ' + str(exc))
                    if subscribed:
                        try:
                            device.unsubscribe(STATS_TOPIC, stats.receive, timeout=5.0)
                        except Exception as exc:
                            result['restore_errors'].append('unsubscribe: ' + str(exc))
                    if starting:
                        try:
                            result['final_js'] = {topic: query(topic) for topic in starting}
                            if result['final_js'] != starting:
                                raise RuntimeError('Final JS110 settings differ from original')
                        except Exception as exc:
                            result['restore_errors'].append('final settings: ' + str(exc))
                    result['passed'] = good and not result['restore_errors']
                    if result['passed']:
                        target.bench.call('-run', success='Core run')
                        if target.read(0xE000EDF0, 'resumed-dhcsr') & (1 << 17):
                            raise RuntimeError('Core remained halted after resume')
                        result['core_resumed'] = True
                    result['core_halt_attempted'] = target.halt_attempted
    except (Exception, KeyboardInterrupt) as exc:
        result['passed'] = False
        result['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        (out / 'result.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(result, allow_nan=False))
    return 0 if result['passed'] and result['core_resumed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--device', default='u/js110/000163')
    parser.add_argument('--deps', type=Path, default=DEFAULT_DEPS)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--exclusive-bench', action='store_true', help='Confirm no other instrument/debugger owner')
    parser.add_argument('--other-gpio-disconnected', action='store_true')
    parser.add_argument('--test-supply-off', action='store_true')
    args = parser.parse_args()
    if not args.execute or not args.exclusive_bench:
        parser.error('Explicit --execute --exclusive-bench required')
    if not args.device.startswith('u/js110/'):
        parser.error('JS110 only')
    if args.test_supply_off and not args.other_gpio_disconnected:
        parser.error('--test-supply-off requires --other-gpio-disconnected')
    sys.path.insert(0, str(args.deps.resolve()))
    from pyjoulescope_driver import Driver, __version__
    return run(args, Driver, __version__)


if __name__ == '__main__':
    raise SystemExit(main())
