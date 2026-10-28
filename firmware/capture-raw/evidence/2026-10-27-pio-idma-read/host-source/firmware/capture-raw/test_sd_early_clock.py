"""Bind the isolated CSD-before-CMD7 experiment to its exact RAM profile."""
import copy
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from test_sd_width import bench


class EarlyClockAdmission(unittest.TestCase):
    def setUp(self):
        self.m=dict(sd_early_run_clock=True,sd_startup_opt=True,sd_review_profile=True,
            sd_bus_width=4,sd_clock_hz=12500000,sd_gpio_speed=3,
            sd_clock_negedge=True,sd_clock_negedge_init=True,
            magic_format=True,line_stream=True,async_stop=True,transport='idma',
            pattern=0,exposure_coarse=1428,flash=False,standby=False,
            bss_start=0x34308000,bss_end=0x3430A000,
            sd_startup_proof=0x34309000,sd_startup_proof_bytes=64,
            sd_early_clock_proof=0x34309040,sd_early_clock_proof_bytes=64,
            flags=['-DSD_STARTUP_OPT=1','-DSD_EARLY_RUN_CLOCK=1'])
        self.words=[0x314B4345,1,12500000,0x32,25000000,34,34,35,
                    0x302ee,0x30006,200000,25000000,1000,1410,1420,0]
        self.card={'csd0':0x400E0032}
        self.calls=0

    def upload(self,address,size,label):
        self.calls+=1
        self.assertEqual((address,size),(0x34309040,64))
        return struct.pack('<16I',*self.words)

    def decode(self,operation=1):
        return bench.early_clock_snapshot(self,self.m,'test',operation,self.card)

    def test_complete_clock_transition_in_capture_and_read(self):
        for operation in (1,3):
            result=self.decode(operation)
            self.assertEqual(result['switch_cycles'],410)
            self.assertEqual(result['csd_max_hz'],25000000)

    def test_legacy_profile_does_not_read_new_telemetry(self):
        self.assertIsNone(bench.early_clock_snapshot(self,{},'old',1,{}))
        self.assertEqual(self.calls,0)

    def test_scope_layout_and_flag_mismatch_rejected_before_read(self):
        changes=(dict(flash=True),dict(standby=True),dict(sd_startup_opt=False),dict(sd_bus_width=1),
            dict(sd_clock_hz=25000000),dict(sd_clock_negedge_init=False),dict(sd_gpio_speed=2),
            dict(sd_review_profile=False),dict(raw_dma_tail_wait=True),dict(sd_idma_read=True),
            dict(sd_fixed_compensation=True),dict(line_stream=False),dict(pattern=1),
            dict(exposure_coarse=30000),dict(preinit=True),dict(sd_early_clock_proof_bytes=60),
            dict(sd_early_clock_proof=0x34309fe0),dict(card=0x34309050),
            dict(sd_early_clock_proof=0x34309020),dict(sd_early_run_clock=1),dict(flags=[]))
        good=copy.deepcopy(self.m)
        for change in changes:
            self.m=copy.deepcopy(good);self.m.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):self.decode()
            self.assertEqual(self.calls,0)
        self.m=good
        with self.assertRaises(ValueError):self.decode(2)
        self.assertEqual(self.calls,0)

    def test_every_transition_field_is_bound(self):
        for index,value in ((0,0),(1,2),(2,25000000),(3,0x2a),(4,50000000),(5,0),(6,35),
                            (7,36),(8,0x30006),(9,0x34006),(10,0),(11,200000),
                            (12,1411),(13,1421),(14,1409),(15,1)):
            good=self.words[:];self.words[index]=value
            with self.subTest(index=index),self.assertRaises(ValueError):self.decode()
            self.words=good
        self.card['csd0']^=1
        with self.assertRaises(ValueError):self.decode()

    def test_timestamp_wrap_is_valid_but_reversal_is_not(self):
        self.words[12:15]=[0xffffff00,0x0000009a,0x000000a4]
        self.assertEqual(self.decode()['switch_cycles'],410)
        self.words[14]=0xffffff10
        with self.assertRaises(ValueError):self.decode()

    def test_reserved_or_too_slow_csd_values_are_rejected(self):
        for speed in (0,0x80,0x34,0x37,0x0a):
            self.words[3]=speed;self.card['csd0']=speed
            with self.subTest(speed=speed),self.assertRaises(ValueError):self.decode()

    def test_cli_refuses_unreviewed_combinations_before_creating_output(self):
        common=['--sd-early-run-clock','--sd-review-profile','--sd-startup-opt',
                '--sd-bus-width','4','--sd-clock-hz','12500000','--sd-clock-negedge',
                '--sd-clock-negedge-init','--magic-format','--line-stream','--async-stop']
        script=Path(__file__).with_name('build.py')
        for flags in (['--sd-early-run-clock'],common+['--flash'],common+['--standby'],
                common+['--sd-clock-hz','25000000'],common+['--raw-dma-tail-wait'],
                common+['--sd-idma-read'],common+['--pattern','diagonal'],common+['--preinit']):
            with tempfile.TemporaryDirectory() as td:
                out=Path(td)/'not-created'
                process=subprocess.run([sys.executable,str(script),'--out',str(out),*flags],
                                       capture_output=True,text=True)
                self.assertNotEqual(process.returncode,0,process.stdout+process.stderr)
                self.assertIn('Early run clock requires',process.stderr)
                self.assertFalse(out.exists())


if __name__=='__main__':unittest.main()
