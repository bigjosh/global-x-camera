"""Offline admission/telemetry tests; no instrument, serial or device access."""
import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from test_bench import bench
import test_board_eth_bench as ethernet
import test_inspect_flash as flash


def manifest():
    fixture=ethernet.BoardEthernetProof();fixture.setUp();m=copy.deepcopy(fixture.m)
    m.update(dma_sleep=True,dma_sleep_profile=True,dma_wait=0x34309500,dma_wait_bytes=24,
        dma_wait_clock=0x34300101,dma_sleep_clocks=0x34309540,dma_sleep_clocks_words=16,
        binary_bytes=0x7000,flash=False,standby=False,error_blinks=True,
        sensor_autostop=True,sensor_single_frame=True,sensor_autostop_proof_schema=2,
        sensor_autostop_readback_timing='post-start',sensor_autostop_prestart=None,
        sensor_autostop_prestart_bytes=0,sensor_autostop_proof=0x34309400,
        sensor_autostop_proof_bytes=160,phase_markers=dict(events={'11':'sensor_autonomous_standby_observed'}),
        card=0x34308000,slots=0x34308100,producer=0x34308400,producer_bytes=416,
        magic_slots=0x34308600,magic_slots_bytes=576,sd_scr=0x34308840,sd_scr_bytes=16,
        sd_erase=0x34308850,sd_erase_bytes=32,sd_stream=0x34308870,sd_stream_bytes=44,
        magic_proof=0x343088A0,magic_proof_words=8,sd_startup_proof=0x343088C0,
        sd_startup_proof_bytes=64,sd_width_proof=0x34308900,sd_width_proof_bytes=24,
        chunk_sectors=3730,magic_layout_version=2,image_offset=156,metadata_offset=4,
        metadata_bytes=152,end_guard_word_bias=1,slot_buffer=bench.FRONT_MAGIC_BUFFER,
        original_guard=bench.FRONT_MAGIC_FRAME+bench.FRAME_BYTES,
        frame=bench.FRONT_MAGIC_FRAME,frame_bytes=bench.FRAME_BYTES,
        guard=bench.FRONT_MAGIC_BUFFER+bench.SLOT_BYTES,guard_bytes=32,allocation_bytes=bench.SLOT_BYTES)
    m['flags']=[f.replace('-DRAW_DMA_SLEEP=0','-DRAW_DMA_SLEEP=1') for f in m['flags']]
    m['flags']+=['-DSD_DMA_SLEEP_PROFILE=1','-DRAW_SENSOR_AUTOSTOP=1',
        '-DRAW_SENSOR_SINGLE_FRAME=1','-DRAW_ERROR_PREFIX=0']
    return m


