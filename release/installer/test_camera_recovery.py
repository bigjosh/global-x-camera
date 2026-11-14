"""Offline serial mocks and recorded-context regressions; no hardware access."""
import copy
import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import camera_recovery as recovery


ASSETS = Path(__file__).resolve().parent / 'assets' / 'profiles'
# Exact November 13 D8 park-after-knobs/result.json values. Changing the
# prefix to r2 below tests compatible guard/context handling, not r2 hardware.
RECORDED_GUARD = [
    1380405297, 1, 24, 3, 1, 262145, 400000000, 40000,
    11, 40159, 40148, 153, 2, 4294954993, 4100, 270424,
    17825792, 2147483649, 0, 0, 1, 3025253376, 180, 2,
]
RECORDED_VCP = [
    1448100657, 1, 32, 262150, 400000000, 40000, 1000000,
    2400, 5200, 100, 1600, 3, 871, 40159, 20, 9, 0, 9,
    2712, 1136, 1, 13695, 0, 0, 2, 153, 0, 0, 0, 0, 0, 0,
]
RECORDED_CONTEXT = dict(PC=0x3418078C, XPSR=1627389952,
                        PRIMASK=1, FAULTMASK=0, CONTROL=0)


def packed(words):
    return struct.pack('<' + 'I' * len(words), *words)


class FakeTransport:
    def __init__(self, profile='d8-fixed'):
        profiles = recovery.load_profiles(ASSETS)
        self.code = next(code for p, code in profiles if p['id'] == profile)
        self.memory = {
            'recovery-status': packed(RECORDED_GUARD),
            'vcp-status': packed(RECORDED_VCP),
            'live-prefix': self.code.ljust(max(len(code) for _, code in profiles), b'\xff'),
            'ccr': packed([513]), 'fpccr': packed([3221225476]),
            'ahb5enr': packed([0x2020]), 'ahb5rstr': packed([0]),
            'xspi-sr': packed([2]),
            'recovery-status-rechecked': packed(RECORDED_GUARD),
            'vcp-status-rechecked': packed(RECORDED_VCP),
        }
        self.context = dict(RECORDED_CONTEXT)
        self.events, self.calls, self.uploads = [], [], []

    def call(self, *args, **kwargs):
        self.calls.append(args)
        if args != ('-halt', '-coreReg'):
            raise AssertionError(f'Unexpected hardware command {args}')
        return '\n'.join(f'{key} = 0x{value:08X}' for key, value in self.context.items())

    def upload(self, address, length, label):
        self.uploads.append((address, length, label))
        return self.memory[label]

    def log(self, event, **fields):
        self.events.append((event, fields))

    def alter(self, label, fields, name, value):
        values = list(struct.unpack('<' + 'I' * len(fields), self.memory[label]))
        values[fields.index(name)] = value
        self.memory[label] = packed(values)


