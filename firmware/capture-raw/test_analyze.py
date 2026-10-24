"""Timing interpretation regressions; no instruments or image writes."""
import importlib.util
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('raw_analyze_tested',HERE/'analyze.py')
analyze=importlib.util.module_from_spec(spec);spec.loader.exec_module(analyze)


class TimingInterpretation(unittest.TestCase):
    def test_sleep_deltas_cannot_be_reported_as_wall_time(self):
        proof=dict(flags=32,begin=100,end=400000100,first_write=100000100,
                   payload_done=300000100,commit_done=310000100,deinit_done=320000100)
        result=analyze.timing(proof)
        self.assertTrue(result['dma_sleep_enabled'])
        self.assertEqual(result['intervals_may_exclude_sleep'],['payload','commit_tail','operation'])
        self.assertIn('NOT elapsed durations',result['basis'])
        self.assertEqual(result['payload'],0.5)
        self.assertIn('never multiply',result['energy_source'])

    def test_polling_and_short_wrap_remain_nominal_counter_time(self):
        result=analyze.timing(dict(flags=3,arm=0xFFFFFF00,frame_done=0x00000100))
        self.assertFalse(result['dma_sleep_enabled'])
        self.assertEqual(result['intervals_may_exclude_sleep'],[])
        self.assertAlmostEqual(result['camera_arm_to_frame'],512/400000000)
        self.assertNotIn('payload',result)


if __name__=='__main__':unittest.main()
