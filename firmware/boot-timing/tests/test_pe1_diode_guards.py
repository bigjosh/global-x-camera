"""Offline guards for the diode smoke helper; never imports an instrument API."""
from pathlib import Path
from contextlib import redirect_stdout
import io
import json
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_pe1_diode as smoke


class DiodeSmokeGuards(unittest.TestCase):
    class HaltBench:
        """Each connection closes with the core running, as observed on bench."""
        def __init__(self, output, *, halted_dhcsr=0x00130003, pc=0x34302B0C):
            self.output, self.calls, self.uploads = output, [], []
            self.halted_dhcsr, self.pc = halted_dhcsr, pc
            self.values = {smoke.MEMENR: 0xF, smoke.AHB4ENR: 16,
                           smoke.AHB4RSTR: 0, smoke.MODER: 12, smoke.PUPDR: 0,
                           smoke.DHCSR: 0x01110000}
        def bytes(self, address, length):
            if address == 0x343F0000:
                words = [0] * 64
                words[0], words[1], words[5] = 0x43545031, 40, 1
                return struct.pack('<64I', *words)
            if address == 0x34300000:
                return bytes(length)  # Receiver checker is mocked for control-flow tests.
            return struct.pack('<I', self.values[address])
        def upload(self, address, length, name):
            self.uploads.append((address, length))
            return self.bytes(address, length)
        def call(self, *args, **kwargs):
            self.calls.append(args)
            if args[0] != '-halt':
                raise AssertionError('Post-check operation must halt in its own command')
            if '-u' in args:
                index = args.index('-u')
                address, length, path = int(args[index+1], 16), int(args[index+2]), args[index+3]
                data = struct.pack('<I', self.halted_dhcsr) if address == smoke.DHCSR else self.bytes(address, length)
                Path(path).write_bytes(data)
            if '-w32' in args:
                index = args.index('-w32')
                self.values[int(args[index+1], 16)] = int(args[index+2], 16)
            return f'PC = 0x{self.pc:08X}\nXPSR = 0x01000000\nCONTROL = 0x0C\nFAULTMASK = 0x00\n'

    def test_halt_and_dhcsr_are_verified_in_one_connection_and_each_access_rehalts(self):
        with tempfile.TemporaryDirectory() as directory:
            bench = self.HaltBench(Path(directory))
            target = smoke.Target(bench)
            with patch.object(smoke, 'check_receiver'):
                initial = target.check_and_halt()
            first = bench.calls[0]
            self.assertEqual(first[:4], ('-halt', '-u', hex(smoke.DHCSR), '4'))
            self.assertEqual(first[-1], '-coreReg')
            self.assertEqual(initial['dhcsr_within_halt_command'], 0x00130003)
            self.assertTrue(initial['halt_verified_in_command'])
            self.assertEqual(initial['persistent_halt_after_disconnect'], 'not_guaranteed')
            uploads_before = len(bench.uploads)
            target.write_field(smoke.PUPDR, 1, 'test-pull')
            self.assertEqual(len(bench.uploads), uploads_before)
            self.assertTrue(all(call[0] == '-halt' for call in bench.calls))
            self.assertEqual(bench.values[smoke.PUPDR], 4)
            # Explicit final-running check must not accidentally halt again.
            self.assertEqual(target.read(smoke.DHCSR, 'running', halt=False), 0x01110000)
            self.assertEqual(len(bench.uploads), uploads_before + 1)

    def test_same_command_halt_bit_and_exact_idle_pc_are_required_before_mutation(self):
        for bad in ({'halted_dhcsr': 0x01110000}, {'pc': 0x34301000}):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as directory:
                bench = self.HaltBench(Path(directory), **bad)
                target = smoke.Target(bench)
                with patch.object(smoke, 'check_receiver'), self.assertRaisesRegex(ValueError, 'v25 idle'):
                    target.check_and_halt()
                self.assertFalse(target.halt_verified_in_command)
                self.assertFalse(target.modified)
                self.assertEqual(len(bench.calls), 1)
                with self.assertRaises(ValueError):
                    target.write_field(smoke.PUPDR, 1, 'must-refuse')

    def test_disabled_sram_prevents_any_trace_receiver_or_core_access(self):
        class Bench:
            def __init__(self, enabled):
                self.enabled, self.uploads = enabled, []
            def upload(self, address, length, name):
                self.uploads.append((address, length))
                if address != smoke.MEMENR:
                    raise AssertionError('Unexpected high-SRAM or other target access')
                return struct.pack('<I', self.enabled)
            def call(self, *args, **kwargs):
                raise AssertionError('No halt or target write allowed with disabled SRAM')

        # Reject a missing bank even if all unrelated enable bits are set.
        for enabled in (0, 0xFFFFFFFE, 0xFFFFFFFD, 0xFFFFFFFB, 0xFFFFFFF7):
            with self.subTest(enabled=hex(enabled)):
                bench = Bench(enabled)
                target = smoke.Target(bench)
                with self.assertRaisesRegex(ValueError, 'AXISRAM3..6 must already be enabled'):
                    target.check_and_halt()
                self.assertEqual(bench.uploads, [(0x5602824C, 4)])
                self.assertFalse(target.halt_attempted)
                self.assertFalse(target.modified)

    def test_memory_is_rechecked_before_receiver_after_valid_trace(self):
        class Bench:
            def __init__(self):
                self.enables, self.uploads = iter((0xF, 0x7)), []
            def upload(self, address, length, name):
                self.uploads.append((address, length))
                if address == smoke.MEMENR:
                    return struct.pack('<I', next(self.enables))
                if address == 0x343F0000:
                    words = [0] * 64
                    words[0], words[1], words[5] = 0x43545031, 40, 1
                    return struct.pack('<64I', *words)
                raise AssertionError('Receiver read must not occur after a bank is disabled')
            def call(self, *args, **kwargs):
                raise AssertionError('No core or register mutation permitted')

        bench = Bench()
        target = smoke.Target(bench)
        with self.assertRaisesRegex(ValueError, 'RCC_MEMENR=0x00000007'):
            target.check_and_halt()
        self.assertEqual(bench.uploads, [(smoke.MEMENR, 4), (0x343F0000, 256),
                                         (smoke.MEMENR, 4)])
        self.assertFalse(target.halt_attempted)

    def test_source_requires_finite_fresh_complete_window(self):
        good = {'age_s': 0.1, 'voltage': {'min': 4.5, 'avg': 4.8, 'max': 4.9}}
        self.assertIs(smoke.check_supply(good), good)
        for bad in (None, {'age_s': 3, 'voltage': good['voltage']},
                    {'age_s': .1, 'voltage': {'min': 0, 'avg': 4.8, 'max': 4.9}},
                    {'age_s': .1, 'voltage': {'min': 4.5, 'avg': float('nan'), 'max': 4.9}}):
            with self.assertRaises(ValueError):
                smoke.check_supply(bad)

    def test_shared_supply_requires_isolation_and_idle_routes(self):
        settings = {smoke.EXTIO_TOPIC: 3300, smoke.GPO_TOPICS[0]: 0, smoke.GPO_TOPICS[1]: 0}
        routes = {key: 0 for key in smoke.ROUTES}
        smoke.check_settings(settings, routes, change_supply=True, other_disconnected=True)
        with self.assertRaises(ValueError):
            smoke.check_settings(settings, routes, change_supply=True, other_disconnected=False)
        for route in smoke.ROUTES:
            with self.assertRaises(ValueError):
                smoke.check_settings(settings, dict(routes, **{route: 1}),
                                     change_supply=True, other_disconnected=True)
        with self.assertRaises(ValueError):
            smoke.check_settings(dict(settings, **{smoke.GPO_TOPICS[1]: 1}), routes,
                                 change_supply=True, other_disconnected=True)

    def test_only_pe1_field_changes(self):
        for value in (0, 0xFFFFFFFF, 0xA55AA55A):
            for setting in range(4):
                changed = smoke.field(value, setting)
                self.assertEqual(changed & ~12, value & ~12)
                self.assertEqual((changed >> 2) & 3, setting)

    def test_matrix_stops_at_first_failure(self):
        class Target:
            calls = []
            def write_field(self, *args): self.calls.append(args)
            def read(self, *args): return 2  # Incorrect first active pull-up/low.
        target, samples, outputs = Target(), [], []
        with patch.object(smoke.time, 'sleep'):
            with self.assertRaises(RuntimeError):
                smoke.run_matrix(target, lambda *args: outputs.append(args), lambda: None,
                                 samples.append, smoke.ACTIVE_MATRIX, 3300)
        self.assertEqual(len(samples), 1)
        self.assertEqual(len(target.calls), 1)
        self.assertEqual(outputs, [(smoke.GPO_TOPICS[0], 0)])
        self.assertFalse(samples[0]['passed'])

    def test_matrix_covers_sink_release_and_non_sourcing(self):
        self.assertEqual(smoke.ACTIVE_MATRIX, ((1, 0, 0), (1, 1, 1), (2, 1, 0), (2, 0, 0)))
        self.assertEqual(set(smoke.OFF_MATRIX), {(1, 0, 1), (2, 0, 0), (1, 1, 1), (2, 1, 0)})


