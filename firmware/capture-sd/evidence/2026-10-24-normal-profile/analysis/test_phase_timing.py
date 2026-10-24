import copy
import unittest
from phase_timing import infer


def channels():
    result={n:dict(initial_state=0,begin_s=0,end_s=10,transitions=[.1]) for n in (0,1,4,6)}
    result[1]['transitions']=[v for i in range(10) for v in (1+i*.1,1+i*.1+.000001)]
    return result


class PhaseTests(unittest.TestCase):
    def test_ordered_is_never_width_or_physical_standby_qualification(self):
        r=infer(channels(),'standby')
        self.assertFalse(r['width_qualified'])
        self.assertAlmostEqual(r['frame_irq_to_save_begin_ms'],100)
        self.assertEqual(r['events'][-1]['label'],'Pre-Standby WFI checkpoint')
        self.assertNotIn('actual_standby_verified',r)

    def test_refuses_missing_extra_partial_mixed_or_unobserved_edges(self):
        variants=[]
        c=channels();c[1]['transitions'].pop();variants.append(c)
        c=channels();c[1]['initial_state']=1;variants.append(c)
        c=channels();c[1]['begin_s']=1;variants.append(c)
        c=channels();c[0]['initial_state']=1;variants.append(c)
        c=channels();c[4]['transitions']=[];variants.append(c)
        c=channels();c[4]['end_s']=10.001;variants.append(c)
        c=channels();c[0]['transitions']=[2];variants.append(c)
        for c in variants:
            with self.assertRaises(ValueError):infer(c,'standby')

    def test_awake_completion_label(self):
        r=infer(channels(),'awake')
        self.assertEqual(r['events'][-1]['label'],'Awake completion checkpoint')


if __name__=='__main__':unittest.main()
