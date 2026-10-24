import copy
import json
from pathlib import Path
import struct
import unittest
import receiver_timing as timing


class ReceiverTiming(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).parent/'records/awake02'
        cls.spec = json.loads((cls.root/'receiver-spec.json').read_text())
        cls.data = {k:(cls.root/v['path']).read_bytes()
                    for k,v in cls.spec['artifacts'].items()}

    def call(self, frame=None, raw=None, loader=None):
        d=self.data
        return timing.partition(frame or json.loads(d['frame_result']),
            raw or d['receiver_raw'], json.loads(d['maintenance']),
            d['report_raw'], loader or d['loader_raw'])

    def test_exact_partition_and_same_clock_entry_gap(self):
        result=self.call()
        self.assertEqual(sum(result['disjoint_cycles'].values()), result['total_cycles'])
        self.assertEqual(result['disjoint_cycles']['loader_tail_entry_bss_and_report_initialization'], 11120363)
        self.assertEqual(result['disjoint_cycles']['sensor_stop_call'], 13960561)

    def test_corrupt_or_old_header_cannot_accept_surviving_timing_words(self):
        for index, value in [(0,0), (3,1), (5,0x7f), (14,1), (22,123)]:
            with self.subTest(index=index):
                frame=json.loads(self.data['frame_result'])
                words=frame['receiver_words']; words[index]=value
                with self.assertRaises(ValueError):
                    self.call(frame, struct.pack('<32I',*words))
        frame=json.loads(self.data['frame_result']);frame['receiver_proof_valid_after_maintenance']=False
        with self.assertRaises(ValueError):self.call(frame)

    def test_raw_disagreement_and_reversed_interval_rejected(self):
        raw=bytearray(self.data['receiver_raw']);raw[64]^=1
        with self.assertRaises(ValueError):self.call(raw=raw)
        frame=json.loads(self.data['frame_result']); words=frame['receiver_words']
        words[17]=words[16]-1
        with self.assertRaises(ValueError):self.call(frame,struct.pack('<32I',*words))
        loader=bytearray(self.data['loader_raw']);loader[40]=1
        with self.assertRaises(ValueError):self.call(loader=loader)

    def test_native_wrap_is_supported_but_reversal_is_not(self):
        self.assertEqual(timing.delta(5,0xfffffffe),7)
        with self.assertRaises(ValueError):timing.delta(9,10)


if __name__=='__main__':unittest.main()
