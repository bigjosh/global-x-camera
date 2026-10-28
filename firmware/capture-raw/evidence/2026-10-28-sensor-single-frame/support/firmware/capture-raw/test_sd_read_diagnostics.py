"""Offline admission and retained-failure tests for matched single-sector reads."""
import copy
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from test_bench import bench


class ReceiveDiagnostics(unittest.TestCase):
    def setUp(self):
        self.m=dict(sd_read_diagnostics=True,sd_idma_read=False,
            sd_read_diagnostics_proof=0x34309080,sd_read_diagnostics_proof_bytes=64,
            raw_read_camera_proof=0x343090C0,raw_read_camera_proof_bytes=64,
            sd_startup_opt=True,sd_review_profile=True,sd_bus_width=4,sd_clock_hz=25000000,
            sd_gpio_speed=3,sd_clock_negedge=True,sd_clock_negedge_init=True,
            magic_format=True,line_stream=True,async_stop=True,transport='idma',
            pattern=0,exposure_coarse=1428,flash=False,standby=False,
            bss_start=0x34308000,bss_end=0x3430A000,
            sd_startup_proof=0x34309000,sd_startup_proof_bytes=64)
        macros=dict(SD_READ_DIAGNOSTICS='1',SD_IDMA_READ='0',SD_BUS_WIDTH='4',RAW_SD_CLOCK_HZ='25000000U',
            SD_GPIO_SPEED='3',SD_REVIEW_PROFILE='1',SD_STARTUP_OPT='1',SD_CLOCK_NEGEDGE='1',
            SD_CLOCK_NEGEDGE_INIT='1',RAW_FLASH='0',RAW_STANDBY='0',RAW_DMA='1',RAW_MAGIC_FORMAT='1',
            RAW_LINE_STREAM='1',RAW_ASYNC_STOP='1',SD_FIXED_COMPENSATION='0',SD_HIGH_SPEED='0',
            SD_HIGH_SPEED_MIXED_SLEW='0',SD_HIGH_SPEED_FIXED_COMPENSATION='0',SD_HIGH_SPEED_COMBINED_ELECTRICAL='0',
            SD_EARLY_RUN_CLOCK='0',RAW_DMA_TAIL_WAIT='0',RAW_DMA_SLEEP='0',RAW_PREINIT='0',
            RAW_LINE_SNAPSHOTS='0',RAW_LINE_POISON='0',RAW_WHOLE_IMAGE_PREERASE='0',
            RAW_PATTERN='0',RAW_EXPOSURE_COARSE='1428U')
        self.m['flags']=[f'-D{k}={v}' for k,v in macros.items()]
        self.words=[0x31445253,1,0,0,1,bench.READ_BUFFER,512,128,2,0,0,0,0x92,0x34003,1,14]
        self.camera=[0x31504352,1,2,0x44014,0x100,0x400,0,0,0,0,100,50100,0xFF3,0x300,1,1]
        self.calls=0

    def flag(self,macro,value):
        self.m['flags']=[f for f in self.m['flags'] if not f.startswith('-D'+macro+'=')]+[f'-D{macro}={value}']

    def upload(self,address,size,label):
        self.calls+=1
        self.assertEqual(size,64)
        if address==self.m['sd_read_diagnostics_proof']:return struct.pack('<16I',*self.words)
        self.assertEqual(address,self.m['raw_read_camera_proof'])
        return struct.pack('<16I',*self.camera)

    def decode(self,count=1):
        return bench.read_diagnostics_snapshot(self,self.m,'read',lba=0,count=count)

    def test_both_modes_and_explicit_frequencies_keep_failure_status(self):
        for hz,divider in ((12500000,6),(25000000,3)):
            self.m['sd_clock_hz']=hz;self.flag('RAW_SD_CLOCK_HZ',str(hz)+'U')
            self.words[13]=0x34000|divider
            for mode in (False,True):
                self.m['sd_idma_read']=mode;self.flag('SD_IDMA_READ',str(int(mode)))
                self.words[2]=self.words[11]=int(mode)
                bench.diagnostic_layout(self.m,3)
                result=self.decode()
                self.assertEqual((result['sta'],result['result']),(2,14))
        # Telemetry is also available for a successful transfer; ordinary card
        # ownership/result validation remains a separate gate.
        self.words[8]=0x100;self.words[15]=0
        self.assertEqual(self.decode()['result'],0)

    def test_legacy_does_not_read_or_accept_unbound_telemetry(self):
        for m in ({},dict(sd_read_diagnostics=False,sd_read_diagnostics_proof=None,
                          sd_read_diagnostics_proof_bytes=0,raw_read_camera_proof=None,raw_read_camera_proof_bytes=0)):
            self.assertFalse(bench.read_diagnostics_layout(m))
        for m in (dict(flags=['-DSD_READ_DIAGNOSTICS=1']),dict(sd_read_diagnostics_proof=0x34309080),
                  dict(raw_read_camera_proof_bytes=64)):
            with self.assertRaises(ValueError):bench.read_diagnostics_layout(m)
        self.assertEqual(self.calls,0)

    def test_request_identity_hardware_scope_and_register_bounds(self):
        for index,value in ((0,0),(1,2),(2,1),(3,1),(4,2),(5,bench.READ_BUFFER+4),(6,1024),
                            (7,129),(9,513),(10,1),(11,1),(13,0x24003),(14,0)):
            old=self.words[:];self.words[index]=value
            with self.subTest(index=index),self.assertRaises(ValueError):self.decode()
            self.words=old
        with self.assertRaises(ValueError):self.decode(2)

    def test_camera_is_held_in_reset_and_sd_speeds_unchanged(self):
        bench.read_camera_snapshot(self,self.m,'good')
        for index,value in ((0,0),(1,2),(2,1),(3,0x14),(4,0),(5,0),(6,0x20),(7,0x20),
                            (8,0x20),(9,0x400),(11,200),(12,0xFD3),(13,0),(14,0),(15,0)):
            old=self.camera[:];self.camera[index]=value
            with self.subTest(index=index),self.assertRaises(ValueError):bench.read_camera_snapshot(self,self.m,'bad')
            self.camera=old

    def test_manifest_scope_flags_and_overlap_before_upload(self):
        changes=(dict(flash=True),dict(standby=True),dict(sd_clock_hz=50000000),dict(sd_gpio_speed=2),
                 dict(sd_bus_width=1),dict(sd_clk_gpio_speed=3),dict(sd_fixed_compensation=True),
                 dict(sd_clock_negedge_init=False),dict(sd_startup_opt=False),dict(sd_review_profile=False),
                 dict(error_blinks=True),dict(raw_dma_tail_wait=True),dict(sd_early_run_clock=True),
                 dict(sd_idma_read=1),dict(sd_read_diagnostics=1),dict(pattern=1),dict(exposure_coarse=999),
                 dict(sd_read_diagnostics_proof_bytes=60),dict(sd_read_diagnostics_proof=0x34309FE0),
                 dict(card=0x34309080),dict(raw_read_camera_proof=0x34309080),
                 dict(raw_read_camera_proof_bytes=60),dict(flags=[]))
        original=copy.deepcopy(self.m)
        for change in changes:
            self.m=copy.deepcopy(original);self.m.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):self.decode()
        for index,flag in enumerate(original['flags']):
            self.m=copy.deepcopy(original);self.m['flags'].pop(index)
            with self.subTest(missing=flag),self.assertRaises(ValueError):self.decode()
            self.m=copy.deepcopy(original);self.m['flags'].append(flag)
            with self.subTest(duplicate=flag),self.assertRaises(ValueError):self.decode()
        self.m=original
        for operation in (1,2):
            with self.assertRaises(ValueError):bench.diagnostic_layout(self.m,operation)
        self.assertEqual(self.calls,0)

    def test_count_refusal_before_plan_or_hardware(self):
        with tempfile.TemporaryDirectory() as td:
            args=SimpleNamespace(build=Path(td),expected_sha='unused',operation='read',lba=0,count=2,
                                 out=Path(td)/'not-created')
            with patch.object(bench,'checked_build',return_value=(self.m,b'code')),patch.object(bench,'fields',return_value=[]):
                with self.assertRaisesRegex(ValueError,'one-sector READ'):bench.run(args)
            self.assertFalse(args.out.exists())

    def test_builder_refuses_scope_changes_before_output(self):
        common=['--sd-read-diagnostics','--sd-review-profile','--sd-startup-opt','--sd-bus-width','4',
                '--sd-clock-hz','25000000','--sd-clock-negedge','--sd-clock-negedge-init',
                '--magic-format','--line-stream','--async-stop']
        script=Path(__file__).with_name('build.py')
        for flags in (['--sd-read-diagnostics'],common+['--flash'],common+['--standby'],
                      common+['--sd-clock-hz','50000000'],common+['--sd-gpio-speed','1'],
                      common+['--sd-clk-gpio-speed','3'],common+['--sd-fixed-compensation'],
                      common+['--preinit'],common+['--error-blinks'],common+['--raw-dma-tail-wait']):
            with tempfile.TemporaryDirectory() as td:
                out=Path(td)/'not-created'
                p=subprocess.run([sys.executable,str(script),'--out',str(out),*flags],capture_output=True,text=True)
                self.assertEqual(p.returncode,2,p.stdout+p.stderr)
                self.assertIn('Receive diagnostics require',p.stderr)
                self.assertFalse(out.exists())


if __name__=='__main__':unittest.main()
