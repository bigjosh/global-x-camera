"""Offline qualification regressions; no recorder or hardware imports."""
import json
from pathlib import Path
import tempfile
import unittest

import summarize_cycles as report


class SummaryTests(unittest.TestCase):
    def test_unknown_final_pulse_is_not_relabelled(self):
        decoded=dict(decode_passed=False,reset_rises_s=[1.],pulses=[
            dict(event_id=i,start_s=1.+i*.01) for i in range(1,10)]+
            [dict(event_id=None,start_s=1.1)])
        p=report.phase_intervals(decoded)
        self.assertFalse(p['strict_decode_passed'])
        self.assertEqual(p['unknown_pulse_count'],1)
        self.assertIsNone(p['interval_ms']['deinitialize_to_pre_wfi'])
        self.assertNotIn('10',p['since_reset_ms'])
        self.assertAlmostEqual(p['interval_ms']['full_commit'],10)

    def test_duplicate_event_cannot_supply_an_endpoint(self):
        decoded=dict(decode_passed=False,reset_rises_s=[0.],pulses=[
            dict(event_id=1,start_s=.1),dict(event_id=1,start_s=.2),dict(event_id=2,start_s=.3)])
        p=report.phase_intervals(decoded)
        self.assertIsNone(p['interval_ms']['receiver_to_strobe'])

    def test_sbf_does_not_imply_image_integrity_and_requires_trial_binding(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); recording=root/'result.json'; recording.write_text('{}')
            sbf=root/'sbf.json'
            s=dict(passed=True,sbf=True,prefix_sha256='p',cpucr_written=False,
                   reset_or_power_changed=False,fresh_park_result=dict(passed=True,prefix_sha256='p'))
            sbf.write_text(json.dumps(s)); qpath=root/'qualification.json'
            q=dict(schema=1,bench_owner='root',cycle='trial01',sector_sha256='s',
                recording_result_sha256=report.sha(recording),owner_attests_no_intervening_poweroff=True,
                owner_attests_sbf_cleared_before_cycle=True,owner_attestation='Warm recovery only after this cycle.',
                sbf_evidence=dict(path='sbf.json',sha256=report.sha(sbf)))
            def run():
                qpath.write_text(json.dumps(q))
                return report.qualification(qpath,cycle_name='trial01',recording_result=recording,sector='s',prefix='p')
            self.assertTrue(run()['terminal_state_qualified'])
            self.assertFalse(run()['image_integrity_verified'])
            q['owner_attests_no_intervening_poweroff']=False
            with self.assertRaises(ValueError):run()
            q['owner_attests_no_intervening_poweroff']=True
            s['sbf']=False;sbf.write_text(json.dumps(s))
            with self.assertRaises(ValueError):run() # Hash must fail first.
            q['sbf_evidence']['sha256']=report.sha(sbf)
            with self.assertRaises(ValueError):run() # Even newly bound SBF false fails.

    def test_no_missing_phase_aggregate_is_fabricated(self):
        decoded=dict(decode_passed=False,reset_rises_s=[],pulses=[])
        p=report.phase_intervals(decoded)
        self.assertTrue(all(v is None for v in p['interval_ms'].values()))
        self.assertEqual(p['since_reset_ms'],{})


if __name__=='__main__':unittest.main()
