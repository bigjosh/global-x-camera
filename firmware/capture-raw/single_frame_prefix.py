"""Narrow audit for the reviewed minimal single-frame stage-one image.

Normal explicit-STOP builds retain their older checker unchanged. The new
unrelocated prefix is pinned in full, then only two ELF-mapped CRC data words
may be relocated. No recovery instruction, recovery literal or error-engine
byte is waived by this selector.
"""
import hashlib
from pathlib import Path
import re
import struct

HERE=Path(__file__).resolve().parent
REFERENCE=HERE/'evidence/2026-10-28-ethernet-powerdown/flash-candidate/staged/stage1.bin'
REFERENCE_SHA='2b9724bc4b60af52b1c4ab45e1b232578e9640efc3a30a57772a810d99c3f344'
UNRELOCATED_SHA='41216a3b2f921e80f401da7cb82806e350149c50fc132c2266ae3706dd2c2de7'
CRC_OFFSETS=(0xC9C,0x1358)


def check(folder,prefix):
    reference=REFERENCE.read_bytes()
    if hashlib.sha256(reference).hexdigest()!=REFERENCE_SHA:
        raise ValueError('Single-frame normal prefix reference changed')
    if len(prefix)!=6720 or hashlib.sha256(prefix).hexdigest()!=UNRELOCATED_SHA:
        raise ValueError('Unreviewed single-frame prefix bytes')
    if prefix[:0x67A]!=reference[:0x67A]:
        raise ValueError('Single-frame recovery instruction/vector bytes changed')
    # Two post-recovery loader literals point into the unchanged table shifted
    # eight bytes by the sensor context burst. There are no instruction changes
    # below the existing stage-two-length boundary at offset0xAFE.
    normalized=bytearray(prefix[:0xAFE])
    for offset,old,new in ((0x988,0x341817F0,0x341817F8),
                           (0x990,0x34181800,0x34181808)):
        if struct.unpack_from('<I',reference,offset)[0]!=old or struct.unpack_from('<I',prefix,offset)[0]!=new:
            raise ValueError('Unexpected single-frame table pointer')
        struct.pack_into('<I',normalized,offset,old)
    if normalized!=reference[:0xAFE] or prefix[0xAFE:0xB02]!=reference[0xAFE:0xB02]:
        raise ValueError('Single-frame early loader instruction changed')
    if prefix[0x1420:0x1A40]!=reference[0x1420:0x1A40]:
        raise ValueError('Single-frame fixed error bridge/engine changed')
    if prefix[0x1390:0x1394]!=bytes((1,0,4,0)):
        raise ValueError('Single-frame context byte table changed')
    listing=(Path(folder)/'stage1.lst').read_text()
    if not re.search(r'34180a76:.*\bbl\s+3418078c <recovery_gpio_park>',listing):
        raise ValueError('Single-frame recovery branch changed')
    literals=set()
    for line in listing.splitlines():
        match=re.match(r'([0-9a-f]+):.*\[pc,.*@\s*\(?([0-9a-f]+)',line)
        if match and 0x34180790<=int(match[1],16)<=0x34180A76:
            offset=int(match[2],16)-0x34180400
            if not 0<=offset<=len(prefix)-4 or prefix[offset:offset+4]!=reference[offset:offset+4]:
                raise ValueError('Single-frame recovery literal changed')
            literals.add(offset)
    if len(literals)!=20:
        raise ValueError('Single-frame recovery literal set changed')
    return dict(schema=1,unrelocated_sha256=UNRELOCATED_SHA,reference_sha256=REFERENCE_SHA,
        guard_bytes_equal=True,recovery_literal_offsets=sorted(literals),
        error_bridge_engine_equal=True,post_guard_table_pointer_offsets=[0x988,0x990],
        crc_literal_offsets=list(CRC_OFFSETS),context_table_offset=0x1390,
        context_table_bytes='01000400',early_load_bytes=15804)
