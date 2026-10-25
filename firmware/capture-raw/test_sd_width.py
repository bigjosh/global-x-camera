"""Reject unqualified width telemetry before accepting a successful RAM operation."""
import copy
import importlib.util
from pathlib import Path
import struct
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('width_guard_bench',HERE/'bench.py')
bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)


class FakeRead:
    def __init__(self,words):self.raw=struct.pack('<6I',*words);self.calls=0
    def upload(self,address,size,name):
        self.calls+=1
        assert (address,size)==(0x34308000,24)
        return self.raw


class WidthGuards(unittest.TestCase):
    def setUp(self):
        self.manifest=dict(sd_bus_width=4,sd_width_proof=0x34308000,
            sd_width_proof_bytes=24,bss_start=0x34307000,bss_end=0x34309000,
            flags=['-DSD_BUS_WIDTH=4'])
        self.proof=[4,5,0x920,1,0x24003,4]

    def test_legacy_one_bit_needs_no_new_read(self):
        fake=FakeRead(self.proof)
        self.assertIsNone(bench.width_snapshot(fake,{},'old'))
        self.assertEqual(fake.calls,0)

    def test_success_retains_actual_negotiation(self):
        result=bench.width_snapshot(FakeRead(self.proof),self.manifest,'ok')
        self.assertEqual(result['configured_clkcr'],0x24003)
        self.assertEqual(result['negotiated_width'],4)

    def test_missing_card_or_host_transition_is_rejected(self):
        for index,value in [(0,1),(1,1),(1,4),(2,0x900),(2,0x400020),(3,0),(4,3),(4,0x8003),(5,1)]:
            with self.subTest(index=index,value=value):
                words=self.proof.copy();words[index]=value
                with self.assertRaises(ValueError):
                    bench.width_snapshot(FakeRead(words),self.manifest,'bad')

    def test_unreviewed_manifest_refuses_before_read(self):
        for changes in [dict(sd_bus_width=True),dict(sd_bus_width=8),
                        dict(sd_width_proof_bytes=20),dict(sd_width_proof=0x34308FF0),
                        dict(flags=[]),dict(sd_bus_width=1)]:
            with self.subTest(changes=changes):
                m=copy.deepcopy(self.manifest);m.update(changes);fake=FakeRead(self.proof)
                with self.assertRaises(ValueError):bench.width_snapshot(fake,m,'bad')
                self.assertEqual(fake.calls,0)


if __name__=='__main__':unittest.main()