class SleepProof(unittest.TestCase):
    def setUp(self):
        self.m=manifest();self.p=dict(operation=1);self.reads=[]
        self.wait=[self.m['dma_wait_clock'],190,200,300000,7,0]
        # Arbitrary unrelated bits must survive each set-alias operation.
        self.clocks=[0x400,0x800,0x100,0x58F,0x4A00,0x180,1,0,0x10,0x13,1,0,0x25,0x24,0x80,0x82]
        self.stream=[0x34300201,0,1,bench.SLOT_BYTES,bench.SLOT_BYTES,bench.SLOT_BYTES,1,0,0,100,100]

    def upload(self,address,size,label):
        self.reads.append((address,size,label))
        values={self.m['dma_wait']:self.wait,self.m['dma_sleep_clocks']:self.clocks,
            self.m['sd_stream']:self.stream}[address]
        self.assertEqual(size,len(values)*4)
        return struct.pack('<'+str(len(values))+'I',*values)

    def snapshot(self):return bench.dma_sleep_snapshot(self,self.m,self.p)[2]

    def test_wait_evidence_is_not_sleep_or_idle_authority(self):
        result=self.snapshot()
        self.assertTrue(result['attempted']);self.assertTrue(result['wfi_instructions_executed'])
        self.assertFalse(result['idle_permission']);self.assertFalse(result['sleep_entered_proven'])
        self.assertEqual(result['wait']['wall_ms'],200)
        self.assertIn('not wall time',result['cycle_qualification'])
        self.wait[1:]=[0,0,1200,0,0] # A fast DMA can finish before the first WFI.
        self.assertFalse(self.snapshot()['wfi_instructions_executed'])

    def test_no_feature_and_legacy_clock_schema_remain_separate(self):
        self.assertIsNone(bench.dma_sleep_snapshot(self,{},self.p));self.assertFalse(self.reads)
        self.m['dma_sleep_clocks_words']=14;self.clocks=self.clocks[:14]
        _,result=bench.dma_sleep_clocks_snapshot(self,self.m)
        self.assertEqual(len(result),14);self.assertNotIn('apb4_after',result)
        with self.assertRaises(ValueError):bench.dma_sleep_layout(self.m)

    def test_read_and_awake_pio_or_idma_need_zero_wait_and_clock_side_effects(self):
        self.wait[1:]=[0]*5;self.clocks=[0]*16
        for mode in (1,2):
            self.stream[2]=mode;self.stream[3]=bench.SLOT_BYTES if mode==1 else 512
            result=self.snapshot();self.assertFalse(result['attempted'])
            self.assertFalse(result['wfi_instructions_executed'])
        self.p['operation']=3
        self.assertFalse(self.snapshot()['attempted'])
        for key,values in (('wait',self.wait),('clocks',self.clocks)):
            for i in range(1 if key=='wait' else 0,len(values)):
                values[i]=1
                with self.subTest(key=key,index=i),self.assertRaises(ValueError):self.snapshot()
                values[i]=0
        self.p['operation']=2
        with self.assertRaises(ValueError):self.snapshot()

    def test_pio_never_claims_prepared_sleep(self):
        self.stream[2:4]=[2,512]
        with self.assertRaises(ValueError):self.snapshot()
        self.clocks=[0]*16
        with self.assertRaises(ValueError):self.snapshot()

    def test_every_context_fault_and_clock_gate_is_checked(self):
        for bit in range(32):
            self.wait[5]=1<<bit
            with self.subTest(bit=bit),self.assertRaises(ValueError):self.snapshot()
        self.wait[5]=0
        good=self.clocks[:]
        for index in range(16):
            self.clocks=good[:];self.clocks[index]^=0x40000000 if index in (0,8,12) else 1
            with self.subTest(index=index),self.assertRaises(ValueError):self.snapshot()
        self.clocks=good[:]
        self.wait[4]=self.wait[1]+1
        with self.assertRaises(ValueError):self.snapshot()

    def test_stream_corruption_cannot_qualify_sleep(self):
        good=self.stream[:]
        for index,value in ((2,0),(2,3),(3,bench.SLOT_BYTES-512),(4,0),(5,0),(8,1)):
            self.stream=good[:];self.stream[index]=value
            with self.subTest(index=index),self.assertRaises(ValueError):self.snapshot()

    def test_short_clock_read_and_wrong_callback_fail(self):
        owner=self
        class Short:
            def upload(self,address,size,label):return owner.upload(address,size,label)[:-4]
        with self.assertRaisesRegex(ValueError,'Incomplete DMA wait'):
            bench.dma_sleep_snapshot(Short(),self.m,self.p)
        with self.assertRaisesRegex(ValueError,'Incomplete DMA Sleep clocks'):
            bench.dma_sleep_clocks_snapshot(Short(),self.m)
        self.wait[0]^=2
        with self.assertRaises(ValueError):self.snapshot()


