"""Offline rejection tests for separately labelled source-order inference."""
import copy
from pathlib import Path
import unittest
from ordered_edges import infer,analyze

def fixture():
    edges=[]
    for i in range(10):edges.extend([1.+i*.1,1.+i*.1+(i+1)*.5e-6])
    def channel(level,times):return dict(initial_state=level,begin_s=0.,end_s=3.,transitions=times)
    return {0:channel(0,[.1]),4:channel(0,[.05]),1:channel(0,edges),6:channel(1,[])}

class OrderedTests(unittest.TestCase):
    def test_widths_never_become_qualified(self):
        result=infer(fixture())
        self.assertFalse(result['width_qualification'])
        self.assertTrue(result['ordered_structure_valid'])
        self.assertTrue(all(e['assignment_basis']=='inferred from source call order'for e in result['events']))
    def test_missing_or_extra_edges_rejected(self):
        for count in (18,19,21,22):
            c=fixture();c[1]['transitions']=(c[1]['transitions']+[2.1,2.2])[:count]
            with self.subTest(count=count),self.assertRaises(ValueError):infer(c)
    def test_initial_high_rejected(self):
        c=fixture();c[1]['initial_state']=1
        with self.assertRaises(ValueError):infer(c)
    def test_boundary_pulse_rejected(self):
        for which in ('begin_s','end_s'):
            c=fixture();c[1][which]=c[1]['transitions'][0 if which=='begin_s'else-1]
            with self.subTest(which=which),self.assertRaises(ValueError):infer(c)
    def test_reordered_edges_rejected(self):
        c=fixture();c[1]['transitions'][3]=c[1]['transitions'][1]
        with self.assertRaises(ValueError):infer(c)
    def test_mixed_capture_bounds_rejected(self):
        c=fixture();c[4]['end_s']+=.01
        with self.assertRaises(ValueError):infer(c)
    def test_unobserved_or_multiple_reference_edges_rejected(self):
        for n in (0,4):
            for edges in ([],[.05,.1,.2],[2.5]):
                c=fixture();c[n]['transitions']=edges
                with self.subTest(channel=n,edges=edges),self.assertRaises(ValueError):infer(c)
    def test_actual_record_stays_separate_from_strict_failure(self):
        result=analyze(Path(__file__).parent/'v61-cycle-01')
        self.assertFalse(result['original_width_decode_passed'])
        self.assertFalse(result['width_qualification'])
        self.assertFalse(result['image_integrity_verified'])
        self.assertFalse(result['sbf_reader_trial_entry_proven'])
        self.assertEqual(result['transition_count'],20)
        self.assertAlmostEqual(result['events'][-1]['from_reset_release_ms'],2732.16819)

if __name__=='__main__':unittest.main()
