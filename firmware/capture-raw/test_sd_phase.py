"""RAM-only launch-phase binding; no hardware accessed."""
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_sd_width import bench, FakeRead

HERE=Path(__file__).resolve().parent


class PhaseGuards(unittest.TestCase):
    def setUp(self):
        self.manifest=dict(sd_clock_negedge=True,sd_clock_hz=25000000,
            sd_bus_width=4,sd_gpio_speed=3,sd_fixed_compensation=False,
            sd_compensation_modified=False,flash=False,standby=False,
            sd_width_proof=0x34308000,sd_width_proof_bytes=24,
            bss_start=0x34307000,bss_end=0x34309000,
            flags=['-DSD_CLOCK_NEGEDGE=1','-DSD_BUS_WIDTH=4','-DRAW_SD_CLOCK_HZ=25000000U'])

    def test_legacy_and_explicit_default_keep_rising_phase(self):
        self.assertEqual(bench.phase_layout({}),0)
        self.assertEqual(bench.phase_layout(dict(sd_clock_negedge=False,
            flags=['-DSD_CLOCK_NEGEDGE=0'])),0)

    def test_phase_bit_must_match_read_back_width_proof(self):
        words=[4,5,0x920,1,0x34003,4]
        result=bench.width_snapshot(FakeRead(words),self.manifest,'phase')
        self.assertEqual(result['configured_clkcr'],0x34003)
        for clkcr in (0x24003,0x36003,0x34006,0x74003):
            bad=words.copy();bad[4]=clkcr
            with self.subTest(clkcr=clkcr),self.assertRaises(ValueError):
                bench.width_snapshot(FakeRead(bad),self.manifest,'wrong')
        old=copy.deepcopy(self.manifest);old['sd_clock_negedge']=False
        old['flags'][0]='-DSD_CLOCK_NEGEDGE=0'
        with self.assertRaises(ValueError):bench.width_snapshot(FakeRead(words),old,'old')

    def test_manifest_scope_and_compiler_mismatch_rejected_before_read(self):
        changes=[dict(sd_clock_negedge=1),dict(sd_clock_negedge='true'),dict(flags=[]),
            dict(flags=['-DSD_CLOCK_NEGEDGE=1']*2),dict(standby=True),
            dict(sd_bus_width=1),dict(sd_gpio_speed=0),dict(sd_fixed_compensation=True),
            dict(sd_compensation_modified=True),dict(sd_clock_hz=12500000)]
        for change in changes:
            m=copy.deepcopy(self.manifest);m.update(change);fake=FakeRead([4,5,0x920,1,0x34003,4])
            with self.subTest(change=change),self.assertRaises(ValueError):
                bench.width_snapshot(fake,m,'bad')
            self.assertEqual(fake.calls,0)

    def test_explicit_followup_phase_allows_medium_and_high_slew(self):
        for speed in (1,2):
            m=copy.deepcopy(self.manifest);m['sd_gpio_speed']=speed
            self.assertEqual(bench.phase_layout(m),0x10000)
        for speed in (True,-1,0,4,'1'):
            m=copy.deepcopy(self.manifest);m['sd_gpio_speed']=speed
            with self.assertRaises(ValueError):bench.phase_layout(m)

    def test_flash_phase_accepts_only_the_selected_electrical_profile(self):
        for standby in (False,True):
            m=copy.deepcopy(self.manifest);m.update(flash=True,standby=standby)
            self.assertEqual(bench.phase_layout(m),0x10000)
            for changes in (dict(sd_gpio_speed=0),dict(sd_gpio_speed=1),
                    dict(sd_gpio_speed=2),dict(sd_fixed_compensation=True),
                    dict(sd_compensation_modified=True),dict(sd_bus_width=1),
                    dict(sd_clock_hz=12500000)):
                bad=copy.deepcopy(m);bad.update(changes)
                with self.subTest(standby=standby,changes=changes),self.assertRaises(ValueError):
                    bench.phase_layout(bad)

    def test_build_refuses_unreviewed_clock_width_or_compensation_before_output(self):
        with tempfile.TemporaryDirectory(prefix='sd-phase-options-') as root:
            out=Path(root)/'never-created'
            for options in (['--sd-clock-hz','12500000'],
                    ['--sd-bus-width','1'],['--sd-gpio-speed','0'],['--sd-fixed-compensation']):
                run=subprocess.run([sys.executable,str(HERE/'build.py'),'--out',str(out),
                    '--sd-bus-width','4','--sd-clock-negedge',*options],capture_output=True,text=True)
                self.assertEqual(run.returncode,2,run.stdout+run.stderr)
                self.assertIn('Clock phase',run.stderr)
                self.assertFalse(out.exists())


if __name__=='__main__':unittest.main()
