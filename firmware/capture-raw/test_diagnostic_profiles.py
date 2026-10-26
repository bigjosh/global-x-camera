"""Offline admission for separate receive-IDMA and capture-tail experiments."""
import copy
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from test_sd_width import bench


class DiagnosticProfiles(unittest.TestCase):
    def setUp(self):
        self.m=dict(raw_dma_tail_wait=True,sd_idma_read=False,flash=False,standby=False,
            magic_format=True,line_stream=True,async_stop=True,transport='idma',dma_sleep=False,
            raw_dma_tail_wait_proof=0x34309000,raw_dma_tail_wait_proof_bytes=64,
            bss_start=0x34308000,bss_end=0x3430A000,flags=['-DRAW_DMA_TAIL_WAIT=1','-DSD_IDMA_READ=0'])
        self.words=[0x31575444,1,4,0xFFFFFF00,0x100,512,4000000,bench.SLOT_BYTES-512,
                    bench.SLOT_BYTES,2,0,1,0,0,0,0]

    def upload(self,address,size,label):
        self.assertEqual((address,size),(self.m['raw_dma_tail_wait_proof'],64))
        return struct.pack('<16I',*self.words)

    def test_complete_tail_proof_wrap_and_transport(self):
        result=bench.dma_tail_snapshot(self,self.m,'good',dict(mode=1,initial_available_bytes=bench.SLOT_BYTES))
        self.assertEqual(result['elapsed'],512)
        with self.assertRaises(ValueError):bench.dma_tail_snapshot(self,self.m,'bad',dict(mode=2,initial_available_bytes=bench.SLOT_BYTES-512))
        for index,value in ((0,0),(5,513),(7,512),(9,0),(10,1),(11,0),(13,1)):
            good=self.words[:];self.words[index]=value
            with self.subTest(index=index),self.assertRaises(ValueError):
                bench.dma_tail_snapshot(self,self.m,'bad',dict(mode=1,initial_available_bytes=bench.SLOT_BYTES))
            self.words=good

    def test_timeout_can_fall_back_or_finish_on_transport_recheck(self):
        self.words[2]=5;self.words[3]=100;self.words[4]=4000100;self.words[5]=4000000
        self.words[8]=bench.SLOT_BYTES-512
        for mode in (1,2):bench.dma_tail_snapshot(self,self.m,'timeout',dict(mode=mode,initial_available_bytes=bench.SLOT_BYTES))
        self.words[5]=3999999;self.words[4]-=1
        with self.assertRaises(ValueError):bench.dma_tail_snapshot(self,self.m,'early',dict(mode=2,initial_available_bytes=bench.SLOT_BYTES-512))

    def test_already_full_requires_frame_stop_and_monotonic_publication(self):
        self.words[2]=1;self.words[4]=self.words[3];self.words[5]=0
        self.words[7]=bench.SLOT_BYTES;self.words[9]=0;self.words[12]=1
        stream=dict(mode=1,initial_available_bytes=bench.SLOT_BYTES)
        bench.dma_tail_snapshot(self,self.m,'full',stream)
        for index in (11,12):
            self.words[index]=0
            with self.assertRaises(ValueError):bench.dma_tail_snapshot(self,self.m,'bad',stream)
            self.words[index]=1
        with self.assertRaises(ValueError):
            bench.dma_tail_snapshot(self,self.m,'regressed',dict(mode=1,initial_available_bytes=bench.SLOT_BYTES-512))

    def test_layout_rejects_unbound_flags_overlap_and_wrong_operation(self):
        bench.diagnostic_layout(self.m,1)
        for change in (dict(flash=True),dict(raw_dma_tail_wait=1),dict(async_stop=False),
                dict(transport='pio'),dict(raw_dma_tail_wait_proof_bytes=60),
                dict(card=0x34308FF0),dict(flags=['-DRAW_DMA_TAIL_WAIT=0','-DSD_IDMA_READ=0'])):
            m=copy.deepcopy(self.m);m.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):bench.diagnostic_layout(m,1)
        for op in (2,3):
            with self.assertRaises(ValueError):bench.diagnostic_layout(self.m,op)

    def test_idma_receive_is_reviewed_ram_read_only(self):
        m=dict(sd_idma_read=True,sd_review_profile=True,flags=['-DSD_IDMA_READ=1'])
        bench.diagnostic_layout(m,3)
        for change,op in ((dict(sd_review_profile=False),3),(dict(flash=True),3),({},1),({},2),
                (dict(flags=['-DSD_IDMA_READ=0']),3)):
            altered=copy.deepcopy(m);altered.update(change)
            with self.subTest(change=change,op=op),self.assertRaises(ValueError):bench.diagnostic_layout(altered,op)

    def test_builder_rejects_missing_dependencies_before_creating_output(self):
        script=Path(__file__).with_name('build.py')
        for flags in (['--raw-dma-tail-wait'],['--sd-idma-read'],
                ['--sd-idma-read','--sd-review-profile','--flash'],
                ['--raw-dma-tail-wait','--magic-format','--line-stream','--async-stop','--flash']):
            with tempfile.TemporaryDirectory() as td:
                out=Path(td)/'not-created'
                p=subprocess.run([sys.executable,str(script),'--out',str(out),*flags],capture_output=True,text=True)
                self.assertNotEqual(p.returncode,0,p.stdout+p.stderr)
                self.assertFalse(out.exists())


if __name__=='__main__':unittest.main()
