"""Offline protocol checks with drift, corruption and truncation. No hardware."""
import csv
import importlib.util
from pathlib import Path
import random
import struct
import tempfile
import zlib

SPEC=importlib.util.spec_from_file_location('pd0decode',Path(__file__).with_name('decode.py'))
decode=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(decode)


def frames():
    values=[]
    def add(kind,address,payload=b''):
        raw=struct.pack('<4sBHIH',b'BTD1',kind,len(values),address,len(payload))+payload
        values.append(raw+struct.pack('<I',zlib.crc32(raw)))
    add(2,0x50000000,struct.pack('<4I',1,15000,149,0))
    buffers={}
    for kind,base in ((0x10,0x341037F0),(0x11,0x241077F0)):
        data=bytes((n*7+kind)&255 for n in range(2048))
        buffers['secure' if kind==0x10 else 'nonsecure']=data
        for offset in range(0,2048,64):
            add(3,base+offset)
            add(kind,base+offset,data[offset:offset+64])
    add(1,0x100)
    add(4,0,struct.pack('<7I',0xB451B400,0xB4,0x6000000,0x44424733,0x80100001,1,1))
    add(1,0xFFFFFFFF)
    return values,buffers


def waveform(path, packets):
    rng=random.Random(371)
    rows=[(0,0,0),(0.115,1,0),(0.1150004,1,1)]
    now=.5
    for packet in packets:
        unit=.000025*rng.uniform(.9,1.1)
        def pulse(n):
            nonlocal now
            rows.append((now,0,1))
            now+=unit*n*rng.uniform(.98,1.02)
            rows.append((now,1,1))
        pulse(12)
        now+=4*unit
        for byte in packet:
            for bit in range(8):
                pulse(3 if byte&(1<<bit) else 1)
                now+=unit*rng.uniform(.98,1.02)
        now+=16*unit
    rows.append((now+.2,1,1))
    with path.open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['Time [s]','Channel 1','Channel 2']);w.writerows(rows)


def main():
    packets,expected=frames()
    with tempfile.TemporaryDirectory(prefix='pd0-offline-') as folder:
        path=Path(folder)/'digital.csv'
        waveform(path,packets)
        report,data=decode.inspect(path)
        assert report['passed'],report['errors']
        assert data==expected
        corrupt=packets.copy()
        damaged=bytearray(corrupt[2]);damaged[15]^=0x08
        corrupt[2]=bytes(damaged)
        waveform(path,corrupt)
        report,data=decode.inspect(path)
        assert not report['passed'] and report['rejected_frames']
        assert 'secure' not in data and data['nonsecure']==expected['nonsecure']
        waveform(path,packets[:-1]+[packets[-1][:-1]])
        report,data=decode.inspect(path)
        assert not report['passed'] and not report['completion_checkpoint']
        assert data==expected
        waveform(path,packets[:66])
        report,data=decode.inspect(path)
        assert not report['passed'] and 'nonsecure' not in data
    print('PASS: full traces with timing drift; CRC corruption; truncated completion; partial dump')

if __name__=='__main__': main()
