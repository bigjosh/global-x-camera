"""Offline separation-profile and phase-order checks; no instrument access."""
import copy
import struct
import unittest
import test_board_eth_bench as ethernet
from test_bench import bench


class SDInitializationGapProof(unittest.TestCase):
    def setUp(self):
        fixture=ethernet.BoardEthernetProof('test_powerdown_follows_arm_and_precedes_card_initialization')
        fixture.setUp()
        self.m=copy.deepcopy(fixture.m)
        self.m.update(sd_init_gap_ms=200,sd_init_gap_proof=0x34309400,sd_init_gap_proof_bytes=64)
        self.m['flags'].append('-DRAW_SD_INIT_GAP_MS=200U')
        self.m['phase_markers']=dict(events={'11':'sd_init_gap_begin','12':'sd_init_gap_end'})
        self.p=dict(operation=1,arm=100,frame_done=6000000,camera_stop=20000000,sd_begin=100000600)
        self.eth=fixture.w[:]
        self.g=[0x31504147,1,3,0,2000100,6000000,20000000,20000500,100000500,
                80000000,0,0,1,1,400000000,0]
        self.reads=[]

    def upload(self,address,size,label):
        self.reads.append((address,size,label))
        if address==self.m['sd_init_gap_proof']:
            self.assertEqual(size,64);return struct.pack('<16I',*self.g)
        self.assertEqual((address,size),(self.m['board_eth_proof'],256))
        return struct.pack('<64I',*self.eth)

    def snapshot(self):return bench.sd_init_gap_snapshot(self,self.m,self.p,'test')

    def test_completed_gap_is_bound_to_frame_stop_sd_and_zero_commands(self):
        g=self.snapshot()
        self.assertTrue(g['attempted']);self.assertTrue(g['completed'])
        self.assertEqual(g['elapsed_ms'],200)
        self.assertEqual(g['wait_for_stop_ms'],45.001)
        e=bench.board_eth_snapshot(self,self.m,self.p,'eth')
        self.assertTrue(e['qualified_powerdown'])
        self.assertIn('test-sd-init-gap.bin',[r[2] for r in self.reads])

    def test_normal_eth_adjacency_is_not_relaxed(self):
        m=copy.deepcopy(self.m)
        m.update(sd_init_gap_ms=0,sd_init_gap_proof=None,sd_init_gap_proof_bytes=0)
        m['flags'].remove('-DRAW_SD_INIT_GAP_MS=200U')
        with self.assertRaises(ValueError):bench.board_eth_snapshot(self,m,self.p,'normal')
        self.p['sd_begin']=3000000
        self.assertTrue(bench.board_eth_snapshot(self,m,self.p,'normal')['qualified_powerdown'])

    def test_gap_entry_must_follow_eth_without_unexplained_delay(self):
        self.g[4]=7000000
        # Independently valid gap timing does not bypass PHY-to-gap adjacency.
        self.assertTrue(self.snapshot()['completed'])
        with self.assertRaises(ValueError):bench.board_eth_snapshot(self,self.m,self.p,'late')
        self.g[4]=1999999
        with self.assertRaises(ValueError):bench.board_eth_snapshot(self,self.m,self.p,'early')

    def test_wrap_safe_timestamps_and_already_finished_frame(self):
        for shift in (0,0xFFFFFF00,0x80000000):
            p=self.p.copy();g=self.g[:];e=self.eth[:]
            for k in ('arm','frame_done','camera_stop','sd_begin'):self.p[k]=(p[k]+shift)&0xFFFFFFFF
            for i in range(4,9):self.g[i]=(g[i]+shift)&0xFFFFFFFF
            for i in (6,7):self.eth[i]=(e[i]+shift)&0xFFFFFFFF
            with self.subTest(shift=shift):
                self.assertEqual(self.snapshot()['elapsed_ms'],200)
                self.assertTrue(bench.board_eth_snapshot(self,self.m,self.p,'wrap')['qualified_powerdown'])
            self.p=p;self.g=g;self.eth=e
        self.p['frame_done']=self.g[5]=1000000
        self.p['camera_stop']=self.g[6]=2000000
        self.g[7]=2000200;self.g[8]=82000200;self.p['sd_begin']=82000300
        self.assertTrue(self.snapshot()['completed'])

    def test_default_and_legacy_are_inert_but_hidden_feature_is_rejected(self):
        for m in ({},dict(sd_init_gap_ms=0,sd_init_gap_proof=None,sd_init_gap_proof_bytes=0)):
            self.assertIsNone(bench.sd_init_gap_snapshot(self,m,self.p,'off'))
        self.assertFalse(self.reads)
        bad=(dict(sd_init_gap_ms=True),dict(sd_init_gap_ms=200.0),dict(sd_init_gap_ms=1),
             dict(sd_init_gap_ms=None),dict(sd_init_gap_proof=0x34309400),dict(sd_init_gap_proof_bytes=64),
             dict(flags=['-DRAW_SD_INIT_GAP_MS=200U']),dict(flags=['-DRAW_SD_INIT_GAP_MS=0U']))
        for m in bad:
            with self.subTest(m=m),self.assertRaises(ValueError):bench.sd_init_gap_layout(m)

    def test_read_is_capture_gap_free_and_format_is_not_admitted(self):
        self.p['operation']=3;self.g=[0]*16;self.eth=[0]*64
        g=self.snapshot();self.assertFalse(g['attempted']);self.assertFalse(g['completed'])
        self.assertFalse(bench.board_eth_snapshot(self,self.m,self.p,'read')['attempted'])
        for i in range(16):
            self.g=[0]*16;self.g[i]=1
            with self.subTest(word=i),self.assertRaises(ValueError):self.snapshot()
        self.p['operation']=2
        with self.assertRaises(ValueError):bench.sd_init_gap_layout(self.m,2)

    def test_exact_profile_flags_and_disjoint_bss_required_before_upload(self):
        original=copy.deepcopy(self.m)
        for change in (dict(board_eth_powerdown=False),dict(sd_clock_hz=12500000),
                dict(sd_bus_width=1),dict(sd_init_gap_proof=0x34309404),dict(sd_init_gap_proof_bytes=60),
                dict(sd_init_gap_proof=0x3430A000),dict(bss_end=0x343AF004),
                dict(card=0x34309420),dict(board_eth_proof=0x34309400),dict(producer=0x34309300),
                dict(magic_proof=0x343093F0),dict(standby=True),dict(power_probe='hold-after-stop'),
                dict(phase_markers={}),dict(phase_markers=dict(events={'11':'sd_init_gap_end',
                                                                    '12':'sd_init_gap_begin'}))):
            self.m=copy.deepcopy(original);self.m.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):self.snapshot()
        for flags in ([],original['flags'][:-1],original['flags']+['-DRAW_SD_INIT_GAP_MS=200U'],
                      original['flags'][:-1]+['-DRAW_SD_INIT_GAP_MS=200']):
            self.m=copy.deepcopy(original);self.m['flags']=flags
            with self.subTest(flags=flags),self.assertRaises(ValueError):self.snapshot()
        self.assertFalse(self.reads)

    def test_incomplete_proof_is_not_decoded_as_a_success(self):
        class Truncated:
            def upload(inner,address,size,label):return bytes(60)
        with self.assertRaisesRegex(ValueError,'Incomplete SD initialization gap telemetry'):
            bench.sd_init_gap_snapshot(Truncated(),self.m,self.p,'short')

    def test_flash_profile_admission_retains_independent_ram_runner_restriction(self):
        for standby in (False,True):
            m=copy.deepcopy(self.m);m.update(flash=True,standby=standby)
            m['flags']=[f.replace('-DRAW_FLASH=0','-DRAW_FLASH=1').replace(
                '-DRAW_STANDBY=0',f'-DRAW_STANDBY={int(standby)}') for f in m['flags']]
            self.assertTrue(bench.sd_init_gap_layout(m,1))

    def test_every_completion_precondition_and_reserved_word_is_checked(self):
        original=self.g[:]
        for i in (0,1,2,3,5,6,9,10,11,12,13,14,15):
            self.g=original[:];self.g[i]^=1
            with self.subTest(word=i),self.assertRaises(ValueError):self.snapshot()
        self.g=original[:]
        for key in ('arm','frame_done','camera_stop','sd_begin'):
            previous=self.p[key];self.p[key]=0
            with self.subTest(key=key),self.assertRaises(ValueError):self.snapshot()
            self.p[key]=previous

    def test_short_long_reversed_or_unexplained_gaps_are_rejected(self):
        original=self.g[:];p=self.p.copy()
        changes=({4:99},{4:400000101},{6:5999999},{7:19999999},
                 {7:24000001},{8:100000499},{8:120000500})
        for change in changes:
            self.g=original[:]
            for k,v in change.items():self.g[k]=v
            with self.subTest(change=change),self.assertRaises(ValueError):self.snapshot()
        self.g=original[:]
        for end in (100000499,104000501):
            self.p['sd_begin']=end
            with self.subTest(sd_begin=end),self.assertRaises(ValueError):self.snapshot()
        self.p=p


if __name__=='__main__':unittest.main()
