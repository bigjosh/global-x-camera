"""Offline guards for the diode smoke helper; never imports an instrument API."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_pe1_diode as smoke


class DiodeSmokeGuards(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