class ParkTests(unittest.TestCase):
    def test_both_reviewed_prefixes_match_the_recorded_guard(self):
        for identity in ('d8-fixed', 'r2-knobs'):
            with self.subTest(identity=identity):
                transport = FakeTransport(identity)
                profile = recovery.verify_park(transport, ASSETS)
                self.assertEqual(profile['id'], identity)
                self.assertEqual(transport.calls, [('-halt', '-coreReg')])
                self.assertEqual(transport.events[-1][0], 'recovery_verified')
                self.assertEqual(transport.events[-1][1]['vcp_status']['good_pulses'], 9)

    def test_unknown_live_code_never_halts(self):
        t = FakeTransport()
        t.memory['live-prefix'] = b'X' + t.memory['live-prefix'][1:]
        with self.assertRaisesRegex(ValueError, 'no halt'):
            recovery.verify_park(t, ASSETS)
        self.assertFalse(t.calls)

    def test_truncated_reads_never_halt(self):
        for label in ('recovery-status', 'vcp-status', 'live-prefix'):
            with self.subTest(label=label):
                t = FakeTransport()
                t.memory[label] = t.memory[label][:-1]
                with self.assertRaisesRegex(ValueError, 'Incomplete'):
                    recovery.verify_park(t, ASSETS)
                self.assertFalse(t.calls)

    def test_bad_guard_or_pulse_proof_never_halts(self):
        cases = [
            ('recovery-status', recovery.FIELDS, 'state', 2),
            ('recovery-status', recovery.FIELDS, 'reason', 3),
            ('recovery-status', recovery.FIELDS, 'elapsed_cycles', 39999),
            ('recovery-status', recovery.FIELDS, 'sample_cycle', 40160),
            ('recovery-status', recovery.FIELDS, 'polls', 100000),
            ('recovery-status', recovery.FIELDS, 'pupdr', 4),
            ('recovery-status', recovery.FIELDS, 'dbgcr', 0),
            ('vcp-status', recovery.VCP_FIELDS, 'max_train', 2),
            ('vcp-status', recovery.VCP_FIELDS, 'good_pulses', 2),
            ('vcp-status', recovery.VCP_FIELDS, 'request_cycle', 40011),
            ('vcp-status', recovery.VCP_FIELDS, 'source_bits', 1),
            ('vcp-status', recovery.VCP_FIELDS, 'reserved30', 1),
        ]
        for label, fields, key, value in cases:
            with self.subTest(label=label, key=key):
                t = FakeTransport()
                t.alter(label, fields, key, value)
                with self.assertRaises(ValueError):
                    recovery.verify_park(t, ASSETS)
                self.assertFalse(t.calls)

    def test_gpio_only_recovery_not_accepted_as_uart_proof(self):
        t = FakeTransport()
        for key, value in dict(reserved=1, idr=0).items():
            t.alter('recovery-status', recovery.FIELDS, key, value)
        for key, value in dict(source_bits=1, request=0, request_cycle=0,
                               max_train=0, good_pulses=0, edges=0).items():
            t.alter('vcp-status', recovery.VCP_FIELDS, key, value)
        with self.assertRaisesRegex(ValueError, 'No observed UART'):
            recovery.verify_park(t, ASSETS)
        self.assertFalse(t.calls)

    def test_invalid_core_state_never_reads_xspi(self):
        cases = [('PC', 0x34300000), ('CONTROL', 2), ('PRIMASK', 0),
                 ('FAULTMASK', 1), ('XPSR', 0x01000003), ('XPSR', 0)]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                t = FakeTransport()
                t.context[key] = value
                with self.assertRaisesRegex(ValueError, 'context'):
                    recovery.verify_park(t, ASSETS)
                self.assertNotIn('xspi-sr', [label for _, _, label in t.uploads])
        t = FakeTransport()
        del t.context['PC']
        with self.assertRaises(ValueError):
            recovery.verify_park(t, ASSETS)

    def test_cache_fpu_and_xspi_gates(self):
        for label, value in [('ccr', 0x10000), ('ccr', 0x20000), ('fpccr', 1),
                             ('ahb5enr', 0x20), ('ahb5rstr', 0x2000),
                             ('xspi-sr', 0x20), ('xspi-sr', 0x100)]:
            with self.subTest(label=label, value=value):
                t = FakeTransport()
                t.memory[label] = packed([value])
                with self.assertRaises(ValueError):
                    recovery.verify_park(t, ASSETS)
                if label != 'xspi-sr':
                    self.assertNotIn('xspi-sr', [key for _, _, key in t.uploads])

    def test_post_halt_records_must_remain_exactly_stable(self):
        t = FakeTransport()
        # A changed yet internally valid clock record must still be rejected.
        t.alter('recovery-status-rechecked', recovery.FIELDS, 'begin_cycle', 12)
        t.alter('recovery-status-rechecked', recovery.FIELDS, 'sample_cycle', 40160)
        with self.assertRaisesRegex(ValueError, 'status changed'):
            recovery.verify_park(t, ASSETS)
        t = FakeTransport()
        t.alter('vcp-status-rechecked', recovery.VCP_FIELDS, 'last_low', 2713)
        with self.assertRaisesRegex(ValueError, 'proof changed'):
            recovery.verify_park(t, ASSETS)

    def test_timer_wrap_preserves_valid_relative_deadline(self):
        guard = dict(zip(recovery.FIELDS, RECORDED_GUARD))
        vcp = dict(zip(recovery.VCP_FIELDS, RECORDED_VCP))
        delta = 0xFFFFFF00
        for key in ('begin_cycle', 'sample_cycle'):
            guard[key] = (guard[key] + delta) & 0xFFFFFFFF
        for key in ('first_cycle', 'last_cycle', 'request_cycle'):
            vcp[key] = (vcp[key] + delta) & 0xFFFFFFFF
        recovery.validate_status([guard[key] for key in recovery.FIELDS])
        recovery.validate_vcp_status([vcp[key] for key in recovery.VCP_FIELDS], guard)


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'profiles'
        shutil.copytree(ASSETS, self.root)
        self.document = json.loads((self.root / 'profiles.json').read_text())

    def save(self):
        (self.root / 'profiles.json').write_text(json.dumps(self.document))

    def test_manifest_is_not_its_own_authority(self):
        self.document['profiles'][0]['sector0_sha256'] = '0' * 64
        self.save()
        t = FakeTransport()
        with self.assertRaisesRegex(ValueError, 'reviewed'):
            recovery.verify_park(t, self.root)
        self.assertFalse(t.uploads)
        self.assertFalse(t.calls)

    def test_prefix_tampering(self):
        p = self.root / self.document['profiles'][0]['prefix_file']
        p.write_bytes(p.read_bytes()[:-1] + b'X')
        with self.assertRaisesRegex(ValueError, 'bytes differ'):
            recovery.load_profiles(self.root)

    def test_path_escape_and_duplicates_rejected(self):
        self.document['profiles'][0]['prefix_file'] = '../outside.bin'
        self.save()
        with self.assertRaisesRegex(ValueError, 'escapes'):
            recovery.load_profiles(self.root)
        self.document = json.loads((ASSETS / 'profiles.json').read_text())
        self.document['profiles'].append(copy.deepcopy(self.document['profiles'][0]))
        self.save()
        with self.assertRaisesRegex(ValueError, 'reviewed'):
            recovery.load_profiles(self.root)


