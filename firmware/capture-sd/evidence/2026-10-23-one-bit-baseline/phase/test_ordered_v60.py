"""Offline rejection tests; do not access hardware or alter raw evidence."""
import json
from pathlib import Path
import unittest
from ordered_v60 import analyze, infer_storage, verify_save

HERE = Path(__file__).resolve().parent


def fixture():
    edges = []
    for index, event in enumerate(range(4, 10)):
        edges.extend([1+index*.1, 1+index*.1+event*.5e-6])
    def channel(level, transitions):
        return dict(initial_state=level, begin_s=0., end_s=3., transitions=transitions)
    return {0: channel(1, []), 1: channel(0, edges), 4: channel(1, []), 6: channel(1, [])}


class Tests(unittest.TestCase):
    def test_storage_inference_does_not_qualify_widths(self):
        result = infer_storage(fixture())
        self.assertFalse(result['width_qualification'])
        self.assertEqual([e['inferred_event_id'] for e in result['events']], list(range(4, 10)))
        self.assertTrue(all(e['assignment_basis'] == 'inferred from source call order'
                            for e in result['events']))
        self.assertIsNone(result['observed_reset_release_s'])

    def test_missing_extra_or_boundary_pulses_rejected(self):
        for count in (10, 11, 13, 14):
            channels = fixture()
            channels[1]['transitions'] = (channels[1]['transitions']+[2., 2.1])[:count]
            with self.subTest(count=count), self.assertRaises(ValueError):
                infer_storage(channels)
        for edge in ('begin_s', 'end_s'):
            channels = fixture()
            channels[1][edge] = channels[1]['transitions'][0 if edge == 'begin_s' else -1]
            with self.subTest(boundary=edge), self.assertRaises(ValueError):
                infer_storage(channels)

    def test_unknown_start_and_nonincreasing_edges_rejected(self):
        channels = fixture(); channels[1]['initial_state'] = 1
        with self.assertRaises(ValueError): infer_storage(channels)
        channels = fixture(); channels[1]['transitions'][2] = channels[1]['transitions'][0]
        with self.assertRaises(ValueError): infer_storage(channels)

    def test_reset_or_power_activity_rejected(self):
        for number in (0, 4):
            channels = fixture(); channels[number]['initial_state'] = 0
            with self.subTest(channel=number), self.assertRaises(ValueError):
                infer_storage(channels)
            channels = fixture(); channels[number]['transitions'] = [.2, .3]
            with self.subTest(channel=number), self.assertRaises(ValueError):
                infer_storage(channels)

    def test_mixed_exports_rejected(self):
        channels = fixture(); channels[6]['end_s'] += .01
        with self.assertRaises(ValueError): infer_storage(channels)

    def proof(self):
        return json.loads((HERE/'same-frame-01/bench-result.json').read_text())

    def test_actual_explicit_save_proof(self):
        report = verify_save(self.proof(), False)
        self.assertEqual(report['name'], 'IMG00062.PNG')

    def test_failed_nonidle_stale_or_wrong_input_refused(self):
        for key, value in (('result', 1), ('media_idle', 0), ('nonce', 0),
                           ('operation', 3), ('fnv_after', 123), ('final_ccr', 0x20000)):
            proof = self.proof(); proof['report'][key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                verify_save(proof, False)
        proof = self.proof(); proof['request']['nonce'] += 1
        with self.assertRaises(ValueError): verify_save(proof, False)
        proof = self.proof(); proof['card']['cleanup_error'] = 12
        with self.assertRaises(ValueError): verify_save(proof, False)

    def test_wrong_code_or_unproven_park_refused(self):
        proof = self.proof(); proof['module_sha256'] = '0'*64
        with self.assertRaises(ValueError): verify_save(proof, False)
        for key, value in (('CONTROL', 12), ('PC', 0x34320000), ('PRIMASK', 0)):
            proof = self.proof(); proof['final_context']['registers'][key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                verify_save(proof, False)

    def test_actual_cold_preserves_strict_failure_and_distinguishes_awake(self):
        result = analyze(HERE/'v60-cycle-01')
        self.assertEqual(result['saved_name'], 'IMG00061.PNG')
        self.assertFalse(result['width_qualification'])
        self.assertFalse(result['original_width_decode_passed'])
        self.assertFalse(result['image_integrity_verified'])
        self.assertEqual(result['events'][-1]['inferred_checkpoint'],
                         'Awake diagnostic completion checkpoint')

    def test_actual_storage_has_no_invented_reset_edge(self):
        for name, image, duration in (
                ('same-frame-01', 'IMG00062.PNG', 2113.32992),
                ('same-frame-02', 'IMG00063.PNG', 2115.04938),
                ('same-frame-03', 'IMG00064.PNG', 2109.92746)):
            with self.subTest(record=name):
                result = analyze(HERE/name)
                self.assertEqual(result['saved_name'], image)
                self.assertEqual(result['complete_pulse_count'], 6)
                self.assertFalse(result['original_width_decode_passed'])
                self.assertIsNone(result['observed_reset_release_s'])
                self.assertAlmostEqual(result['events'][-1]['from_save_entry_ms'], duration)


if __name__ == '__main__':
    unittest.main()
