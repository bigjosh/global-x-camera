"""Offline command/cleanup guard tests. Never opens USB, serial or JS."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

import record_startup as recorder


class FakeDevice:
    def __init__(self, current, fail_query=False):
        self.current = current
        self.fail_query = fail_query
        self.commands = []

    def query(self, topic, timeout):
        if self.fail_query:
            raise RuntimeError('Disconnected before cleanup read')
        return self.current

    def publish(self, topic, value, timeout):
        self.commands.append((topic, value))
        self.current = value


class CleanupTests(unittest.TestCase):
    def test_aborted_off_never_reenabled(self):
        dev = FakeDevice(0)
        final = recorder.restore_range(dev, 128, lambda *a, **k: None)
        self.assertEqual(final, 0)
        self.assertEqual(dev.commands, [])

    def test_powered_fixed_range_restores_auto(self):
        dev = FakeDevice(1)
        final = recorder.restore_range(dev, 128, lambda *a, **k: None)
        self.assertEqual(final, 128)
        self.assertEqual(dev.commands, [(recorder.RANGE, 128)])

    def test_already_auto_has_no_power_command(self):
        dev = FakeDevice(128)
        self.assertEqual(recorder.restore_range(dev, 128, lambda *a, **k: None), 128)
        self.assertEqual(dev.commands, [])

    def test_unknown_state_does_not_get_power_command(self):
        dev = FakeDevice(0, fail_query=True)
        with self.assertRaises(RuntimeError):
            recorder.restore_range(dev, 128, lambda *a, **k: None)
        self.assertEqual(dev.commands, [])

    def test_pure_cleanup_never_selects_on_from_off(self):
        for initial in (0, 1, 128):
            self.assertEqual(recorder.cleanup_range(initial, 0), 0)
            self.assertIsNone(recorder.cleanup_range(initial, None))


class ArgumentTests(unittest.TestCase):
    def base(self):
        return ['--out', str(recorder.CAMPAIGN/'offline-placeholder')]

    def parse(self, *more):
        with contextlib.redirect_stderr(io.StringIO()):
            return recorder.parse_args(self.base()+list(more))

    def test_default_is_passive(self):
        a = self.parse()
        self.assertEqual(a.mode, 'observe')
        self.assertFalse(a.execute)
        self.assertFalse(recorder.wants_uart(a.mode))

    def test_all_mutations_need_execute_proof_and_current_bounds(self):
        for mode in recorder.MODES[1:]:
            for args in ([], ['--execute'], ['--execute', '--park-proof', 'unused']):
                with self.subTest(mode=mode, args=args), self.assertRaises(SystemExit):
                    self.parse('--mode', mode, *args)
            a = self.parse('--mode', mode, '--execute', '--park-proof', 'unused',
                           '--park-current-min-ma', '10', '--park-current-max-ma', '200')
            self.assertEqual(a.mode, mode)

    def test_normal_cold_needs_no_uart(self):
        self.assertFalse(recorder.wants_uart('cold-normal'))
        self.assertFalse(recorder.wants_train('cold-normal'))

    def test_recovery_modes_select_train(self):
        for mode in recorder.MODES:
            self.assertEqual(recorder.wants_train(mode), mode.endswith('recovery'))

    def test_passive_cannot_change_range(self):
        with self.assertRaises(SystemExit):
            self.parse('--on-range', '1')

    def test_duration_and_byte_budgets(self):
        with self.assertRaises(SystemExit):
            self.parse('--off-seconds', '0')
        with self.assertRaises(SystemExit):
            self.parse('--post-seconds', '60')
        with self.assertRaises(SystemExit):
            self.parse('--max-mib', '64')


class ProofTests(unittest.TestCase):
    def test_exact_fresh_proof_accepted_wrong_or_stale_rejected(self):
        proof = dict(passed=True, prefix_sha256=recorder.PREFIX,
                     context={'PC': 0x3418078C}, halt_requested=True,
                     ram_writes=False, nor_commands=False)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'proof.json'
            path.write_text(json.dumps(proof))
            result = recorder.validate_proof(path)
            self.assertEqual(result['prefix_sha256'], recorder.PREFIX)
            with self.assertRaises(ValueError):
                recorder.validate_proof(path, now=time.time()+601)
            proof['prefix_sha256'] = '99db-old-build'
            path.write_text(json.dumps(proof))
            with self.assertRaises(ValueError):
                recorder.validate_proof(path)


if __name__ == '__main__':
    unittest.main()
