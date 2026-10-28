"""Offline admission and causal-window checks; no instrument access."""
import copy
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from test_bench import bench


COMMON=['--sd-review-profile','--sd-startup-opt','--sd-bus-width','4','--sd-clock-hz','25000000',
        '--sd-clock-negedge','--sd-clock-negedge-init','--magic-format','--line-stream','--async-stop']


class PowerProbe(unittest.TestCase):
    def setUp(self):
        self.m=dict(power_probe='hold-after-stop',power_probe_proof=0x34309040,power_probe_proof_bytes=64,
            sd_review_profile=True,sd_startup_opt=True,sd_clock_negedge=True,sd_clock_negedge_init=True,
            magic_format=True,line_stream=True,async_stop=True,sd_bus_width=4,sd_clock_hz=25000000,
            sd_gpio_speed=3,transport='idma',pattern=0,exposure_coarse=1428,
            bss_start=0x34308000,bss_end=0x3430A000,
            phase_markers=dict(events={'11':'power_probe_hold_begin','12':'power_probe_hold_end'}))
        macros=dict(RAW_POWER_PROBE='1',RAW_FLASH='0',RAW_STANDBY='0',SD_REVIEW_PROFILE='1',SD_STARTUP_OPT='1',
            SD_BUS_WIDTH='4',RAW_SD_CLOCK_HZ='25000000U',SD_GPIO_SPEED='3',SD_CLOCK_NEGEDGE='1',
            SD_CLOCK_NEGEDGE_INIT='1',RAW_MAGIC_FORMAT='1',RAW_LINE_STREAM='1',RAW_ASYNC_STOP='1',
            RAW_DMA='1',RAW_PREINIT='0',RAW_LINE_SNAPSHOTS='0',RAW_LINE_POISON='0',
            RAW_WHOLE_IMAGE_PREERASE='0',RAW_DMA_SLEEP='0',RAW_DMA_TAIL_WAIT='0',
            SD_EARLY_RUN_CLOCK='0',SD_IDMA_READ='0',SD_FIXED_COMPENSATION='0',SD_HIGH_SPEED='0',
            RAW_PATTERN='0',RAW_EXPOSURE_COARSE='1428U')
        self.m['flags']=[f'-D{k}={v}' for k,v in macros.items()]
        self.words=[0x31505750,1,1,3,100,200,300,80000300,1<<10,0xA520,0xA520,0xA520,0xA520,0,15,80000000]
        self.p=dict(operation=1,frame_done=150,camera_stop=180,sd_begin=80001000)
        self.calls=0

    def upload(self,address,size,label):
        self.calls+=1
        self.assertEqual((address,size),(0x34309040,64))
        return struct.pack('<16I',*self.words)

    def read(self):return bench.power_probe_snapshot(self,self.m,self.p,'test')

    def test_both_profiles_and_no_other_pin_change(self):
        self.assertEqual(self.read()['hold_ms'],200)
        self.m['power_probe']='reset-after-stop';self.m['flags'][0]='-DRAW_POWER_PROBE=2'
        self.words[2]=2;self.words[11]&=~32;self.words[12]&=~32
        self.assertEqual(self.read()['mode'],2)
        self.words[11]^=64
        with self.assertRaises(ValueError):self.read()

    def test_disabled_is_noop_but_hidden_feature_rejected(self):
        for m in ({},dict(power_probe=None,power_probe_proof=None,power_probe_proof_bytes=0)):
            self.assertIsNone(bench.power_probe_snapshot(self,m,self.p,'old'))
        self.assertEqual(self.calls,0)
        for m in (dict(flags=['-DRAW_POWER_PROBE=1']),dict(power_probe_proof=1),dict(power_probe_proof_bytes=64)):
            with self.assertRaises(ValueError):bench.power_probe_layout(m)

    def test_scope_flags_bounds_and_operations_rejected_before_read(self):
        original=copy.deepcopy(self.m)
        changes=[dict(flash=True),dict(standby=True),dict(preinit=True),dict(error_blinks=True),
            dict(sd_clock_hz=12500000),dict(sd_bus_width=1),dict(exposure_coarse=14280),
            dict(sd_clk_gpio_speed=3),dict(sd_read_diagnostics=True),dict(power_probe=True),
            dict(power_probe_proof=0x34309041),dict(power_probe_proof_bytes=60),
            dict(power_probe_proof=0x34309FF0),dict(card=0x34309050),dict(flags=[]),dict(phase_markers={})]
        for change in changes:
            self.m=copy.deepcopy(original);self.m.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):self.read()
        for i,flag in enumerate(original['flags']):
            self.m=copy.deepcopy(original);self.m['flags'].pop(i)
            with self.subTest(flag=flag),self.assertRaises(ValueError):self.read()
            self.m=copy.deepcopy(original);self.m['flags'].append(flag)
            with self.subTest(duplicate=flag),self.assertRaises(ValueError):self.read()
        self.m=original
        for op in (2,3):
            self.p['operation']=op
            with self.assertRaises(ValueError):self.read()
        self.assertEqual(self.calls,0)

    def test_failed_or_short_hold_and_reordered_camera_are_rejected(self):
        for index in (0,1,2,3,8,9,10,11,12,13,14,15):
            original=self.words[:];self.words[index]^=32 if index in (8,9,10,11,12) else 1
            if index==8:self.words[index]^=(1<<10)^32
            with self.subTest(index=index),self.assertRaises(ValueError):self.read()
            self.words=original
        self.words[7]=40000300
        with self.assertRaises(ValueError):self.read()
        self.words[7]=80000300;self.p['camera_stop']=400
        with self.assertRaises(ValueError):self.read()
        self.p['camera_stop']=180;self.p['sd_begin']=250
        with self.assertRaises(ValueError):self.read()

    def test_builder_refuses_combination_before_creating_directory(self):
        script=Path(__file__).with_name('build.py')
        for extras in (['--flash'],['--standby'],['--preinit'],['--dma-sleep'],['--error-blinks'],
                       ['--sd-clock-hz','12500000'],['--exposure-coarse','14280']):
            with tempfile.TemporaryDirectory() as td:
                out=Path(td)/'absent'
                run=subprocess.run([sys.executable,str(script),'--out',str(out),*COMMON,
                    '--power-probe','hold-after-stop',*extras],capture_output=True,text=True)
                self.assertEqual(run.returncode,2,run.stdout+run.stderr)
                self.assertIn('Power probe requires',run.stderr)
                self.assertFalse(out.exists())

    def test_hook_is_before_sd_and_after_bounded_camera_wait(self):
        text=Path(__file__).with_name('magic_runtime.inc').read_text()
        execute=text.index('MAGIC_LATE static void raw_magic_execute(void)\n{')
        self.assertLess(text.index('magic_power_probe();',execute),text.index('init_card();',execute))
        helper=text[text.index('static void magic_power_probe(void)'):execute]
        self.assertLess(helper.index('while(!raw_capture_frame_validated()'),helper.index('GPIOO->BSRR'))
        self.assertIn('storage_call_depth',helper)
        self.assertIn('1200000000U',helper)
        self.assertIn('&& --budget',helper)

    def phy_setup(self,mode):
        self.m['power_probe']='ethernet-powerdown' if mode==4 else 'ethernet-control'
        self.m['flags'][0]=f'-DRAW_POWER_PROBE={mode}'
        self.m.update(power_phy_proof=0x34309200,power_phy_proof_bytes=256)
        self.p['deinit_done']=100000000
        w=[0]*64
        w[:10]=[0x31594850,1,mode,6,0,0,200,3000000,100000100,104000000]
        w[10:24]=[7,0xc131,0x1000,0x1000,0x1800 if mode==4 else 0x1000,
            0x1800 if mode==4 else 0x1000,0x1800 if mode==4 else 0x1000,
            0x1800 if mode==4 else 0x1000,0x1000,0x1000,2,0,0,2]
        w[30]=w[31]=1;w[56:62]=[1,7,0xc131,3,400000000,2000]
        return w

    def test_ethernet_identity_mutation_gpio_and_cleanup_are_all_required(self):
        for mode in (3,4):
            w=self.phy_setup(mode)
            class Reader:
                def upload(s,address,size,label):
                    self.assertEqual((address,size),(0x34309200,256))
                    return struct.pack('<64I',*w)
            self.assertEqual(bench.power_phy_snapshot(Reader(),self.m,self.p,'test')['mode'],mode)
            for index in (0,1,2,3,4,5,10,11,12,13,14,15,16,17,18,19,21,22,23,24,27,30,31,32,38,56,57,58,59,60,61,62,63):
                old=w[index];w[index]^=16 if index in (11,58) else 1
                with self.subTest(mode=mode,index=index),self.assertRaises(ValueError):
                    bench.power_phy_snapshot(Reader(),self.m,self.p,'test')
                w[index]=old
            w[8]=99999999
            with self.assertRaises(ValueError):bench.power_phy_snapshot(Reader(),self.m,self.p,'test')

    def test_ethernet_telemetry_cannot_overlap_or_appear_in_other_modes(self):
        self.m.update(power_phy_proof=0x34309200,power_phy_proof_bytes=256)
        with self.assertRaises(ValueError):bench.power_probe_layout(self.m,1)
        self.phy_setup(3)
        for address in (0x34309040,0x34309201,0x34309F20):
            self.m['power_phy_proof']=address
            with self.assertRaises(ValueError):bench.power_probe_layout(self.m,1)

    def test_receiver_requires_idle_clocks_and_exact_power_transition(self):
        self.m['power_probe']='receiver-off';self.m['flags'][0]='-DRAW_POWER_PROBE=5'
        self.m.update(power_csi_proof=0x34309200,power_csi_proof_bytes=128)
        w=[0]*32;w[:12]=[0x31595043,1,2,0,200,400,0x44,0,0x30000,1,2,3]
        w[24:27]=w[6:9]
        class Reader:
            def upload(s,address,size,label):
                self.assertEqual((address,size),(0x34309200,128))
                return struct.pack('<32I',*w)
        self.assertTrue(bench.power_csi_snapshot(Reader(),self.m,self.p,'test')['receiver_off'])
        changes={0:1,1:1,2:1,3:1,6:4,7:4,8:0x10000,9:1,10:2,11:1,12:0x20000,
            14:0x8000,15:8,16:0x80000000,17:8,18:0x80000000,19:8,20:0x80000000,
            21:1,22:2,23:1,24:1,25:1,26:1,29:1,30:1,31:1}
        for index,mask in changes.items():
            w[index]^=mask
            with self.subTest(index=index),self.assertRaises(ValueError):
                bench.power_csi_snapshot(Reader(),self.m,self.p,'test')
            w[index]^=mask
        self.p['camera_stop']=500
        with self.assertRaises(ValueError):bench.power_csi_snapshot(Reader(),self.m,self.p,'test')


if __name__=='__main__':unittest.main()
