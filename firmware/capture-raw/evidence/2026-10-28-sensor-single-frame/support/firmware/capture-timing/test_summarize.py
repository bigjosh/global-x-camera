"""Offline checks that the ledger preserves evidence and does not guess alignment."""
import unittest

from summarize import summarize_documents


def sample():
    sequence = [(200, .010), (201, .0101), (202, .0102), (203, .0103),
                (204, .015), (205, .0151), (206, .0152), (207, .0153),
                (2, .0154), (101, .017), (12, .019), (15, .021),
                (24, .022), (25, .0221), (74, .027), (50, .028),
                (51, .038), (29, .0382), (30, .048),
                (50, .060), (51, .070), (73, .075), (40, .080)]
    ram = [dict(id=event, cycles=round(stamp * 400000000), tick_ms=int(stamp * 1000), core_hz=400000000)
           for event, stamp in sequence]
    timing = dict(matched=True, mode='cold', nrst_release_s=0., pd0_rise_s=.0099,
                  events=[dict(event, time_s=stamp) for event, (_, stamp) in zip(ram, sequence)])
    details = [dict(id=event['id'], cycles=event['cycles'] - 500, csi_sr0=0, csi_sr1=0)
               for event in ram if event['id'] in (73, 74)]
    words = [0] * 64
    words[52:59] = [12000000, 804000000, 160800000, 160800000, 0x20018602, 1, 4336]
    result = dict(events=ram, event_count=len(ram), errors=2, error_events=details, words=words,
                  completed=True, image_integrity_matches=True, visual_qualification='pending')
    return timing, result


class SummaryTests(unittest.TestCase):
    def test_first_pulse_and_late_stop_error_stay_separate(self):
        summary = summarize_documents(*sample())
        self.assertEqual(summary['first_strobe_us'], 28000)
        self.assertEqual(summary['first_strobe_width_us'], 10000)
        self.assertEqual(len(summary['strobe_pulses']), 2)
        self.assertEqual(summary['strobe_pulses'][1]['rise_us'], 60000)
        self.assertEqual(summary['error_counts'], dict(pre_frame=1, during_frame=0, post_frame=1, unclassified=0))
        self.assertEqual(summary['errors'][1]['optical_phase'], 'after_first_frame')
        self.assertFalse(summary['exposure_qualified'])
        self.assertEqual(summary['visual_qualification'], 'pending')

    def test_mismatched_result_is_rejected(self):
        timing, result = sample()
        result['events'][5]['cycles'] += 1
        with self.assertRaisesRegex(ValueError, 'different RAM event sequence'):
            summarize_documents(timing, result)

    def test_bad_error_detail_association_is_rejected(self):
        timing, result = sample()
        result['error_events'].reverse()
        with self.assertRaisesRegex(ValueError, 'Error details'):
            summarize_documents(timing, result)

    def test_applied_clock_bytes_and_missing_diagnostics(self):
        timing, result = sample()
        summary = summarize_documents(timing, result)
        self.assertEqual(summary['clock_readbacks']['system_predivider'], 2)
        self.assertEqual(summary['clock_readbacks']['system_multiplier'], 134)
        self.assertEqual(summary['clock_readbacks']['mipi_multiplier'], 32)
        result['words'] = [0] * 64
        self.assertIsNone(summarize_documents(timing, result)['clock_readbacks'])


if __name__ == '__main__':
    unittest.main()
