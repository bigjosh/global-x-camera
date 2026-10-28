"""Bind the reviewed startup experiment to real delay/cache telemetry."""
import copy
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from test_sd_width import bench


class StartupAdmission(unittest.TestCase):
    def setUp(self):
        self.m=dict(sd_startup_opt=True,sd_review_profile=True,sd_bus_width=4,
            magic_format=True,sd_clock_hz=12500000,sd_high_speed=False,flash=False,standby=False,
            bss_start=0x34308000,bss_end=0x3430A000,sd_startup_proof=0x34309000,sd_startup_proof_bytes=64,
            flags=['-DSD_STARTUP_OPT=1','-DSD_REVIEW_PROFILE=1','-DSD_HIGH_SPEED=0',
                   '-DRAW_SD_CLOCK_HZ=12500000U'])
        self.words=[0x31504F53,1,400100,400100,100000,400000,410,12500000,1,1,0,0,0,0,0,0]

    def upload(self,address,size,label):
        self.assertEqual((address,size),(0x34309000,64))
        return struct.pack('<16I',*self.words)

    def test_capture_and_read_counts_and_deinit_cache_clear(self):
        self.assertEqual(bench.startup_snapshot(self,self.m,'capture',1)['scr_hits'],1)
        self.words[9]=0
        self.assertEqual(bench.startup_snapshot(self,self.m,'read',3)['scr_reads'],1)
        self.words[9]=1
        for index,value in ((0,0),(2,399999),(3,399999),(4,400000),(5,0),(6,399),
                            (7,25000000),(8,2),(9,2),(10,1),(11,0x34308000),(12,1),(13,1)):
            good=self.words[:];self.words[index]=value
            with self.subTest(index=index),self.assertRaises(ValueError):
                bench.startup_snapshot(self,self.m,'bad',1)
            self.words=good

    def test_layout_and_scope_are_fail_closed(self):
        bench.diagnostic_layout(self.m,1)
        for change in (dict(flash=True),dict(sd_review_profile=False),dict(sd_bus_width=1),
                dict(sd_startup_proof_bytes=60),dict(card=0x34308FF0),
                dict(raw_dma_tail_wait_proof=0x34309020),dict(flags=['-DSD_STARTUP_OPT=0'])):
            m=copy.deepcopy(self.m);m.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):bench.diagnostic_layout(m,1)
        with self.assertRaises(ValueError):bench.diagnostic_layout(self.m,2)

    def test_builder_rejects_unreviewed_width_and_flash(self):
        script=Path(__file__).with_name('build.py')
        for flags in ([],['--sd-review-profile'],['--sd-review-profile','--sd-bus-width','4','--flash']):
            with tempfile.TemporaryDirectory() as td:
                out=Path(td)/'not-created'
                p=subprocess.run([sys.executable,str(script),'--out',str(out),'--sd-startup-opt',*flags],capture_output=True,text=True)
                self.assertNotEqual(p.returncode,0,p.stdout+p.stderr)
                self.assertFalse(out.exists())

    def test_promoted_25_flash_still_refuses_other_experiments_before_build(self):
        script=Path(__file__).with_name('build.py')
        selected=['--flash','--sd-bus-width','4','--sd-clock-hz','25000000',
                  '--sd-clock-negedge','--sd-clock-negedge-init','--sd-review-profile',
                  '--sd-startup-opt','--magic-format','--line-stream','--async-stop']
        for options in (['--sd-clock-hz','50000000'],['--raw-dma-tail-wait'],['--sd-idma-read'],
                ['--dma-sleep'],['--cycle-trace'],['--sd-early-run-clock'],['--sd-gpio-speed','2'],
                ['--sd-fixed-compensation'],['--snapshot'],['--poison'],['--preinit'],
                ['--pattern','diagonal'],['--exposure-coarse','30000']):
            with self.subTest(options=options),tempfile.TemporaryDirectory() as td:
                out=Path(td)/'not-created'
                p=subprocess.run([sys.executable,str(script),'--out',str(out),*selected,*options],
                                 capture_output=True,text=True)
                self.assertEqual(p.returncode,2,p.stdout+p.stderr)
                self.assertFalse(out.exists())

    def test_25_flash_startup_proof_requires_exact_clock_and_scr_cache_completion(self):
        m=copy.deepcopy(self.m)
        m.update(flash=True,standby=False,sd_clock_hz=25000000,sd_gpio_speed=3,
                 sd_clock_negedge=True,sd_clock_negedge_init=True,line_stream=True,
                 async_stop=True,transport='idma',pattern=0,exposure_coarse=1428)
        m['flags'][-1]='-DRAW_SD_CLOCK_HZ=25000000U'
        self.words[7]=25000000
        self.assertEqual(bench.startup_snapshot(self,m,'promoted',1)['run_hz'],25000000)
        for index,value in ((7,12500000),(7,50000000),(9,0),(10,1),(11,0x34308000),(12,1)):
            good=self.words[:];self.words[index]=value
            with self.subTest(index=index,value=value),self.assertRaises(ValueError):
                bench.startup_snapshot(self,m,'unqualified',1)
            self.words=good

    def test_only_exact_no_tail_125_and_25_flash_profiles_are_admitted(self):
        m=copy.deepcopy(self.m)
        m.update(flash=True,sd_gpio_speed=3,sd_clock_negedge=True,sd_clock_negedge_init=True,
                 magic_format=True,line_stream=True,async_stop=True,transport='idma',pattern=0,
                 exposure_coarse=1428)
        for hz in (12500000,25000000):
            m['sd_clock_hz']=hz
            m['flags'][-1]=f'-DRAW_SD_CLOCK_HZ={hz}U'
            for standby in (False,True):
                m['standby']=standby
                self.assertTrue(bench.startup_flash_profile(m))
                bench.diagnostic_layout(m,1)
        for change in (dict(sd_clock_hz=50000000),dict(sd_clock_negedge_init=False),dict(sd_review_profile=False),
                dict(sd_fixed_compensation=True),dict(sd_idma_read=True),dict(raw_dma_tail_wait=True),
                dict(dma_sleep=True),dict(cycle_trace={'schema':1}),dict(pattern=1),dict(exposure_coarse=30000),
                dict(preinit=True),dict(sd_bus_width=1),dict(sd_gpio_speed=2),dict(async_stop=False),
                dict(sd_early_run_clock=True),dict(sd_clock_negedge=False),dict(transport='pio'),
                dict(line_snapshots=True),dict(line_poison=True),dict(whole_image_preerase=True)):
            bad=copy.deepcopy(m);bad.update(change)
            with self.subTest(change=change):
                self.assertFalse(bench.startup_flash_profile(bad))
                with self.assertRaises(ValueError):bench.diagnostic_layout(bad,1)


if __name__=='__main__':unittest.main()
