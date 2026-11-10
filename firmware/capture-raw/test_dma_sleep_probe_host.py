"""Offline tests for the separate failed-capture WFI diagnostic runner."""
import copy
import struct
import tempfile
from pathlib import Path
import unittest

import dma_sleep_probe as probe
from test_dma_sleep_bench import manifest


def probe_manifest():
    m=manifest();m.update(dma_sleep_probe=True,dma_sleep_probe_address=0x34309600,
        dma_sleep_probe_words=24,error_blinks=False,source_hashes={'dma_sleep_probe.inc':'f'*64},
        failure_park_policy='Same terminal loop; nonzero result is failure, never idle permission')
    m['flags']=[f for f in m['flags'] if not f.startswith('-DRAW_ERROR_PREFIX=')]+['-DRAW_DMA_SLEEP_PROBE=1']
    return m


def valid_words():
    return [0x31505344,1,4,0,0,0,100,103,1000,1201000,
        103,123,1201000,1205000,20,20,200,200,0,0,0,0,0,0]


class ProbeHost(unittest.TestCase):
    def test_exact_probe_gets_separate_layout_only(self):
        m=probe_manifest();original=copy.deepcopy(m)
        self.assertTrue(probe.bench.dma_sleep_probe_layout(m));self.assertEqual(m,original)
        self.assertTrue(m['dma_sleep_probe']);self.assertFalse(m['error_blinks'])
        with self.assertRaises(ValueError):probe.bench.diagnostic_layout(m,1)
        for change in (dict(flash=True),dict(standby=True),dict(error_blinks=True),
                dict(dma_sleep_probe=False),dict(dma_sleep_probe=1),dict(dma_sleep_probe_words=23),
                dict(dma_sleep_probe_address=m['dma_wait']),dict(dma_sleep_probe_address=m['card']),
                dict(dma_sleep_probe_address=m['bss_end']-4),dict(dma_sleep_probe_address=0x34309601),
                dict(failure_park_policy='allowed'),dict(source_hashes={})):
            with self.subTest(change=change),self.assertRaises(ValueError):
                probe.bench.dma_sleep_probe_layout(dict(m,**change))

    def test_probe_macro_and_error_engine_cannot_be_hidden(self):
        m=probe_manifest()
        for flags in (m['flags'][:-1],m['flags']+['-DRAW_DMA_SLEEP_PROBE=1'],
                m['flags']+['-DRAW_ERROR_PREFIX=0']):
            with self.assertRaises(ValueError):probe.bench.dma_sleep_probe_layout(dict(m,flags=flags))

    def test_valid_finite_probe_and_wrapping_ticks(self):
        words=valid_words();decoded=probe.decode(struct.pack('<24I',*words));probe.validate_record(decoded)
        self.assertEqual(decoded['sleep_wall_ms'],20)
        self.assertEqual(decoded['sleep_active_cycles'],4000)
        for i in (6,7,10,11):words[i]=(words[i]+0xFFFFFFF0)&0xFFFFFFFF
        probe.validate_record(probe.decode(struct.pack('<24I',*words)))

    def test_faults_activity_or_mutation_refuse_probe_qualification(self):
        good=valid_words()
        changes=((0,0),(1,2),(2,15),(3,1),(4,1),(5,1),(7,102),(7,105),
            (11,122),(11,125),(14,0),(14,1001),(15,19),(16,0),(17,201),
            (18,1),(19,1),(20,1),(21,1),(22,0x1000),(23,0x2000),(23,0xFFFFFFFF))
        for index,value in changes:
            words=good[:];words[index]=value
            with self.subTest(index=index,value=value),self.assertRaises(ValueError):
                probe.validate_record(probe.decode(struct.pack('<24I',*words)))
        for size in (0,92,100):
            with self.assertRaises(ValueError):probe.decode(bytes(size))

    def test_retained_success_is_not_capture_success_or_idle_permission(self):
        m=probe_manifest();m['immutable_bytes']=4;m['expected_flags']=163
        code=b'code';names=probe.bench.fields(Path(__file__).parent)
        p={n:0 for n in names};p.update(magic=probe.bench.MAGIC,schema=1,words=96,nonce=123,
            operation=1,state=15,result=0x334,terminal=probe.bench.DONE,stage=5,
            flags=163,card=m['card'],card_size=200,slots=m['slots'],slots_size=640)
        terminal=struct.pack('<96I',*[p[n] for n in names])
        clock=struct.pack('<16I',0,0,0,0x18F,0x4200,0x80,1,0,0,3,1,0,1,0,0,2)
        blobs={'probe.bin':struct.pack('<24I',*valid_words()),'terminal.bin':terminal,
            'dma-wait.bin':struct.pack('<6I',m['dma_wait_clock'],0,0,0,0,0),
            'dma-sleep-clocks.bin':clock,'probe-card.bin':bytes(200),'probe-code.bin':code,
            'probe-current-faults.bin':bytes(8),'probe-final-terminal.bin':terminal}
        calls=[]
        class ReadOnly:
            def upload(self,address,size,label):calls.append(label);return blobs[label]
            def call(self,*args,**kwargs):raise AssertionError('No execution-control command permitted')
        with tempfile.TemporaryDirectory() as d:
            result=probe.retain(ReadOnly(),m,code,123,Path(d),names)
            self.assertTrue(result['diagnostic_passed']);self.assertFalse(result['capture_success'])
            self.assertFalse(result['idle_permission']);self.assertFalse(result['sleep_entered_proven'])
            self.assertFalse(result['post_launch_execution_control'])
        for label,value in (('probe-code.bin',b'evil'),('probe-final-terminal.bin',bytes(384)),
                ('probe-current-faults.bin',struct.pack('<2I',1,0)),('terminal.bin',bytes(384))):
            saved=blobs[label];blobs[label]=value
            with tempfile.TemporaryDirectory() as d,self.assertRaises(ValueError):
                probe.retain(ReadOnly(),m,code,123,Path(d),names)
            blobs[label]=saved


if __name__=='__main__':unittest.main()