def port(device='/dev/cu.usbmodem123', serial='ST123', vid=0x0483, pid=0x3754):
    return SimpleNamespace(device=device, serial_number=serial, vid=vid, pid=pid)


class PortTests(unittest.TestCase):
    def test_binds_full_identity_and_ignores_other_usb_devices(self):
        ports = [port(), port('/dev/cu.other', 'OTHER'), port('/dev/cu.ptp', pid=123)]
        self.assertEqual(recovery.select_serial_port('ST123', ports=ports),
                         '/dev/cu.usbmodem123')
        with self.assertRaises(RuntimeError):
            recovery.select_serial_port('ST123', '/dev/cu.other', ports)

    def test_prefers_matching_callout_alias_but_rejects_two_interfaces(self):
        ports = [port(), port('/dev/tty.usbmodem123')]
        self.assertEqual(recovery.select_serial_port('ST123', ports=ports), ports[0].device)
        ports.append(port('/dev/cu.usbmodem456'))
        with self.assertRaises(RuntimeError):
            recovery.select_serial_port('ST123', ports=ports)
        self.assertEqual(recovery.select_serial_port('ST123', ports[0].device, ports), ports[0].device)

    def test_missing_serial_or_ambiguous_port_fails(self):
        with self.assertRaises(ValueError):
            recovery.select_serial_port('', ports=[port()])
        with self.assertRaises(RuntimeError):
            recovery.select_serial_port('ST123', ports=[port(), port()])
        with self.assertRaises(RuntimeError):
            recovery.select_serial_port('ST123', ports=[])


class FakeUART:
    def __init__(self, write_result=32768, write_error=None, paced=False):
        self.is_open = False
        self.events = []
        self.write_result, self.write_error = write_result, write_error
        self.paced = paced
        self.started = threading.Event()
        self.cancelled = threading.Event()
        self._break = False

    @property
    def break_condition(self):
        return self._break

    @break_condition.setter
    def break_condition(self, value):
        self._break = value
        self.events.append(('break', value))

    def open(self):
        self.is_open = True
        self.events.append(('open',))

    def write(self, data):
        self.events.append(('write', data))
        self.started.set()
        if self.paced:
            self.cancelled.wait(0.005)
        if self.write_error:
            raise self.write_error
        return self.write_result

    def cancel_write(self):
        self.events.append(('cancel',))
        self.cancelled.set()

    def reset_output_buffer(self):
        self.events.append(('purge',))

    def close(self):
        self.events.append(('close',))
        self.is_open = False


