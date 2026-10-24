"""Offline qualification of the separate known-compute restoration policy."""
from copy import deepcopy
import sys
import unittest

import restore_known_compute as known
import test_restore_after_compute as original

class KnownTests(original.Tests):
    @classmethod
    def setUpClass(cls):
        # Reuse every nonce/context/one-cycle/no-retry assertion against the new
        # module, overriding only the deliberately changed starting-current test.
        original.run=known
        super().setUpClass()
    def test_invalid_expired_or_unstable_start_never_switches(self):
        for mode in ('wrongkind','expired','stale'):
            c,o,p,proof=self.state(stale=mode=='stale')
            if mode=='wrongkind':proof['start_kind']='nor-maintenance-complete'
            if mode=='expired':proof['verified_monotonic_ns']-=61_000_000_000
            with self.subTest(mode=mode),self.assertRaises((ValueError,RuntimeError)):self.perform(c,o,p,proof)
            self.assertEqual(o.commands,[])
    def test_high_initial_current_is_recorded_without_normal_claim(self):
        c,o,p,proof=self.state(initial=.56)
        result=self.perform(c,o,p,proof)
        self.assertEqual([k for k,t in o.commands],['off','auto'])
        record=next(v for k,v in o.logs if k=='compute_completed_start')
        self.assertEqual(len({s['sequence'] for s in record['statistics']}),6)
        self.assertTrue(all(s['current']['avg']==.56 for s in record['statistics']))
        self.assertIs(record['initial_current_is_normal_claim'],False)
        self.assertIs(record['high_current_cause_established'],False)
        self.assertIs(result['terminal_state_qualified'],False)
    def test_nonfinite_or_wrong_voltage_still_refuses_before_off(self):
        for signal,value in [('current',float('nan')),('power',float('inf')),('voltage',4.4)]:
            c,o,p,proof=self.state(initial=.56);latest=o.latest
            def bad():
                data=deepcopy(latest());data[signal]['avg']=value;return data
            o.latest=bad
            with self.subTest(signal=signal),self.assertRaises(RuntimeError):self.perform(c,o,p,proof)
            self.assertEqual(o.commands,[])
    def test_original_guard_file_unchanged(self):
        self.assertEqual(known.sha_file(known.HERE/'restore_after_compute.py'),
            '02cf79a10d345675e55ae51b2a591c6eb6d4e96c9e2742e76172c99c7a311f3a')

if __name__=='__main__':unittest.main()
