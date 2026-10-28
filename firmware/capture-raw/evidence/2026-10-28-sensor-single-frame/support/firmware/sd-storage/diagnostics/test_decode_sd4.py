"""Pure offline checks for native SD packet framing and per-lane CRC."""
import binascii
import hashlib
import unittest
import numpy as np
import decode_sd4 as d


def packet(payload):
    nibbles = np.empty(len(payload) * 2, dtype=np.uint8)
    raw = np.frombuffer(payload, dtype=np.uint8)
    nibbles[::2], nibbles[1::2] = raw >> 4, raw & 15
    lanes = np.ones((4, 1042), dtype=np.uint8)
    lanes[:, 0] = 0
    for lane in range(4):
        bits = (nibbles >> lane) & 1
        lanes[lane, 1:1025] = bits
        # Independent bit-at-a-time CRC compared with decoder's crc_hqx.
        crc = 0
        for bit in bits:
            top = ((crc >> 15) ^ int(bit)) & 1
            crc = (crc << 1) & 0xffff
            if top:
                crc ^= 0x1021
        lanes[lane, 1025:1041] = [(crc >> i) & 1 for i in range(15, -1, -1)]
    return lanes


def cmd(index, argument=0, host=True):
    raw = bytes([(0x40 if host else 0) | index]) + argument.to_bytes(4, 'big')
    raw += bytes([(d.crc7(raw) << 1) | 1])
    return np.unpackbits(np.frombuffer(raw, dtype=np.uint8))


class DecodeTests(unittest.TestCase):
    def test_crc7_known(self):
        self.assertEqual((d.crc7(bytes.fromhex('4000000000')) << 1) | 1, 0x95)
        self.assertEqual((d.crc7(bytes.fromhex('48000001aa')) << 1) | 1, 0x87)

    def test_four_lane_good_and_bad(self):
        payload = bytes(range(256)) * 2
        lanes = packet(payload)
        times = np.arange(1042) * 40e-9
        result = d.packet_at(lanes, times, 0)
        self.assertEqual(result['crc_ok_by_lane'], [True] * 4)
        self.assertEqual(result['payload_sha256'], hashlib.sha256(payload).hexdigest())
        lanes[1, 93] ^= 1
        result = d.packet_at(lanes, times, 0)
        self.assertEqual(result['crc_ok_by_lane'], [True, False, True, True])

    def test_command_response_and_long_response(self):
        bits = np.concatenate([np.ones(4, np.uint8), cmd(2), np.ones(8, np.uint8),
                               np.array([0,0]+[1]*134, np.uint8), np.ones(8, np.uint8), cmd(25, 3730)])
        frames = d.commands(bits, np.arange(len(bits))*40e-9)
        self.assertEqual([f['length_bits'] for f in frames], [48,136,48])
        self.assertEqual(frames[-1]['index'], 25)
        self.assertIsNone(frames[1]['crc_ok'])

    def test_write_status_and_bad_frame_retained(self):
        bits = np.ones(1400, np.uint8)
        bits[0:48], bits[56:104] = cmd(25, 100), cmd(25, 0x900, False)
        lanes = np.ones((4,1400), np.uint8)
        lanes[:,120:1162] = packet(bytes(range(256))*2)
        lanes[2,400] ^= 1
        lanes[0,1164:1169] = [0,1,0,1,1]  # CRC error token, not accepted.
        lanes[0,1169:1180] = 0
        times = np.arange(len(bits))*40e-9
        records = d.transactions(d.commands(bits,times), lanes, times)
        self.assertEqual(len(records),1)
        self.assertEqual(len(records[0]['packets']),1)
        decoded = records[0]['packets'][0]
        self.assertEqual(decoded['crc_ok_by_lane'],[True,True,False,True])
        self.assertEqual(decoded['crc_status_candidates'][0]['meaning'],'crc_error')
        self.assertAlmostEqual(decoded['observed_busy']['duration_s'],11*40e-9)

    def test_duplicate_transition_sampling(self):
        channel = dict(initial=1, edges=np.array([1.,2.]))
        self.assertEqual(d.sampled(channel,np.array([.9,1.,1.1,2.])).tolist(),[1,0,0,1])

    def test_constant_low_is_not_a_valid_command(self):
        frames=d.commands(np.zeros(96,dtype=np.uint8),np.arange(96)*40e-9)
        self.assertTrue(frames)
        self.assertTrue(all(f['end_bit']==0 and f['crc_ok'] is False for f in frames))


if __name__ == '__main__':
    unittest.main()
