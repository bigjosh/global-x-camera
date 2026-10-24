"""Offline actual-C counter/export checks and baseline byte identity."""
import ctypes as C
from pathlib import Path
import random,tempfile,unittest
import test_png16 as old
from decode_profile import decode

class ProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='miniz-profile-')
        folder=Path(cls.temp.name);(folder/'base').mkdir();(folder/'new').mkdir()
        cls.new=old.compile_library(folder/'new')
        here=old.HERE
        try:
            old.HERE=here.parent/'huffman-local-source-v1'
            cls.base=old.compile_library(folder/'base')
        finally:old.HERE=here
        cls.new.png16_miniz_profile_export.argtypes=[C.POINTER(C.c_uint32)]
    @classmethod
    def tearDownClass(cls):
        old.close_library(cls.base);old.close_library(cls.new);cls.temp.cleanup()
    def test_exact_output_and_counter_nesting(self):
        rng=random.Random(72)
        cases=[[0]*35840,[i%1024 for i in range(35840)],[rng.randrange(1024) for _ in range(35840)]]
        for mode in range(4):
            for samples in cases:
                a=old.EncoderTests();a.lib=self.base
                b=old.EncoderTests();b.lib=self.new
                self.new.png16_miniz_profile_reset()
                x=a.encode(samples,1120,32,mode)[1];y=b.encode(samples,1120,32,mode)[1]
                self.assertEqual(x,y)
                words=(C.c_uint32*55)();words[0]=0xa5a5a5a5;words[54]=0x5a5a5a5a
                self.new.png16_miniz_profile_export(C.cast(C.byref(words,4),C.POINTER(C.c_uint32)))
                self.assertEqual(words[0],0xa5a5a5a5);self.assertEqual(words[54],0x5a5a5a5a)
                report=decode(list(words)[1:54],require_mcu=False)
                if mode:
                    self.assertEqual(report['inclusive']['init']['calls'],1)
                    self.assertGreater(report['inclusive']['compress_inclusive']['calls'],0)
                    self.assertGreater(report['inclusive']['adler']['calls'],0)
                else:self.assertEqual(report['clock_reads'],0)
    def test_callback_failure_and_reset(self):
        b=old.EncoderTests();b.lib=self.new
        for fail_after in [0,8,20]:
            self.new.png16_miniz_profile_reset()
            b.encode([i%1024 for i in range(1120*128)],1120,128,3,fail_after=fail_after)
            words=(C.c_uint32*53)();self.new.png16_miniz_profile_export(words)
            decode(list(words),require_mcu=False)
        self.new.png16_miniz_profile_reset();self.new.png16_miniz_profile_export(words)
        report=decode(list(words),require_mcu=False)
        self.assertEqual(report['clock_reads'],0)
        self.assertTrue(all(v==0 for v in report['disjoint_cycles'].values()))
    def test_wrong_extension_refused(self):
        words=[0]*53
        with self.assertRaises(ValueError):decode(words)
if __name__=='__main__':unittest.main(verbosity=2)