class SleepAdmission(unittest.TestCase):
    def test_only_concrete_profile_admitted_without_widening_ram_runner(self):
        for is_flash,standby in ((False,False),(True,False),(True,True)):
            m=manifest();m.update(flash=is_flash,standby=standby)
            m['flags']=[f.replace('-DRAW_FLASH=0',f'-DRAW_FLASH={int(is_flash)}').replace(
                '-DRAW_STANDBY=0',f'-DRAW_STANDBY={int(standby)}').replace(
                '-DRAW_ERROR_PREFIX=0',f'-DRAW_ERROR_PREFIX={int(is_flash)}') for f in m['flags']]
            with self.subTest(flash=is_flash,standby=standby):
                self.assertTrue(bench.dma_sleep_layout(m,1));bench.magic_layout(m)
                self.assertTrue(bench.board_eth_layout(m,1));self.assertTrue(bench.sensor_autostop_layout(m,1))
                bench.diagnostic_layout(m,1)
                self.assertEqual(bench.startup_flash_profile(m),is_flash)
                if is_flash:
                    with tempfile.TemporaryDirectory() as d:
                        folder=Path(d);(folder/'manifest.json').write_text(json.dumps(m))
                        (folder/'capture.bin').write_bytes(b'not executed')
                        with self.assertRaisesRegex(ValueError,'Only reviewed RAM/awake'):
                            bench.checked_build(folder,'0'*64)

    def test_wrong_profiles_and_probe_fail_before_read(self):
        m=manifest()
        for change in (dict(dma_sleep_profile=False),dict(dma_sleep_profile=1),dict(dma_sleep=False),
                dict(sensor_single_frame=False),dict(sensor_autostop=False),dict(board_eth_powerdown=False),
                dict(error_blinks=False),dict(sd_clock_hz=12500000),dict(sd_bus_width=1),
                dict(raw_dma_tail_wait=True),dict(sd_idma_read=True),dict(sd_read_diagnostics=True),
                dict(dma_sleep_probe=True),dict(sd_init_gap_ms=200),dict(whole_image_preerase=True),
                dict(sd_clk_gpio_speed=2),dict(magic_layout_version=None),dict(exposure_coarse=30000),
                dict(standby=True),dict(dma_wait_clock=0x34300100),dict(dma_wait_clock=0x343AF001),
                dict(dma_wait_bytes=20),dict(dma_sleep_clocks_words=14)):
            with self.subTest(change=change),self.assertRaises(ValueError):
                bench.dma_sleep_layout(dict(m,**change),1)
        for macro in ('SD_DMA_SLEEP_PROFILE','RAW_DMA_SLEEP','RAW_SENSOR_SINGLE_FRAME','RAW_ERROR_PREFIX'):
            for duplicate in (False,True):
                bad=copy.deepcopy(m);selected=next(f for f in bad['flags'] if f.startswith('-D'+macro+'='))
                if duplicate:bad['flags'].append(selected)
                else:bad['flags'].remove(selected)
                with self.subTest(macro=macro,duplicate=duplicate),self.assertRaises(ValueError):
                    bench.dma_sleep_layout(bad,1)
        for bad in (dict(flags=['-DSD_DMA_SLEEP_PROFILE=1']),dict(dma_sleep_profile=None),
                dict(m,flags=m['flags']+['-DRAW_DMA_SLEEP_PROBE=1'])):
            with self.assertRaises(ValueError):bench.dma_sleep_layout(bad)

    def test_wait_and_clocks_bounds_and_overlaps(self):
        m=manifest()
        for key in ('dma_wait','dma_sleep_clocks'):
            for address in (m['bss_start']-4,m['bss_end']-4,m[key]+1,
                    m['card'],m['slots'],m['producer'],m['magic_slots'],m['sd_scr'],m['sd_erase'],
                    m['sd_stream'],m['magic_proof'],m['sd_startup_proof'],m['sd_width_proof'],
                    m['board_eth_proof'],m['sensor_autostop_proof']):
                with self.subTest(key=key,address=address),self.assertRaises(ValueError):
                    bench.dma_sleep_layout(dict(m,**{key:address}))
        with self.assertRaises(ValueError):bench.dma_sleep_layout(dict(m,dma_wait=m['dma_sleep_clocks']))
        with self.assertRaises(ValueError):bench.dma_sleep_layout(dict(m,bss_end=0x343B0000))

    def test_flash_sleep_refusal_precedes_any_execution_control(self):
        _,m,code,payloads=flash.fixture()
        with tempfile.TemporaryDirectory() as directory:
            class B:
                output=Path(directory)/'inspection'
                def upload(self,address,count,name):return payloads[name]
            with patch.object(flash.f.bench,'dma_sleep_snapshot',side_effect=ValueError('sleep proof')), \
                patch.object(flash.f.bench.sd,'context_proof') as context:
                with self.assertRaisesRegex(ValueError,'sleep proof'):flash.f.inspect(B(),Path(__file__).parent,m,code)
                context.assert_not_called()


if __name__=='__main__':unittest.main()
