"""Offline invariants for window validity, native alignment and marker selection."""
import unittest
import numpy as np
from analyze_inrush import FS, metrics, select_onset, decode_markers, cycle_metrics


def analog(current, start=0):
    values = np.asarray(current, dtype=np.float32)
    return {'current': (start, values), 'voltage': (start, np.full(len(values), 5, dtype=np.float32)),
            'power': (start, values * 5)}


class AnalysisTests(unittest.TestCase):
    def test_integrals_keep_negative_charge(self):
        report = metrics(analog([2, -1, 0, 3]), 0, 4, 0)
        self.assertTrue(report['valid'])
        self.assertAlmostEqual(report['charge_mC'], .002)
        self.assertAlmostEqual(report['positive_charge_mC'], .0025)
        self.assertAlmostEqual(report['negative_charge_mC'], -.0005)
        self.assertAlmostEqual(report['energy_mJ'], .010)
        self.assertEqual(report['current_above_A']['1']['episodes'], 2)

    def test_native_sample_ids_not_array_indices(self):
        signals = analog([1, 2, 3, 4], 100)
        signals['voltage'] = (99, np.array([99, 4, 5, 6, 7], dtype=np.float32))
        report = metrics(signals, 100, 103, 100)
        self.assertTrue(report['valid'])
        self.assertEqual(report['voltage_mean'], 5)
        self.assertEqual(report['native_peak_unqualified']['source_voltage_V'], 6)

    def test_negative_slice_never_wraps(self):
        report = metrics(analog([1, 2, 3], 100), 99, 101, 100)
        self.assertFalse(report['valid'])
        self.assertNotIn('energy_mJ', report)

    def test_nan_invalidates_integral(self):
        report = metrics(analog([1, np.nan, 3]), 0, 3, 0)
        self.assertFalse(report['valid'])
        self.assertNotIn('charge_mC', report)
        self.assertEqual(report['streams']['current']['nonfinite_samples'], 1)

    def test_variable_dwell_uses_observed_range_on(self):
        for before in (5000, 45000):
            values = np.zeros(before + 120000, dtype=np.float32)
            values[before + 8:] = .1
            signals = analog(values, 100)
            rng = np.full(len(values) - 20, 7, dtype=np.uint8)
            rng[before - 20:] = 0
            signals['current_range'] = (120, rng)
            onset, report = select_onset(signals)
            self.assertEqual(onset, 100 + before + 8)
            self.assertTrue(report['prior_1ms_abs_mean_below_100uA'])

    def test_multiple_onsets_need_selection(self):
        values = np.zeros(140000, dtype=np.float32)
        values[5008:7000] = .1
        values[80008:] = .1
        signals = analog(values)
        rng = np.full(len(values), 7, dtype=np.uint8)
        rng[5000:7000] = 0
        rng[80000:] = 0
        signals['current_range'] = (0, rng)
        with self.assertRaisesRegex(ValueError, 'Multiple onset'):
            select_onset(signals)
        onset, _ = select_onset(signals, index=1)
        self.assertEqual(onset, 80008)

    def test_no_marker_does_not_invent_cycle(self):
        signals = analog(np.zeros(10000))
        marker = decode_markers(signals, 2000)
        self.assertFalse(marker['unique_complete_train'])
        self.assertFalse(cycle_metrics(signals, marker, 2000)['available'])

    def test_eleven_marker_train_allows_overlap_order(self):
        signals = analog(np.full(10000, .1))
        gpio = np.zeros(10000, dtype=np.uint8)
        ids = [1, 2, 4, 3, 11, 5, 6, 7, 8, 9, 10]
        for pos, marker in enumerate(ids):
            start = 1000 + pos * 200
            gpio[start:start + 4 * marker + 1] = 1
        signals['gpi0'] = (0, gpio)
        marker = decode_markers(signals, 0)
        self.assertTrue(marker['unique_complete_train'])
        self.assertEqual([x['id'] for x in marker['events']], ids)

    def test_invalid_precedence_rejected(self):
        signals = analog(np.full(10000, .1))
        gpio = np.zeros(10000, dtype=np.uint8)
        for pos, marker in enumerate([1, 2, 4, 11, 3, 5, 6, 7, 8, 9, 10]):
            start = 1000 + pos * 200
            gpio[start:start + 4 * marker + 1] = 1
        signals['gpi0'] = (0, gpio)
        self.assertFalse(decode_markers(signals, 0)['unique_complete_train'])


if __name__ == '__main__':
    unittest.main()
