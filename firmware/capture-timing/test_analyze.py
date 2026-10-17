"""Offline tests for timestamp association; never connect to hardware."""
import tempfile
import unittest
from pathlib import Path

from analyze import correlate, transitions


def trace(ids):
    events = [dict(id=event, cycles=1000 * i, tick_ms=i, core_hz=1000000)
              for i, event in enumerate(ids)]
    return dict(events=events, event_count=len(events), completed=True,
                image_integrity_matches=True, camera_error=0, errors=0, result=0)


def edges_for(ids):
    edges = [[] for _ in range(6)]
    edges[0] = [(.1, 0), (1., 1)]
    edges[1] = [(.2, 0), (1.1, 1)]
    edges[2] = [(1.099, 0)] + [(1.2 + i * .001, 1 - i % 2) for i in range(len(ids))]
    return edges


class CorrelationTests(unittest.TestCase):
    def test_odd_and_even_event_counts(self):
        for ids in ([2, 3, 40], [2, 3, 30, 40]):
            output = correlate(edges_for(ids), trace(ids))
            self.assertEqual(len(output['events']), len(ids))
            self.assertEqual(output['events'][-1]['pe0_level'], len(ids) % 2)
            self.assertAlmostEqual(output['events'][0]['after_nrst_us'], 200000)

    def test_extra_or_missing_edge_rejected(self):
        for extra in (-1, 1):
            ids = [2, 3, 40]
            edges = edges_for(ids)
            if extra == -1:
                edges[2].pop()
            else:
                edges[2].append((1.25, 0))
            with self.assertRaisesRegex(ValueError, 'ambiguous alignment'):
                correlate(edges, trace(ids))

    def test_multiple_resets_require_trim(self):
        ids = [2, 3, 40]
        edges = edges_for(ids)
        edges[0].insert(0, (.01, 1))
        with self.assertRaisesRegex(ValueError, 'exactly one NRST'):
            correlate(edges, trace(ids))
        self.assertTrue(correlate(edges, trace(ids), after_s=.05)['matched'])

    def test_ram_launch_requires_explicit_boundary(self):
        ids = [2, 3, 40]
        with self.assertRaisesRegex(ValueError, '--after-s'):
            correlate(edges_for(ids), trace(ids), mode='ram')
        output = correlate(edges_for(ids), trace(ids), mode='ram', after_s=1.)
        self.assertIsNone(output['nrst_release_s'])
        self.assertNotIn('after_nrst_us', output['events'][0])

    def test_clock_transition_not_converted_even_if_frequency_fields_equal(self):
        ids = [2, 3, 40]
        output = correlate(edges_for(ids), trace(ids))
        self.assertNotIn('dwt_delta_us', output['events'][1])
        self.assertEqual(output['events'][2]['dwt_delta_us'], 1000)

    def test_pa0_pulse_and_errors_reported_without_claiming_exposure(self):
        ids = [2, 3, 24, 50, 51, 29, 30, 40]
        result = trace(ids)
        result['errors'] = 1
        output = correlate(edges_for(ids), result)
        self.assertEqual(len(output['pa0_pulses']), 1)
        self.assertAlmostEqual(output['pa0_pulses'][0]['width_us'], 1000)
        self.assertTrue(output['pa0_pulses'][0]['rise_after_start_stream'])
        self.assertFalse(output['exposure_qualified'])
        self.assertTrue(any('errors is nonzero' in warning for warning in output['warnings']))

    def test_nominal_clock_disagreement_is_visible(self):
        ids = [2, 3, 40]
        edges = edges_for(ids)
        edges[2][-1] = (1.203, 1)
        output = correlate(edges, trace(ids))
        self.assertAlmostEqual(output['events'][-1]['observed_cycles_per_second'], 500000, delta=.001)
        self.assertTrue(any('over 0.5%' in warning for warning in output['warnings']))

    def test_first_csv_row_is_state_not_transition(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'digital.csv'
            path.write_text('Time [s],Channel 0,Channel 1,Channel 2,Channel 3,Channel 4,Channel 5\n'
                            '0,1,1,1,1,1,1\n.1,1,1,0,1,1,1\n.2,1,1,1,1,1,1\n')
            edges = transitions(path)
            self.assertEqual(edges[0], [])
            self.assertEqual(edges[2], [(.1, 0), (.2, 1)])


if __name__ == '__main__':
    unittest.main()