class SerialTests(unittest.TestCase):
    def setUp(self):
        self.logs = []
        self.log = lambda event, **fields: self.logs.append((event, fields))

    def test_exact_measured_request_and_cleanup(self):
        uart = FakeUART()
        with patch.object(recovery, '_serial', return_value=uart), \
                patch.object(recovery.time, 'sleep') as sleep:
            recovery.request_recovery('PORT', self.log)
        self.assertEqual([e[1] for e in uart.events if e[0] == 'write'], [b'\xc0' * 32768])
        self.assertEqual([e[1] for e in uart.events if e[0] == 'break'], [True, False])
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [.3, .023, .1, .75])
        self.assertFalse(uart.is_open)
        self.assertEqual(self.logs[-1][0], 'uart_closed')

    def test_failed_send_does_not_reset_and_closes(self):
        for uart in [FakeUART(write_result=17), FakeUART(write_error=OSError('gone'))]:
            with self.subTest(uart=uart), patch.object(recovery, '_serial', return_value=uart), \
                    patch.object(recovery.time, 'sleep'):
                with self.assertRaises(RuntimeError):
                    recovery.request_recovery('PORT', self.log)
                self.assertFalse(uart.is_open)
                self.assertFalse(any(e[0] == 'break' for e in uart.events))

    def test_normal_reset_never_transmits_data(self):
        uart = FakeUART()
        with patch.object(recovery, '_serial', return_value=uart), patch.object(recovery.time, 'sleep'):
            recovery.normal_reset('PORT', self.log)
        self.assertFalse(any(e[0] == 'write' for e in uart.events))
        self.assertEqual([e[1] for e in uart.events if e[0] == 'break'], [True, False])
        self.assertFalse(uart.is_open)

    def test_serial_config_is_lazy_and_disables_flow_control(self):
        uart = FakeUART()
        module = SimpleNamespace(Serial=lambda: uart, EIGHTBITS=8,
                                 PARITY_NONE='N', STOPBITS_ONE=1)
        with patch.dict(sys.modules, {'serial': module}):
            self.assertIs(recovery._serial('PORT'), uart)
        self.assertEqual((uart.baudrate, uart.bytesize, uart.parity, uart.stopbits),
                         (1000000, 8, 'N', 1))
        self.assertFalse(uart.rts or uart.dtr or uart.xonxoff or uart.rtscts or uart.dsrdtr)
        self.assertFalse(uart.is_open)

    def test_stream_keeps_transmitting_until_exit_without_reset(self):
        uart = FakeUART(paced=True)
        with patch.object(recovery, '_serial', return_value=uart):
            with recovery.RecoveryStream('PORT', self.log, max_duration=1) as stream:
                self.assertTrue(uart.started.wait(1))
                stream.check()
            self.assertFalse(stream.worker.is_alive())
            with self.assertRaisesRegex(RuntimeError, 'not open'):
                stream.check()
        self.assertFalse(any(e[0] == 'break' for e in uart.events))
        self.assertFalse(uart.is_open)
        self.assertGreater(stream.bytes_written, 0)
        self.assertIn('uart_power_on_stream_armed', [event for event, _ in self.logs])

    def test_stream_exception_or_timeout_releases_port(self):
        uart = FakeUART(write_error=OSError('lost'))
        with patch.object(recovery, '_serial', return_value=uart):
            with self.assertRaisesRegex(RuntimeError, 'stream failed'):
                with recovery.RecoveryStream('PORT', self.log):
                    self.fail('A failed initial write must not enter the context')
        self.assertFalse(uart.is_open)
        uart = FakeUART(paced=True)
        with patch.object(recovery, '_serial', return_value=uart):
            with recovery.RecoveryStream('PORT', self.log, max_duration=1) as stream:
                stream.deadline = time.monotonic() - 1
                with self.assertRaises(TimeoutError):
                    stream.check()
        self.assertFalse(uart.is_open)
        self.assertFalse(any(e[0] == 'break' for e in uart.events))

    def test_initial_partial_send_fails_before_context_and_never_claims_armed(self):
        uart = FakeUART(write_result=12)
        with patch.object(recovery, '_serial', return_value=uart):
            with self.assertRaisesRegex(RuntimeError, 'stream failed'):
                with recovery.RecoveryStream('PORT', self.log):
                    self.fail('Partial first write must prevent context entry')
        self.assertFalse(uart.is_open)
        self.assertNotIn('uart_power_on_stream_armed', [event for event, _ in self.logs])
        self.assertFalse(any(e[0] == 'break' for e in uart.events))

    def test_initial_queue_timeout_cancels_and_joins_sender(self):
        uart = FakeUART()
        def blocked_write(data):
            uart.started.set()
            uart.cancelled.wait(1)
            return 0
        uart.write = blocked_write
        stream = recovery.RecoveryStream('PORT', self.log)
        def timed_out_wait(seconds):
            self.assertEqual(seconds, 3)
            self.assertTrue(uart.started.wait(1))
            return False
        with patch.object(recovery, '_serial', return_value=uart), \
                patch.object(stream._ready, 'wait', side_effect=timed_out_wait):
            with self.assertRaisesRegex(TimeoutError, 'not queued'):
                with stream:
                    self.fail('Timed-out first write must prevent context entry')
        self.assertFalse(uart.is_open)
        self.assertFalse(stream.worker.is_alive())
        self.assertTrue(uart.cancelled.is_set())
        self.assertFalse(any(e[0] == 'break' for e in uart.events))

    def test_interruption_while_break_is_asserted_releases_reset(self):
        uart = FakeUART()
        with patch.object(recovery, '_serial', return_value=uart), \
                patch.object(recovery.time, 'sleep', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                recovery.normal_reset('PORT', self.log)
        self.assertFalse(uart.is_open)
        self.assertEqual([e[1] for e in uart.events if e[0] == 'break'], [True, False])

    def test_positive_wait_arms_without_break(self):
        uart = FakeUART(paced=True)
        with patch.object(recovery, '_serial', return_value=uart):
            recovery.request_recovery('PORT', self.log, wait_for_power=.015)
        self.assertFalse(uart.is_open)
        self.assertFalse(any(e[0] == 'break' for e in uart.events))
        self.assertIn('uart_power_on_wait_complete', [name for name, _ in self.logs])

    def test_stream_cleanup_on_caller_exception(self):
        uart = FakeUART(paced=True)
        with patch.object(recovery, '_serial', return_value=uart):
            with self.assertRaisesRegex(ValueError, 'caller'):
                with recovery.RecoveryStream('PORT', self.log) as stream:
                    self.assertTrue(uart.started.wait(1))
                    raise ValueError('caller')
        self.assertFalse(stream.worker.is_alive())
        self.assertFalse(uart.is_open)

    def test_cleanup_failure_still_closes_and_is_reported(self):
        uart = FakeUART()
        def failed_cancel():
            raise OSError('cancel failed')
        uart.cancel_write = failed_cancel
        with patch.object(recovery, '_serial', return_value=uart), \
                patch.object(recovery.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'cleanup failed'):
                recovery.normal_reset('PORT', self.log)
        self.assertFalse(uart.is_open)
        self.assertIn(('break', False), uart.events)
        self.assertTrue(self.logs[-1][1]['cleanup_errors'])

    def test_unbounded_or_negative_wait_rejected_before_serial_open(self):
        with patch.object(recovery, '_serial') as factory:
            for value in (-1, float('inf'), float('nan')):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    recovery.request_recovery('PORT', self.log, wait_for_power=value)
                with self.subTest(value=value), self.assertRaises(ValueError):
                    recovery.RecoveryStream('PORT', self.log, max_duration=value)
            factory.assert_not_called()


if __name__ == '__main__':
    unittest.main()
