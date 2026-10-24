import struct
import unittest
import protocol as p


def good(mode=0, pattern=1):
    x = dict.fromkeys(p.FIELDS, 0)
    size = 1120*1364*(5 if mode else 8)//4
    x.update(magic=p.MAGIC, schema=1, words=40, nonce=123, mode=mode,
        pattern=pattern, state=3, expected_bytes=size, frame=0x34000000,
        width=1120, height=1364, dma_bytes=size, frames=1, sensor_format=10,
        sensor_dt=0x30 if mode else 0x2B, p0fscr=0x30 if mode else 0x2B,
        vc0cfgr1=((2 if mode else 3)<<8)|1, primask=1, cpacr=0,
        reset_begin=10, reset_end=40810, terminal=p.DONE,
        pattern_register=0x121 if pattern else 0)
    return x


def pack(x):
    return struct.pack('<40I', *(x[k] for k in p.FIELDS))


class Tests(unittest.TestCase):
    def test_modes(self):
        for mode in (0,1):
            for pattern in (0,1):
                self.assertEqual(p.success(pack(good(mode,pattern)),123,mode,pattern)['mode'],mode)

    def test_bad_request(self):
        for args in ((0,0,0),(123,2,0),(123,0,2),(-1,0,0),(2**32,0,0)):
            with self.assertRaises(ValueError): p.request(*args)

    def test_exact_fields(self):
        fields='nonce mode pattern expected_bytes dma_bytes canary_mask frames errors sensor_format sensor_dt control ipsr primask cpacr terminal pattern_register'.split()
        for field in fields:
            with self.subTest(field=field):
                x=good();x[field]^=1
                with self.assertRaises(ValueError):p.success(pack(x),123,0,1)

    def test_context_and_active(self):
        for field,mask in [('ccr',0x10000),('ccr',0x20000),('fpccr',1),
                           ('systick',1),('p0ppcr',0x20),('p0fctcr',8),
                           ('cmsr1',0x8000),('csi_sr0',0x20000)]:
            with self.subTest(field=field,mask=mask):
                x=good();x[field]|=mask
                with self.assertRaises(ValueError):p.success(pack(x),123,0,1)

    def test_format_and_reset(self):
        for field,value in [('vc0cfgr1',0x201),('p0fscr',0x30),('reset_end',40809)]:
            x=good();x[field]=value
            with self.assertRaises(ValueError):p.success(pack(x),123,0,1)

    def test_short(self):
        with self.assertRaises(ValueError):p.decode(bytes(159))


if __name__=='__main__':unittest.main()
