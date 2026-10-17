"""Decode the PD0 fallback from Logic digital.csv. Purely offline.

Requires CRC-valid self-described packets. Never fills missing trace data or
labels partial output as complete. Completed 2048-byte traces can be supplied
to the existing offline ROM-event decoder separately.
"""
import argparse
import csv
import json
from pathlib import Path
import struct
import zlib

HEADER = struct.Struct('<4sBHIH')
TRACE_BASES = {0x10: (0x341037F0, 'secure'), 0x11: (0x241077F0, 'nonsecure')}


def load_edges(path, column):
    edges = []
    previous_time = None
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        if column not in reader.fieldnames or 'Time [s]' not in reader.fieldnames:
            raise ValueError(f'Missing expected CSV columns: {column}')
        for row in reader:
            time, level = float(row['Time [s]']), int(row[column])
            if level not in (0, 1) or (previous_time is not None and time < previous_time):
                raise ValueError('Invalid level or nonmonotonic time')
            previous_time = time
            if not edges or edges[-1][1] != level:
                edges.append((time, level))
    if not edges:
        raise ValueError(f'No data in {column}')
    return edges


def decode_frames(edges):
    lows = [(edges[i][0], edges[i+1][0]) for i in range(len(edges)-1)
            if edges[i][1] == 0 and edges[i+1][1] == 1]
    frames, rejected = [], []
    i = 0
    while i + 1 < len(lows):
        start, rise = lows[i]
        unit = (rise-start)/12
        gap = lows[i+1][0]-rise
        if unit <= 0 or not 3.2 <= gap/unit <= 4.8:
            i += 1
            continue

        def byte_at(index):
            value = 0
            for bit in range(8):
                j = index+bit
                if j >= len(lows): raise ValueError('truncated pulse stream')
                ratio = (lows[j][1]-lows[j][0])/unit
                if 0.65 <= ratio <= 1.4: digit = 0
                elif 2.4 <= ratio <= 3.7: digit = 1
                else: raise ValueError('invalid data pulse duration')
                value |= digit << bit
            return value

        header = bytearray()
        try:
            for offset in range(HEADER.size):
                header.append(byte_at(i+1+offset*8))
            magic, kind, seq, address, length = HEADER.unpack(header)
            if magic != b'BTD1':
                i += 1
                continue
            if length > 64: raise ValueError('payload length exceeds protocol bound')
            size = HEADER.size + length + 4
            raw = bytes(byte_at(i+1+offset*8) for offset in range(size))
            last = i+size*8
            for j in range(i+1, last):
                ratio = (lows[j+1][0]-lows[j][1])/unit
                if not 0.65 <= ratio <= 1.5:
                    raise ValueError('invalid inter-bit high interval')
            received = struct.unpack_from('<I',raw,len(raw)-4)[0]
            if zlib.crc32(raw[:-4]) != received: raise ValueError('CRC32 mismatch')
            frames.append({'start_s':start,'end_s':lows[last][1],
                           'unit_s':unit,'sequence':seq,'type':kind,
                           'address':address,'data_hex':raw[HEADER.size:-4].hex(),
                           'crc32':f'{received:08x}'})
            i = last+1
        except ValueError as exc:
            # Only report candidates whose magic is known; ordinary data can
            # resemble the sync ratio but cannot validate a complete packet.
            if bytes(header[:4]) == b'BTD1':
                rejected.append({'start_s':start,'reason':str(exc)})
            i += 1
    return frames, rejected


def inspect(path):
    frames, rejected = decode_frames(load_edges(path, 'Channel 1'))
    errors = []
    seq = [f['sequence'] for f in frames]
    if seq != list(range(len(frames))): errors.append('Missing, duplicated or reordered packet sequence')
    if not frames: errors.append('No CRC-valid BTD1 packets')
    if rejected: errors.append('One or more recognized frames failed validation')
    complete_marker = bool(frames and frames[-1]['type']==1 and
                           frames[-1]['address']==0xFFFFFFFF and frames[-1]['data_hex']=='')
    if not complete_marker: errors.append('No final completion checkpoint')
    pe0_high = None
    if frames:
        try:
            pe = load_edges(path, 'Channel 2')
            start, end = frames[0]['start_s'], frames[-1]['end_s']
            before = [level for time,level in pe if time <= start]
            pe0_high = bool(before and before[-1]==1 and
                           all(level==1 for time,level in pe if start < time <= end))
        except ValueError:
            pe0_high = False
        if not pe0_high: errors.append('PE0 was not observably high throughout the dump')
    recovered, trace_details = {}, {}
    for kind,(base,name) in TRACE_BASES.items():
        chunks = {}
        invalid = []
        for f in frames:
            if f['type'] != kind: continue
            offset = f['address']-base
            data = bytes.fromhex(f['data_hex'])
            if offset < 0 or offset >= 2048 or offset%64 or len(data)!=64 or offset in chunks:
                invalid.append(f['sequence'])
            else: chunks[offset] = data
        missing = [n for n in range(0,2048,64) if n not in chunks]
        if missing or invalid: errors.append(f'{name} trace incomplete or invalid')
        else: recovered[name] = b''.join(chunks[n] for n in range(0,2048,64))
        trace_details[name] = {'base':f'0x{base:08x}', 'received_bytes':sum(map(len,chunks.values())),
                               'missing_offsets':missing,'invalid_sequences':invalid,
                               'complete':not missing and not invalid}
    timer = [f for f in frames if f['type']==2 and f['address']==0x50000000 and len(f['data_hex'])==32]
    status = [f for f in frames if f['type']==4 and len(f['data_hex'])==56]
    if len(timer)!=1: errors.append('Expected exactly one timer snapshot packet')
    if len(status)!=1: errors.append('Expected exactly one debug readback packet')
    timer_words = list(struct.unpack('<4I',bytes.fromhex(timer[0]['data_hex']))) if len(timer)==1 else None
    status_words = list(struct.unpack('<7I',bytes.fromhex(status[0]['data_hex']))) if len(status)==1 else None
    return {'passed':not errors,'errors':errors,'packet_count':len(frames),
            'pe0_high_during_dump':pe0_high,'completion_checkpoint':complete_marker,
            'timer_words':timer_words,'timer_caveat':'Raw RCC_APB1ENR1, CNT, PSC, CPU CONTROL immediately after the marker path. CNT/PSC = 0xffffffff when skipped. Clock rate and origin are unqualified.',
            'debug_words':status_words,
            'register_readbacks':[{'sequence':f['sequence'],'address':f"0x{f['address']:08x}",
                                   'value':f"0x{int.from_bytes(bytes.fromhex(f['data_hex']), 'little'):08x}"}
                                  for f in frames if f['type']==5 and len(f['data_hex'])==8],
            'traces':trace_details,'rejected_frames':rejected,
            'frames':frames}, recovered


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('csv',type=Path)
    p.add_argument('--output',type=Path,required=True,help='New directory for report and complete trace binaries')
    args=p.parse_args()
    report, recovered=inspect(args.csv)
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'decode-report.json').write_text(json.dumps(report,indent=2)+'\n')
    for name,data in recovered.items(): (args.output/f'{name}-trace.bin').write_bytes(data)
    print(json.dumps({k:v for k,v in report.items() if k!='frames'},indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__=='__main__': main()