class SessionRestorationTests(unittest.TestCase):
    def exercise(self, *, voltage=4.8, bad_diode=False, publish_failure=False,
                 target_restore_failure=False, off_test=False):
        class Device:
            def __init__(self):
                self.values = {smoke.EXTIO_TOPIC: 3300, smoke.GPO_TOPICS[0]: 1,
                               smoke.GPO_TOPICS[1]: 0, smoke.RANGE_TOPIC: 128,
                               smoke.STATS_CTRL: 0, **{t: 0 for t in smoke.ROUTES}}
                self.initial = dict(self.values)
                self.commands = []
                self.fail_once = publish_failure
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def device_paths(self): return ['u/js110/fake']
            def open(self, *args, **kwargs): return self
            def query(self, topic, **kwargs): return self.values[topic]
            def publish(self, topic, value, **kwargs):
                self.commands.append((topic, value))
                self.values[topic] = value
                if self.fail_once and topic == smoke.GPO_TOPICS[0] and value == 0:
                    self.fail_once = False
                    raise RuntimeError('USB error after setting changed')
            def subscribe(self, *args): pass
            def unsubscribe(self, *args, **kwargs): pass
        dev = Device()

        class Stats:
            sequence = 0
            def receive(self, *args): pass
            def snapshot(self):
                self.sequence += 1
                return {'sequence': self.sequence, 'age_s': .01,
                        'voltage': {'min': voltage, 'avg': voltage, 'max': voltage}}

        class Bench:
            def __init__(self, *args): self.calls = []
            def call(self, *args, **kwargs): self.calls.append(args)

        class Target:
            def __init__(self, bench):
                self.bench = bench
                self.halt_attempted = False
                self.halt_verified_in_command = False
                self.pull = 0
                self.restored = False
            def check_and_halt(self):
                self.halt_attempted = True
                self.halt_verified_in_command = True
                return {'moder': 3, 'pupdr': 0}
            def write_field(self, address, setting, name):
                if address == smoke.PUPDR: self.pull = setting
            def read(self, address, name, **kwargs):
                if address != smoke.IDR: return 0
                if bad_diode: return 2
                if dev.values[smoke.EXTIO_TOPIC] == 0: return 2 if self.pull == 1 else 0
                return 2 if self.pull == 1 and dev.values[smoke.GPO_TOPICS[0]] else 0
            def restore(self):
                self.restored = True
                return ['simulated target restoration error'] if target_restore_failure else []

        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(out=Path(directory)/'result', device='u/js110/fake',
                                   other_gpio_disconnected=True, test_supply_off=off_test)
            with patch.object(smoke, 'Statistics', Stats), patch.object(smoke, 'Bench', Bench), \
                 patch.object(smoke, 'Target', Target), patch.object(smoke.time, 'sleep'), \
                 redirect_stdout(io.StringIO()):
                code = smoke.run(args, lambda: dev, 'offline-fake')
            result = json.loads((args.out/'result.json').read_text())
        self.assertFalse(any(topic in (smoke.GPO_TOPICS[1], smoke.RANGE_TOPIC)
                             for topic, _ in dev.commands))
        self.assertEqual(dev.values, dev.initial)
        return code, result, dev

    def test_complete_active_and_off_matrices_restore_and_resume(self):
        code, result, _ = self.exercise(off_test=True)
        self.assertEqual(code, 0)
        self.assertTrue(result['core_resumed'])
        self.assertEqual(len(result['samples']), 8)

    def test_source_zero_prevents_halt_and_pin_output_changes(self):
        code, result, dev = self.exercise(voltage=0)
        self.assertEqual(code, 1)
        self.assertFalse(result['core_halt_attempted'])
        self.assertFalse(any(t in (smoke.EXTIO_TOPIC, *smoke.GPO_TOPICS) for t, _ in dev.commands))

    def test_first_mismatch_restores_but_does_not_resume(self):
        code, result, _ = self.exercise(bad_diode=True, off_test=True)
        self.assertEqual(code, 1)
        self.assertEqual(len(result['samples']), 1)
        self.assertFalse(result['core_resumed'])

    def test_partial_usb_success_is_restored_without_resuming(self):
        code, result, _ = self.exercise(publish_failure=True)
        self.assertEqual(code, 1)
        self.assertFalse(result['core_resumed'])
        self.assertFalse(result['restore_errors'])

    def test_failed_target_restore_prevents_resume_but_js_restores(self):
        code, result, _ = self.exercise(target_restore_failure=True)
        self.assertEqual(code, 1)
        self.assertFalse(result['core_resumed'])
        self.assertTrue(result['restore_errors'])


if __name__ == '__main__':
    unittest.main()
