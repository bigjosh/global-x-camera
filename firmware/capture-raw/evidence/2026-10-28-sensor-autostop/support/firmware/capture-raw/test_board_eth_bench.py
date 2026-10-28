"""Offline board-power admission/proof tests; no instrument access."""
import copy
import struct
import unittest
from test_bench import bench


class BoardEthernetProof(unittest.TestCase):
    def setUp(self):
        self.m=dict(board_eth_powerdown=True,board_eth_proof=0x34309200,board_eth_proof_bytes=256,
            sd_review_profile=True,sd_startup_opt=True,sd_clock_negedge=True,sd_clock_negedge_init=True,
            magic_format=True,line_stream=True,async_stop=True,sd_bus_width=4,sd_clock_hz=25000000,
            sd_gpio_speed=3,transport='idma',pattern=0,exposure_coarse=1428,
            bss_start=0x34308000,bss_end=0x3430A000,stack_floor=0x343AF000)
        macros=dict(RAW_BOARD_ETH_POWERDOWN='1',RAW_FLASH='0',RAW_STANDBY='0',
            SD_REVIEW_PROFILE='1',SD_STARTUP_OPT='1',SD_BUS_WIDTH='4',RAW_SD_CLOCK_HZ='25000000U',
            SD_GPIO_SPEED='3',SD_CLOCK_NEGEDGE='1',SD_CLOCK_NEGEDGE_INIT='1',RAW_MAGIC_FORMAT='1',
            RAW_LINE_STREAM='1',RAW_ASYNC_STOP='1',RAW_DMA='1',RAW_PREINIT='0',RAW_LINE_SNAPSHOTS='0',
            RAW_LINE_POISON='0',RAW_WHOLE_IMAGE_PREERASE='0',RAW_DMA_SLEEP='0',RAW_DMA_TAIL_WAIT='0',
            SD_EARLY_RUN_CLOCK='0',SD_IDMA_READ='0',SD_FIXED_COMPENSATION='0',SD_HIGH_SPEED='0',
            RAW_PATTERN='0',RAW_EXPOSURE_COARSE='1428U')
        self.m['flags']=[f'-D{k}={v}' for k,v in macros.items()]
        self.p=dict(operation=1,arm=100,sd_begin=3000000)
        self.w=[0]*64
        self.w[:22]=[0x31485445,1,6,0,0,123,200,2000000,7,0xC131,0x3000,0x3000,
                    0x3800,0x3800,0x3800,1,6,0x40,0x40,0,0x20,1]
        self.w[22:30]=[0x33330000,0x100000,0x20000,0x404B00,0,0x49000005,400000000,2000]
        self.w[58:61]=[0x80000001,0x1000000,0x20201]
        self.reads=0

    def upload(self,address,size,label):
        self.assertEqual((address,size),(0x34309200,256))
        self.reads+=1
        return struct.pack('<64I',*self.w)

    def snapshot(self):return bench.board_eth_snapshot(self,self.m,self.p,'test')

    def test_new_powerdown_and_already_down_are_distinct_qualified_successes(self):
        v=self.snapshot()
        self.assertTrue(v['qualified_powerdown']);self.assertFalse(v['already_powered_down'])
        self.w[5]=119;self.w[10:12]=[0x3800,0x3800];self.w[13:17]=[0,0,0,4]
        v=self.snapshot()
        self.assertTrue(v['qualified_powerdown']);self.assertTrue(v['already_powered_down'])
        self.assertEqual(v['write_attempts'],0)

    def test_icache_supported_but_dcache_forbidden(self):
        for ccr in (0x201,0x20201):
            self.w[60]=ccr;self.assertTrue(self.snapshot()['qualified_powerdown'])
        for ccr in (0x10201,0x30201):
            self.w[60]=ccr
            with self.assertRaises(ValueError):self.snapshot()

    def test_privileged_msp_accepts_fp_context_flags_but_no_other_control_bits(self):
        # CMSIS Cortex-M55: SFPA bit3, FPCA bit2, SPSEL bit1, nPRIV bit0.
        # The actual successful camera capture retains CONTROL=0xC here.
        for control in (0,4,8,12):
            self.w[57]=control
            with self.subTest(control=control):
                self.assertTrue(self.snapshot()['qualified_powerdown'])
        for bit in (0,1,*range(4,32)):
            for fp_context in (0,12):
                self.w[57]=fp_context|(1<<bit)
                with self.subTest(control=self.w[57]),self.assertRaises(ValueError):
                    self.snapshot()

    def test_disabled_legacy_build_is_noop_and_hidden_flag_rejected(self):
        for m in ({},dict(board_eth_powerdown=False,board_eth_proof=None,board_eth_proof_bytes=0)):
            self.assertIsNone(bench.board_eth_snapshot(self,m,self.p,'off'))
        self.assertEqual(self.reads,0)
        for m in (dict(flags=['-DRAW_BOARD_ETH_POWERDOWN=1']),dict(board_eth_powerdown=1),
                  dict(board_eth_proof=0x34309200),dict(board_eth_proof_bytes=256)):
            with self.assertRaises(ValueError):bench.board_eth_layout(m)

    def test_read_requires_zero_proof_and_never_claims_current_phy_state(self):
        self.p['operation']=3;self.w=[0]*64
        v=self.snapshot();self.assertFalse(v['attempted']);self.assertFalse(v['qualified_powerdown'])
        self.w[0]=0x31485445
        with self.assertRaises(ValueError):self.snapshot()
        self.p['operation']=2
        with self.assertRaises(ValueError):self.snapshot()

    def test_flash_awake_and_standby_share_scope_without_allowing_ram_standby(self):
        for standby in (False,True):
            m=copy.deepcopy(self.m);m.update(flash=True,standby=standby,error_blinks=True)
            m['flags']=[f.replace('-DRAW_FLASH=0','-DRAW_FLASH=1').replace(
                '-DRAW_STANDBY=0',f'-DRAW_STANDBY={int(standby)}') for f in m['flags']]
            self.assertTrue(bench.board_eth_layout(m,1))
        self.m['standby']=True
        with self.assertRaises(ValueError):bench.board_eth_layout(self.m,1)

    def test_scope_flags_bounds_and_overlap_fail_before_read(self):
        original=copy.deepcopy(self.m)
        for change in (dict(sd_clock_hz=12500000),dict(sd_bus_width=1),dict(exposure_coarse=30000),
                dict(power_probe='ethernet-powerdown'),dict(cycle_trace={'schema':1}),
                dict(sd_read_diagnostics=True),dict(error_after_frame_test=True),
                dict(board_eth_proof=0x34309204),dict(board_eth_proof_bytes=252),
                dict(board_eth_proof=0x34309F20),dict(bss_end=0x343B0000),
                dict(card=0x34309240),dict(magic_proof=0x343091F0),dict(flags=[])):
            self.m=copy.deepcopy(original);self.m.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):self.snapshot()
        for i,flag in enumerate(original['flags']):
            self.m=copy.deepcopy(original);self.m['flags'].pop(i)
            with self.subTest(missing=flag),self.assertRaises(ValueError):self.snapshot()
            self.m=copy.deepcopy(original);self.m['flags'].append(flag)
            with self.subTest(duplicate=flag),self.assertRaises(ValueError):self.snapshot()
        self.assertEqual(self.reads,0)

    def test_all_optional_errors_preserve_successful_image_but_reject_saving_claim(self):
        for error in range(1,10):
            self.w=[0]*64;self.w[:8]=[0x31485445,1,0xE1,error,0,0,100,200]
            v=self.snapshot()
            self.assertFalse(v['qualified_powerdown']);self.assertEqual(v['warning']['error'],error)
        self.w[:8]=[0x31485445,1,0xE1,0,9,128,100,200]
        self.assertFalse(self.snapshot()['qualified_powerdown'])

    def test_warning_does_not_allow_malformed_or_fabricated_success_fields(self):
        self.w=[0]*64;self.w[:8]=[0x31485445,1,0xE1,5,0,0,100,200]
        good=self.w[:]
        for index,value in ((0,0),(1,2),(2,5),(3,0),(4,10),(5,256),(15,1),(16,7),
                            (31,1),(32,4),(38,4),(44,4),(50,4),(61,1),(62,1),(63,1)):
            self.w=good[:];self.w[index]=value
            with self.subTest(index=index),self.assertRaises(ValueError):self.snapshot()

    def test_qualified_success_needs_exact_identity_clock_gpio_and_mutation_proof(self):
        good=self.w[:]
        for index in (0,1,2,3,4,5,8,9,10,11,12,13,14,15,16,17,18,19,20,21,
                      22,23,24,25,26,27,28,29,30,32,38,44,50,56,57,58,59,60,61,62,63):
            self.w=good[:]
            self.w[index]^=16 if index==9 else 0x20 if index==19 else 0x1000000 if index==59 else 0x10000 if index==60 else 1
            with self.subTest(index=index),self.assertRaises(ValueError):self.snapshot()

    def test_powerdown_follows_arm_and_precedes_card_initialization(self):
        for change in (dict(arm=0),dict(arm=300),dict(sd_begin=0),dict(sd_begin=1999999)):
            old=self.p.copy();self.p.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):self.snapshot()
            self.p=old
        self.w[7]=self.w[6]
        with self.assertRaises(ValueError):self.snapshot()


if __name__=='__main__':unittest.main()
