"""Bind the isolated fixed-compensation diagnostic to build and gate proof."""
import copy
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from test_bench import bench

HERE=Path(__file__).resolve().parent


class CompensationGuards(unittest.TestCase):
    def setUp(self):
        self.manifest=dict(sd_fixed_compensation=True,sd_compensation_modified=True,
            sd_gpio_speed=3,sd_clock_hz=25000000,sd_compensation_proof=0x34308000,
            sd_compensation_proof_bytes=32,bss_start=0x34307000,bss_end=0x34309000,
            flags=['-DSD_FIXED_COMPENSATION=1','-DRAW_SD_CLOCK_HZ=25000000U'])
        self.words=[0x80,0x81,0,0x100,0x200,0x78,0x287,1]
        self.reads=0

    def reader(self,words=None):
        owner=self;values=self.words if words is None else words
        class R:
            def upload(self,address,size,name):
                owner.reads+=1
                assert (address,size)==(0x34308000,32)
                return struct.pack('<8I',*values)
        return R()

    def test_legacy_default_has_no_register_proof_read(self):
        self.assertIsNone(bench.compensation_snapshot(self.reader(),{},'old'))
        self.assertEqual(self.reads,0)

    def test_valid_gates_and_unknown_inherited_before(self):
        for before in (0x78,0x287,0xFFFFFFFF):
            words=self.words.copy();words[5]=before
            result=bench.compensation_snapshot(self.reader(words),self.manifest,'ok')
            self.assertEqual(result['before'],before)
        words=self.words.copy();words[0]=0x81
        bench.compensation_snapshot(self.reader(words),self.manifest,'already-clocked')

    def test_missing_gate_or_refused_application_fails(self):
        for index,value in [(1,0x80),(1,1),(2,1),(3,0),(4,0),(6,0x78),(7,0)]:
            words=self.words.copy();words[index]=value
            with self.subTest(index=index,value=value),self.assertRaises(ValueError):
                bench.compensation_snapshot(self.reader(words),self.manifest,'bad')

    def test_build_scope_or_layout_refuses_before_read(self):
        for changes in [dict(sd_fixed_compensation=1),dict(sd_compensation_modified=False),
                dict(flags=[]),dict(sd_compensation_proof_bytes=20),
                dict(sd_compensation_proof=0x34308FF0),dict(sd_gpio_speed=0),
                dict(flash=True),dict(standby=True),
                dict(sd_clock_hz=12500000,flags=['-DSD_FIXED_COMPENSATION=1','-DRAW_SD_CLOCK_HZ=12500000U'])]:
            m=copy.deepcopy(self.manifest);m.update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                bench.compensation_snapshot(self.reader(),m,'bad')
        self.assertEqual(self.reads,0)

    def test_disabled_diagnostic_cannot_claim_proof(self):
        for m in [dict(sd_compensation_proof=0x34308000),dict(sd_compensation_proof_bytes=32),
                dict(flags=['-DSD_FIXED_COMPENSATION=1'])]:
            with self.assertRaises(ValueError):bench.compensation_layout(m)

    def test_builder_rejects_mixed_experiment_before_output(self):
        with tempfile.TemporaryDirectory(prefix='sd-comp-options-') as root:
            out=Path(root)/'never-created'
            for options in [('--flash',),('--standby',),('--sd-clock-hz','12500000'),('--sd-gpio-speed','0')]:
                run=subprocess.run([sys.executable,str(HERE/'build.py'),'--out',str(out),
                    '--sd-fixed-compensation',*options],capture_output=True,text=True)
                self.assertEqual(run.returncode,2)
                self.assertIn('Fixed compensation is an isolated 25 MHz RAM diagnostic only',run.stderr)
                self.assertFalse(out.exists())


if __name__=='__main__':unittest.main()
