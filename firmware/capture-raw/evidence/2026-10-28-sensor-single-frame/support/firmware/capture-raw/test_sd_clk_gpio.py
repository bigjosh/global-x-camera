"""Offline isolation/admission tests for the explicit PC2-only slew profiles."""
import copy
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from test_bench import bench


class ClockGpioAdmission(unittest.TestCase):
    def setUp(self):
        self.m=dict(sd_clk_gpio_speed=2,sd_clk_gpio_proof=0x34309040,sd_clk_gpio_proof_bytes=48,
            sd_startup_opt=True,sd_review_profile=True,sd_bus_width=4,sd_clock_hz=25000000,
            sd_gpio_speed=3,sd_clock_negedge=True,sd_clock_negedge_init=True,
            magic_format=True,line_stream=True,async_stop=True,transport='idma',
            pattern=0,exposure_coarse=1428,flash=False,standby=False,
            bss_start=0x34308000,bss_end=0x3430A000,
            sd_startup_proof=0x34309000,sd_startup_proof_bytes=64)
        macros=dict(SD_CLK_GPIO_SPEED='2',SD_BUS_WIDTH='4',RAW_SD_CLOCK_HZ='25000000U',SD_GPIO_SPEED='3',
            SD_REVIEW_PROFILE='1',SD_STARTUP_OPT='1',SD_CLOCK_NEGEDGE='1',SD_CLOCK_NEGEDGE_INIT='1',
            RAW_FLASH='0',RAW_STANDBY='0',RAW_DMA='1',RAW_MAGIC_FORMAT='1',RAW_LINE_STREAM='1',RAW_ASYNC_STOP='1',
            SD_FIXED_COMPENSATION='0',SD_HIGH_SPEED='0',SD_HIGH_SPEED_MIXED_SLEW='0',
            SD_HIGH_SPEED_FIXED_COMPENSATION='0',SD_HIGH_SPEED_COMBINED_ELECTRICAL='0',
            SD_EARLY_RUN_CLOCK='0',SD_IDMA_READ='0',RAW_DMA_TAIL_WAIT='0',RAW_DMA_SLEEP='0',
            RAW_PREINIT='0',RAW_LINE_SNAPSHOTS='0',RAW_LINE_POISON='0',RAW_WHOLE_IMAGE_PREERASE='0')
        self.m['flags']=[f'-D{k}={v}' for k,v in macros.items()]
        before_c=0xA5A5A5A5;configured=(before_c&~0xFF3)|0xFF3
        self.words=[0x314B4C43,1,2,0x30,0xFF3,before_c,configured,
                    (configured&~0x30)|0x20,0x300,0x5A5A5A5A,0x5A5A5A5A|0x300,1]
        self.calls=0

    def upload(self,address,size,label):
        self.calls+=1
        self.assertEqual((address,size),(0x34309040,48))
        return struct.pack('<12I',*self.words)

    def decode(self,operation=1):
        return bench.clk_gpio_snapshot(self,self.m,'test',operation)

    def test_baseline_and_both_slow_profiles_in_capture_and_read(self):
        for speed in (3,2,1):
            self.m['sd_clk_gpio_speed']=speed
            self.m['flags']=[f for f in self.m['flags'] if not f.startswith('-DSD_CLK_GPIO_SPEED=')]+[f'-DSD_CLK_GPIO_SPEED={speed}']
            self.words[2]=speed;self.words[7]=(self.words[6]&~0x30)|(speed<<4)
            for op in (1,3):
                self.assertEqual(self.decode(op)['requested_speed'],speed)

    def test_legacy_or_disabled_build_does_not_read_telemetry(self):
        for m in ({},dict(sd_clk_gpio_speed=None,sd_clk_gpio_proof=None,sd_clk_gpio_proof_bytes=0)):
            self.assertIsNone(bench.clk_gpio_snapshot(self,m,'old'))
        self.assertEqual(self.calls,0)
        for m in (dict(flags=['-DSD_CLK_GPIO_SPEED=2']),dict(sd_clk_gpio_proof=0x34309040),
                  dict(sd_clk_gpio_proof_bytes=48)):
            with self.assertRaises(ValueError):bench.clk_gpio_layout(m)

    def test_every_readback_field_and_unrelated_pins_are_bound(self):
        for index in range(12):
            original=self.words[:]
            self.words[index]^=1 if index not in (5,6,7,10) else 0x4
            with self.subTest(index=index),self.assertRaises(ValueError):self.decode()
            self.words=original
        self.words[7]=(self.words[7]&~0x300)|0x100
        with self.assertRaises(ValueError):self.decode()

    def test_manifest_scope_flags_and_storage_overlap_rejected_before_read(self):
        changes=(dict(flash=True),dict(standby=True),dict(sd_clk_gpio_speed=True),dict(sd_clk_gpio_speed=0),
            dict(sd_gpio_speed=2),dict(sd_bus_width=1),dict(sd_clock_hz=12500000),dict(sd_startup_opt=False),
            dict(sd_clock_negedge_init=False),dict(sd_review_profile=False),dict(sd_fixed_compensation=True),
            dict(sd_compensation_modified=True),dict(sd_high_speed=True),dict(sd_early_run_clock=True),
            dict(sd_idma_read=True),dict(raw_dma_tail_wait=True),dict(dma_sleep=True),dict(preinit=True),
            dict(line_snapshots=True),dict(line_poison=True),dict(error_test_code=4),dict(transport='pio'),
            dict(card=0x34309050),dict(sd_width_proof=0x34309060),dict(sd_clk_gpio_proof=0x34309020),
            dict(sd_clk_gpio_proof=0x34309FE0),dict(sd_clk_gpio_proof=0x34309041),
            dict(sd_clk_gpio_proof_bytes=44),dict(flags=[]))
        original=copy.deepcopy(self.m)
        for change in changes:
            self.m=copy.deepcopy(original);self.m.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):self.decode()
        self.m=original
        with self.assertRaises(ValueError):self.decode(2)
        self.assertEqual(self.calls,0)
        for index,flag in enumerate(original['flags']):
            self.m=copy.deepcopy(original);self.m['flags'].pop(index)
            with self.subTest(flag=flag),self.assertRaises(ValueError):self.decode()
            self.m=copy.deepcopy(original);self.m['flags'].append(flag)
            with self.subTest(duplicate=flag),self.assertRaises(ValueError):self.decode()
        self.assertEqual(self.calls,0)

    def test_trace_and_patterns_are_independent_of_the_slew_scope(self):
        self.m['cycle_trace']=dict(address=0x343FB000,words=256)
        self.m['pattern']=1
        self.assertEqual(self.decode()['requested_speed'],2)

    def test_builder_refuses_bad_combinations_before_creating_output(self):
        common=['--sd-clk-gpio-speed','2','--sd-review-profile','--sd-startup-opt',
                '--sd-bus-width','4','--sd-clock-hz','25000000','--sd-clock-negedge',
                '--sd-clock-negedge-init','--magic-format','--line-stream','--async-stop']
        script=Path(__file__).with_name('build.py')
        for flags in (['--sd-clk-gpio-speed','2'],common+['--flash'],common+['--standby'],
                common+['--sd-clock-hz','12500000'],common+['--sd-gpio-speed','2'],
                common+['--sd-fixed-compensation'],common+['--raw-dma-tail-wait'],
                common+['--sd-idma-read'],common+['--preinit']):
            with tempfile.TemporaryDirectory() as td:
                out=Path(td)/'not-created'
                run=subprocess.run([sys.executable,str(script),'--out',str(out),*flags],capture_output=True,text=True)
                self.assertEqual(run.returncode,2,run.stdout+run.stderr)
                self.assertIn('CLK-only slew requires',run.stderr)
                self.assertFalse(out.exists())


if __name__=='__main__':unittest.main()
