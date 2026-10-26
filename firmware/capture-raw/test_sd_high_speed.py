"""Exact High Speed negotiation/clock/phase evidence admission, offline only."""
import copy
import struct
import unittest
import subprocess
import sys
import tempfile
from pathlib import Path
from test_sd_width import bench


class HighSpeedGuards(unittest.TestCase):
    def setUp(self):
        self.m=dict(sd_clock_hz=50000000,sd_bus_width=4,sd_gpio_speed=3,
            sd_fixed_compensation=False,sd_compensation_modified=False,
            sd_clock_negedge=True,sd_clock_negedge_init=True,
            sd_review_profile=True,sd_high_speed=True,sd_kernel_hz=100000000,
            sd_identification_clock_negedge=True,sd_transfer_clock_negedge=False,
            sd_switch_clock_hz=25000000,
            sd_width_proof=0x34308000,sd_width_proof_bytes=24,
            sd_high_speed_proof=0x34308100,sd_high_speed_proof_bytes=184,
            sd_clock_profile_proof=0x34308200,sd_clock_profile_proof_bytes=128,
            bss_start=0x34307000,bss_end=0x34309000,
            flags=['-DRAW_SD_CLOCK_HZ=50000000U','-DSD_BUS_WIDTH=4',
                '-DSD_CLOCK_NEGEDGE=1','-DSD_CLOCK_NEGEDGE_INIT=1',
                '-DSD_REVIEW_PROFILE=1','-DSD_HIGH_SPEED=1'])
        hs=[50000000,100000000,1,1,0x900,0x900,0x100,0x100,0x24001,1,0,0xFF3,0,0x300]
        status=bytearray(64);status[1]=100;status[13]=2;status[16]=1;status[17]=1
        clock=[0]*32
        clock[0:5]=[0x5344434B,1,5,0,0];clock[28]=100000000
        self.blocks={0x34308000:struct.pack('<6I',4,5,0x920,1,0x24001,4),
            0x34308100:struct.pack('<14I',*hs)+bytes(status)*2,
            0x34308200:struct.pack('<32I',*clock)}
        self.calls=0

    def upload(self,address,size,name):
        self.calls+=1
        data=self.blocks[address]
        self.assertEqual(len(data),size)
        return data

    def test_complete_proof_requires_final_phase_zero_and_restored_clock(self):
        result=bench.width_snapshot(self,self.m,'good')
        self.assertEqual(result['configured_clkcr'],0x24001)
        self.assertEqual(result['high_speed']['clock_profile']['state'],5)
        self.assertEqual(self.calls,3)

    def test_profile_rejects_wrong_kernel_phase_or_missing_protocol_before_upload(self):
        for change in (dict(sd_kernel_hz=150000000),dict(sd_high_speed=False),
                dict(sd_review_profile=False),dict(sd_transfer_clock_negedge=True),
                dict(sd_identification_clock_negedge=False),dict(sd_switch_clock_hz=50000000),
                dict(sd_clock_negedge_init=False),dict(sd_clock_profile_proof_bytes=124)):
            m=copy.deepcopy(self.m);m.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):
                bench.width_snapshot(self,m,'bad')
            self.assertEqual(self.calls,0)

    def test_all_switch_status_groups_and_crc_are_checked(self):
        good=self.blocks[0x34308100]
        changes=[(8*4,0x34001),(9*4,0),(6*4,0x102),(7*4,0x1100)]
        for offset,value in changes:
            bad=bytearray(good);struct.pack_into('<I',bad,offset,value)
            self.blocks[0x34308100]=bytes(bad)
            with self.subTest(offset=offset),self.assertRaises(ValueError):
                bench.width_snapshot(self,self.m,'bad')
        for base in (56,120):
            for offset,value in ((1,0),(1,201),(13,0),(14,15),(14,0xF0),(15,15),(15,0xF0),(16,0xF1),(17,2),(29,2)):
                bad=bytearray(good);bad[base+offset]=value
                self.blocks[0x34308100]=bytes(bad)
                with self.subTest(base=base,offset=offset,value=value),self.assertRaises(ValueError):
                    bench.width_snapshot(self,self.m,'bad')

    def mixed_profile(self):
        m=copy.deepcopy(self.m)
        m.update(sd_high_speed_mixed_slew=True,sd_high_speed_gpio_values=dict(c=0x10,e=0))
        m['flags'].append('-DSD_HIGH_SPEED_MIXED_SLEW=1')
        return m

    def test_mixed_slew_requires_exact_pin_encoding_and_preserves_other_bits(self):
        m=self.mixed_profile();raw=bytearray(self.blocks[0x34308100])
        struct.pack_into('<I',raw,11*4,0x10);struct.pack_into('<I',raw,13*4,0)
        self.blocks[0x34308100]=bytes(raw)
        result=bench.width_snapshot(self,m,'mixed')
        self.assertEqual(result['high_speed']['gpio_c_after'],0x10)
        with self.assertRaises(ValueError):bench.width_snapshot(self,self.m,'wrong-profile')
        for index,value in ((11,0xFF3),(13,0x300),(11,0x14),(13,4)):
            bad=bytearray(raw);struct.pack_into('<I',bad,index*4,value)
            self.blocks[0x34308100]=bytes(bad)
            with self.subTest(index=index,value=value),self.assertRaises(ValueError):
                bench.width_snapshot(self,m,'bad-encoding')

    def test_mixed_slew_manifest_is_ram50_only_and_binds_compiler_flag(self):
        for change in (dict(flash=True),dict(standby=True),dict(sd_clock_hz=25000000),
                dict(sd_high_speed_mixed_slew=1),dict(sd_high_speed_mixed_slew=False),
                dict(sd_high_speed_gpio_values=dict(c=0xFF3,e=0x300)),
                dict(flags=self.m['flags']),dict(sd_gpio_speed=1),dict(sd_fixed_compensation=True)):
            m=self.mixed_profile();m.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):bench.width_snapshot(self,m,'bad')
            self.assertEqual(self.calls,0)

    def test_builder_rejects_mixed_slew_outside_reviewed_ram_profile(self):
        with tempfile.TemporaryDirectory(prefix='sd-mixed-slew-') as root:
            out=Path(root)/'not-created'
            base=['--sd-bus-width','4','--sd-clock-hz','50000000','--sd-clock-negedge',
                  '--sd-clock-negedge-init','--sd-review-profile','--sd-high-speed-mixed-slew']
            for extra in (['--flash'],['--standby'],['--sd-clock-hz','25000000'],
                    ['--sd-gpio-speed','1'],['--sd-fixed-compensation']):
                run=subprocess.run([sys.executable,str(Path(__file__).with_name('build.py')),
                    '--out',str(out),*base,*extra],capture_output=True,text=True)
                self.assertEqual(run.returncode,2,run.stdout+run.stderr)
                self.assertFalse(out.exists())

    def high_fixed_profile(self):
        m=copy.deepcopy(self.m)
        m.update(sd_high_speed_fixed_compensation=True,sd_fixed_compensation=True,
            sd_compensation_modified=True,sd_compensation_proof=0x34308300,sd_compensation_proof_bytes=32)
        m['flags']+=['-DSD_HIGH_SPEED_FIXED_COMPENSATION=1','-DSD_FIXED_COMPENSATION=1']
        return m

    def test_high_speed_fixed_compensation_requires_exact_profile(self):
        m=self.high_fixed_profile()
        self.assertEqual(bench.clock_layout(m),50000000)
        self.assertEqual(bench.phase_layout(m),0)
        self.assertTrue(bench.compensation_layout(m))
        for change in (dict(flash=True),dict(standby=True),dict(sd_high_speed_fixed_compensation=1),
                dict(sd_high_speed_fixed_compensation=False),dict(sd_fixed_compensation=False),
                dict(sd_compensation_modified=False),dict(sd_gpio_speed=1),
                dict(sd_high_speed_mixed_slew=True),dict(flags=self.m['flags'])):
            bad=copy.deepcopy(m);bad.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):
                bench.width_layout(bad);bench.compensation_layout(bad)

    def test_builder_rejects_high_speed_fixed_compensation_outside_isolated_ram50(self):
        with tempfile.TemporaryDirectory(prefix='sd-hs-comp-') as root:
            out=Path(root)/'not-created'
            base=['--sd-bus-width','4','--sd-clock-hz','50000000','--sd-clock-negedge',
                '--sd-clock-negedge-init','--sd-review-profile','--sd-high-speed-fixed-compensation']
            for extra in (['--flash'],['--standby'],['--sd-clock-hz','25000000'],
                    ['--sd-gpio-speed','1'],['--sd-high-speed-mixed-slew']):
                run=subprocess.run([sys.executable,str(Path(__file__).with_name('build.py')),
                    '--out',str(out),*base,*extra],capture_output=True,text=True)
                self.assertEqual(run.returncode,2,run.stdout+run.stderr)
                self.assertFalse(out.exists())

    def test_combined_electrical_trial_requires_all_three_flags(self):
        m=self.high_fixed_profile();m.update(sd_high_speed_mixed_slew=True,
            sd_high_speed_combined_electrical=True,sd_high_speed_gpio_values=dict(c=0x10,e=0))
        m['flags']+=['-DSD_HIGH_SPEED_MIXED_SLEW=1','-DSD_HIGH_SPEED_COMBINED_ELECTRICAL=1']
        self.assertEqual(bench.clock_layout(m),50000000);self.assertTrue(bench.compensation_layout(m))
        for change in (dict(sd_high_speed_combined_electrical=False),dict(sd_high_speed_mixed_slew=False),
                dict(sd_high_speed_fixed_compensation=False),dict(sd_high_speed_combined_electrical=1),dict(flash=True)):
            bad=copy.deepcopy(m);bad.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):bench.clock_layout(bad)

    def test_clock_ownership_and_restoration_must_be_complete(self):
        good=self.blocks[0x34308200]
        for index,value in ((2,4),(3,1),(4,1),(24,1),(25,1),(26,1),(27,1),(28,150000000),(29,1)):
            bad=bytearray(good);struct.pack_into('<I',bad,index*4,value)
            self.blocks[0x34308200]=bytes(bad)
            with self.subTest(index=index),self.assertRaises(ValueError):
                bench.width_snapshot(self,self.m,'bad')


if __name__=='__main__':unittest.main()
