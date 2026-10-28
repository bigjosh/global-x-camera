"""Offline exact RAW-slot readback comparison and nominal cycle-counter timing."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import zlib

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
spec=importlib.util.spec_from_file_location('raw_format',ROOT/'firmware/raw-slots/raw_slots.py')
fmt=importlib.util.module_from_spec(spec);spec.loader.exec_module(fmt)


def sha(data): return hashlib.sha256(data).hexdigest()


def timing(proof):
    # Consecutive named intervals are less than a single 10.737s CYCCNT wrap.
    pairs={'camera_arm_to_frame':('arm','frame_done'),
        'sd_init':('sd_begin','sd_ready'),'scan':('sd_ready','scan_done'),
        'payload':('first_write','payload_done'),'commit_tail':('payload_done','commit_done'),
        'deinit':('commit_done','deinit_done'),'operation':('begin','end')}
    out={name:((proof[end]-proof[start])&0xffffffff)/400000000
        for name,(start,end) in pairs.items() if proof.get(start) and proof.get(end)}
    sleeping=bool(proof.get('flags',0)&32)
    out['dma_sleep_enabled']=sleeping
    out['basis']=('Nominal400MHz processor-clock seconds. WFI can stop DWT: payload, commit_tail and operation '
        'intervals exclude actual sleeping time and are NOT elapsed durations. Use external Saleae/JS '
        'timing for wall time and energy; overlapping intervals are not additive.' if sleeping else
        'Nominal400MHz DWT, not external power/reset timing; overlapping intervals are not additive')
    out['intervals_may_exclude_sleep']=['payload','commit_tail','operation'] if sleeping else []
    out['energy_source']='Integrate measured Joulescope power over external wall-time boundaries; never multiply by DWT durations'
    return out


def verify(readback,capture):
    readback,capture=Path(readback),Path(capture)
    vol=(readback/'volume.bin').read_bytes();head=(readback/'header.bin').read_bytes()
    raw=(readback/'payload-padded.bin').read_bytes();expected=(capture/'frame.bin').read_bytes()
    for data in (vol,head):
        if len(data)!=512 or zlib.crc32(data[:508])!=struct.unpack_from('<I',data,508)[0]:
            raise ValueError('Invalid on-card header CRC')
    if (vol[:8]!=b'GXRWVOL1' or head[:8]!=b'GXRAWSL1' or
            struct.unpack_from('<I',head,12)[0]!=fmt.FULL or head[16:24]!=vol[16:24]):
        raise ValueError('Invalid volume/FULL-slot identity')
    if len(raw)!=3730*512 or len(expected)!=fmt.PAYLOAD_BYTES or raw[fmt.PAYLOAD_BYTES:]!=bytes(160):
        raise ValueError('Payload/tail length/padding differs')
    if raw[:fmt.PAYLOAD_BYTES]!=expected:
        n=sum(a!=b for a,b in zip(raw,expected))
        raise ValueError(f'{n} of {len(expected)} camera bytes differ from SD')
    proof=json.loads((capture/'verified.json').read_text())['proof']
    slot=struct.unpack_from('<I',head,24)[0]
    if slot!=proof['slot'] or struct.unpack_from('<I',head,32)[0]!=proof['payload_lba']:
        raise ValueError('Capture and slot identity differ')
    return dict(passed=True,slot=slot,bytes=len(expected),pixels=1120*1364,
        exact_camera_byte_comparison=True,header_crcs_valid=True,padding_zero=True,
        payload_sha256=sha(expected),timing_seconds=timing(proof))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--readback',type=Path,required=True);p.add_argument('--capture',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=verify(a.readback,a.capture)
    a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
