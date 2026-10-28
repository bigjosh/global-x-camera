"""Offline host refusal tests; fake debugger only."""
import struct
import unittest
from unittest import mock
import protocol as p
import run as r

class Fake:
    def __init__(self,sp=0x343b0000,control=0,ccr=513):self.sp=sp;self.control=control;self.ccr=ccr;self.uploads=[]
    def call(self,*args,**kwargs):
        return f'PC = 0x34320016\nXPSR = 0x01000000\nCONTROL = 0x{self.control:x}\nPRIMASK = 0x01\nFAULTMASK = 0x00\nSP = 0x{self.sp:x}\nMSP = 0x{self.sp:x}\n'
    def upload(self,address,size,name):
        self.uploads.append(address)
        return {0xe000ed14:struct.pack('<I',self.ccr),0xe000ef34:bytes(4),r.LOAD:b'code'}[address]

class RunnerTests(unittest.TestCase):
    def test_high_stack_observed(self):
        result=r.exact_code_context(Fake(),b'code',r.LOAD+0x16,'test')
        self.assertEqual(result['stack']['MSP'],0x343b0000)
    def test_low_stack_refused_before_memory_access(self):
        fake=Fake(sp=0x341b8000)
        with self.assertRaises(ValueError):r.exact_code_context(fake,b'code',r.LOAD+0x16,'test')
        self.assertEqual(fake.uploads,[])
    def test_active_fp_or_cache_refused(self):
        for fake in (Fake(control=12),Fake(ccr=0x30201)):
            with self.assertRaises(ValueError):r.exact_code_context(fake,b'code',r.LOAD+0x16,'test')
    def test_request_limits(self):
        self.assertEqual(len(p.request(2,1,3,12,13,14)),64)
        for args in ((2,0),(2,1,4),(2,1,1,0,0,0),(2,1,1,0,0,3200001)):
            with self.assertRaises(ValueError):p.request(*args)
    def test_chunk_monotonicity_and_boundaries(self):
        valid=struct.pack('<IIQQQ',32768,1,100,40,60)+struct.pack('<IIQQQ',40000,2,200,80,120)
        self.assertEqual(len(p.chunks(valid,2)),2)
        for bad in (struct.pack('<IIQQQ',32767,1,100,40,60)+valid[32:],
                    valid[:32]+struct.pack('<IIQQQ',40000,2,90,30,60)):
            with self.assertRaises(ValueError):p.chunks(bad,2)

if __name__=='__main__':unittest.main()
