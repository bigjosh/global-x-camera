"""Bind isolated RAM GPIO-slew diagnostics to compiler and SRAM readback proof."""
import copy
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from test_bench import bench

HERE=Path(__file__).resolve().parent


class GpioGuards(unittest.TestCase):
    def setUp(self):
        self.manifest=dict(sd_gpio_speed=0,sd_bus_width=4,sd_gpio_proof=0x34308000,
            sd_gpio_proof_bytes=32,bss_start=0x34307000,bss_end=0x34309000,
            flags=['-DSD_GPIO_SPEED=0'],sd_gpio_masks=dict(c=0xFF3,e=0x300),
            sd_compensation_modified=False)
        self.words=[0,0xFF3,0xA5A5A5A5,0xA5A5A5A5&~0xFF3,
                    0x300,0x5A5A5A5A,0x5A5A5A5A&~0x300,1]
        self.reads=0

    def reader(self,words=None):
        owner=self;values=self.words if words is None else words
        class R:
            def upload(self,address,size,name):
                owner.reads+=1
                assert (address,size)==(0x34308000,32)
                return struct.pack('<8I',*values)
        return R()

    def test_legacy_default_adds_no_read(self):
        self.assertIsNone(bench.gpio_snapshot(self.reader(),{},'old'))
        self.assertEqual(self.reads,0)

    def test_valid_slew_proof_and_preserved_other_pins(self):
        result=bench.gpio_snapshot(self.reader(),self.manifest,'ok')
        self.assertEqual(result['c_after'],self.words[3])
        self.assertEqual(result['e_after'],self.words[6])
        self.assertEqual(self.reads,1)

    def test_wrong_field_or_unrelated_pin_change_rejected(self):
        for index,value in [(0,3),(1,0x3F0),(3,self.words[3]|0x10),
                            (3,self.words[3]^4),(4,0),(6,self.words[6]|0x100),
                            (6,self.words[6]^1),(7,0)]:
            words=self.words.copy();words[index]=value
            with self.subTest(index=index,value=value),self.assertRaises(ValueError):
                bench.gpio_snapshot(self.reader(words),self.manifest,'bad')

    def test_bad_build_or_layout_refuses_before_read(self):
        for changes in [dict(sd_gpio_speed=True),dict(sd_gpio_speed=2),dict(flags=[]),
                        dict(flags=['-DSD_GPIO_SPEED=3']),dict(sd_gpio_proof_bytes=20),
                        dict(sd_gpio_proof=0x34308FF0),dict(sd_compensation_modified=True),
                        dict(sd_gpio_masks=dict(c=0xFF0,e=0x300)),dict(flash=True),
                        dict(standby=True)]:
            m=copy.deepcopy(self.manifest);m.update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                bench.gpio_snapshot(self.reader(),m,'bad')
        self.assertEqual(self.reads,0)

    def test_one_bit_does_not_reconfigure_e_speed(self):
        m=copy.deepcopy(self.manifest);m.update(sd_bus_width=1,sd_gpio_masks=dict(c=0x3F0,e=0))
        words=[0,0x3F0,0xA5A5A5A5,0xA5A5A5A5&~0x3F0,0,0x12345678,0x12345678,1]
        bench.gpio_snapshot(self.reader(words),m,'ok')
        words[6]^=0x100
        with self.assertRaises(ValueError):bench.gpio_snapshot(self.reader(words),m,'bad')

    def test_intermediate_slew_requires_exact_encoding_and_unrelated_pin_preservation(self):
        for speed in (1,2):
            m=copy.deepcopy(self.manifest)
            m.update(sd_gpio_speed=speed,flags=[f'-DSD_GPIO_SPEED={speed}'])
            words=self.words.copy();words[0]=speed
            words[3]=(words[2]&~words[1])|words[1]//3*speed
            words[6]=(words[5]&~words[4])|words[4]//3*speed
            self.assertEqual(bench.gpio_snapshot(self.reader(words),m,'ok')['requested_speed'],speed)
            for index in (0,3,6,7):
                bad=words.copy();bad[index]^=1 if index!=3 else 0x10
                with self.subTest(speed=speed,index=index),self.assertRaises(ValueError):
                    bench.gpio_snapshot(self.reader(bad),m,'bad')
            for changes in (dict(sd_bus_width=1),dict(sd_clock_hz=12500000,
                    flags=[f'-DSD_GPIO_SPEED={speed}','-DRAW_SD_CLOCK_HZ=12500000U']),
                    dict(sd_fixed_compensation=True,sd_compensation_modified=True)):
                bad=copy.deepcopy(m);bad.update(changes)
                with self.subTest(speed=speed,changes=changes),self.assertRaises(ValueError):
                    bench.gpio_snapshot(self.reader(words),bad,'bad')

    def test_builder_rejects_slew_flash_before_output(self):
        with tempfile.TemporaryDirectory(prefix='sd-gpio-options-') as root:
            out=Path(root)/'never-created'
            for speed in (0,1,2):
                for mode in ('--flash','--standby'):
                    run=subprocess.run([sys.executable,str(HERE/'build.py'),'--out',str(out),
                                        '--sd-gpio-speed',str(speed),mode],capture_output=True,text=True)
                    self.assertEqual(run.returncode,2)
                    self.assertIn('Nondefault SD GPIO speed is RAM diagnostic only',run.stderr)
                    self.assertFalse(out.exists())

    def test_intermediate_builder_rejects_other_clock_width_or_compensation(self):
        with tempfile.TemporaryDirectory(prefix='sd-gpio-options-') as root:
            out=Path(root)/'never-created'
            for speed in (1,2):
                for options in (['--sd-bus-width','1'],['--sd-clock-hz','12500000'],['--sd-fixed-compensation']):
                    run=subprocess.run([sys.executable,str(HERE/'build.py'),'--out',str(out),
                        '--sd-bus-width','4','--sd-gpio-speed',str(speed),*options],capture_output=True,text=True)
                    self.assertEqual(run.returncode,2)
                    self.assertIn('Intermediate GPIO speed',run.stderr)
                    self.assertFalse(out.exists())


if __name__=='__main__':unittest.main()
