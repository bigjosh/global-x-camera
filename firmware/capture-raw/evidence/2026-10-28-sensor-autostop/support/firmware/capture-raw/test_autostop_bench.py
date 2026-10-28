"""Offline AST1 admission, evidence and failure-retention tests; no instruments."""
import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
import test_board_eth_bench as ethernet
from test_bench import bench


class SensorAutostopProof(unittest.TestCase):
    def setUp(self):
        fixture=ethernet.BoardEthernetProof('test_powerdown_follows_arm_and_precedes_card_initialization')
        fixture.setUp()
        self.m=copy.deepcopy(fixture.m)
        self.m.update(sensor_autostop=True,sensor_autostop_proof=0x34309400,
            sensor_autostop_proof_bytes=160,sensor_autostop_prestart=0x343F4060,
            sensor_autostop_prestart_bytes=32,immutable_bytes=4,source_hashes={'test':'abc'})
        self.m['flags'].append('-DRAW_SENSOR_AUTOSTOP=1')
        self.m['phase_markers']=dict(events={'11':'sensor_autonomous_standby_observed'})
        self.p=dict(operation=1,frame_done=2000000,camera_stop=3002000,
            payload_done=4000000,commit_done=4003000,result=0,nonce=123)
        self.a=[0]*40
        self.a[:34]=[0x41535431,1,40,4,0,100,200,1,4,0,300,400,
            2000100,2001000,3000000,1,1,1,0,3,2,0,4000100,4002000,
            2,1,1,0,1,1,15,400000000,0,500]
        self.pre=[0x41535431,100,200,1,4,0,1,0]
        self.reads=[]

    def upload(self,address,size,label):
        self.reads.append((address,size,label))
        if address==self.m['sensor_autostop_proof']:
            self.assertEqual(size,160);return struct.pack('<40I',*self.a)
        self.assertEqual((address,size),(self.m['sensor_autostop_prestart'],32))
        return struct.pack('<8I',*self.pre)

    def snapshot(self):return bench.sensor_autostop_snapshot(self,self.m,self.p,'test')

    def test_complete_one_frame_and_independent_two_frame_outcomes(self):
        for counter,strobes in ((1,1),(2,2),(1,2),(2,1)):
            self.a[15]=self.a[25]=self.a[29]=counter
            self.a[17]=self.a[26]=strobes
            with self.subTest(counter=counter,strobes=strobes):
                p=self.snapshot()
                self.assertTrue(p['completed'])
                self.assertEqual(p['exact_one_frame_observed'],counter==strobes==1)
                self.assertEqual(p['counter_and_strobe_counts_agree'],counter==strobes)
                self.assertEqual(p['sensor_delta'],counter)
                self.assertEqual(p['strobe_delta'],strobes)

    def test_defaults_are_inert_and_hidden_feature_or_nonboolean_rejected(self):
        for m in ({},dict(sensor_autostop=False,sensor_autostop_proof=None,
                sensor_autostop_proof_bytes=0,sensor_autostop_prestart=None,sensor_autostop_prestart_bytes=0)):
            self.assertIsNone(bench.sensor_autostop_snapshot(self,m,self.p,'off'))
        self.assertFalse(self.reads)
        for m in (dict(sensor_autostop=1),dict(sensor_autostop=None),
                dict(sensor_autostop_proof=0x34309400),dict(sensor_autostop_proof_bytes=160),
                dict(sensor_autostop_prestart=0x343F4060),dict(sensor_autostop_prestart_bytes=32),
                dict(flags=['-DRAW_SENSOR_AUTOSTOP=1']),dict(flags=['-DRAW_SENSOR_AUTOSTOP=0'])):
            with self.subTest(m=m),self.assertRaises(ValueError):bench.sensor_autostop_layout(m)

    def test_read_requires_every_proof_word_zero_and_format_is_forbidden(self):
        self.p['operation']=3;self.a=[0]*40
        self.assertFalse(self.snapshot()['attempted'])
        self.assertEqual(len(self.reads),1) # prestart contains boot history, not a READ command.
        for i in range(40):
            self.a=[0]*40;self.a[i]=1
            with self.subTest(i=i),self.assertRaises(ValueError):self.snapshot()
        with self.assertRaises(ValueError):bench.sensor_autostop_layout(self.m,2)

    def test_profile_bounds_and_other_owner_overlaps_rejected_before_read(self):
        original=copy.deepcopy(self.m)
        for changes in (dict(board_eth_powerdown=False),dict(sd_clock_hz=12500000),
                dict(sd_init_gap_ms=200),dict(sensor_autostop_proof=0x34309404),
                dict(sensor_autostop_proof_bytes=156),dict(sensor_autostop_proof=0x3430A000),
                dict(bss_end=0x343AF004),dict(card=0x34309480),dict(board_eth_proof=0x34309400),
                dict(sd_startup_proof=0x343093E0),dict(sensor_autostop_prestart=0x343F4064),
                dict(sensor_autostop_prestart_bytes=28),dict(phase_markers={})):
            self.m=copy.deepcopy(original);self.m.update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.snapshot()
        for flags in (original['flags'][:-1],original['flags']+['-DRAW_SENSOR_AUTOSTOP=1'],
                original['flags'][:-1]+['-DRAW_SENSOR_AUTOSTOP=1U']):
            self.m=copy.deepcopy(original);self.m['flags']=flags
            with self.subTest(flags=flags),self.assertRaises(ValueError):self.snapshot()
        self.assertFalse(self.reads)

    def test_flash_profile_admitted_without_relaxing_ram_runner(self):
        for standby in (False,True):
            m=copy.deepcopy(self.m);m.update(flash=True,standby=standby)
            m['flags']=[f.replace('-DRAW_FLASH=0','-DRAW_FLASH=1').replace(
                '-DRAW_STANDBY=0',f'-DRAW_STANDBY={int(standby)}') for f in m['flags']]
            self.assertTrue(bench.sensor_autostop_layout(m,1))

    def test_every_fixed_field_reserved_word_and_count_bound_is_checked(self):
        original=self.a[:]
        for i in (0,1,2,3,4,7,8,9,18,20,21,24,27,28,30,31,32,*range(34,40)):
            self.a=original[:];self.a[i]^=1
            with self.subTest(i=i),self.assertRaises(ValueError):self.snapshot()
        for i,value in ((15,0),(15,3),(16,0),(16,3),(17,0),(17,3),
                (19,0),(19,1002),(25,2),(26,2),(29,0),(29,2),(29,3)):
            self.a=original[:];self.a[i]=value
            with self.subTest(i=i,value=value),self.assertRaises(ValueError):self.snapshot()

    def test_prestart_record_is_independently_bound_to_ast(self):
        original=self.pre[:]
        for i in range(8):
            self.pre=original[:];self.pre[i]^=1
            with self.subTest(i=i),self.assertRaises(ValueError):self.snapshot()

    def test_wrap_safe_timestamps_preserve_order(self):
        p=self.p.copy();a=self.a[:];pre=self.pre[:]
        for shift in (0xFFFFFF00,0x80000000):
            self.p=p.copy();self.a=a[:];self.pre=pre[:]
            for key in ('frame_done','camera_stop','payload_done','commit_done'):
                self.p[key]=(p[key]+shift)&0xFFFFFFFF
            for i in (5,6,10,11,12,13,14,22,23,33):self.a[i]=(a[i]+shift)&0xFFFFFFFF
            for i in (1,2):self.pre[i]=(pre[i]+shift)&0xFFFFFFFF
            self.assertTrue(self.snapshot()['completed'])

    def test_reordered_unbounded_or_unbound_timestamps_rejected(self):
        original=self.a[:]
        for i,value in ((10,199),(11,299),(12,1999999),(12,2040001),
                (13,2000099),(14,2000999),(14,402001001),(22,2999999),
                (22,3999999),(23,4000100),(23,4003001),(33,399),(33,2000101)):
            self.a=original[:];self.a[i]=value
            with self.subTest(i=i,value=value),self.assertRaises(ValueError):self.snapshot()
        for key,value in (('camera_stop',2999999),('camera_stop',3400001),
                ('payload_done',4000101),('commit_done',4001999)):
            p=self.p.copy();self.p[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.snapshot()
            self.p=p

    def test_truncated_proof_cannot_be_success(self):
        class Short:
            def upload(inner,address,size,label):return bytes(size-4)
        with self.assertRaisesRegex(ValueError,'Incomplete sensor auto-stop'):
            bench.sensor_autostop_snapshot(Short(),self.m,self.p,'short')

    def test_failed_terminal_retained_without_claiming_success_or_idle(self):
        names=bench.fields(Path(__file__).parent)
        p={name:0 for name in names};p.update(self.p,result=0x502,state=15)
        self.a[3]=15;self.a[4]=0x91
        owner=self
        class FailedBench:
            def upload(inner,address,size,label):
                if address==bench.LOAD:return b'code'
                if address==bench.PROOF:return struct.pack('<96I',*[p[n] for n in names])
                return owner.upload(address,size,label)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            r=bench.sensor_autostop_retain(FailedBench(),self.m,p,b'code',123,out,names)
            self.assertEqual(r['ast']['error'],0x91)
            self.assertFalse(r['idle_permission']);self.assertFalse(r['success_permission'])
            self.assertTrue(r['immutable_code_equal']);self.assertTrue(r['final_proof_equal'])
            self.assertEqual((out/'sensor-autostop-retained.bin').stat().st_size,160)
            self.assertEqual(json.loads((out/'sensor-autostop-retained.json').read_text())['operation_result'],0x502)
            with self.assertRaises(ValueError):self.snapshot()


if __name__=='__main__':unittest.main()
