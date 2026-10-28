"""Offline native-SD four-bit packet/CRC inspection of Saleae binary exports.

No instrument imports or commands. All packet failures are retained, never
filtered into a pass. A decoded CRC agrees only with the analyzer's threshold
samples; it cannot prove analog margins at the card/MCU input.
"""
import argparse
import binascii
import hashlib
import json
import struct
from pathlib import Path

import numpy as np


def digital(path):
    path = Path(path)
    with path.open('rb') as fh:
        raw = fh.read(44)
    magic, version, kind, initial, start, end, count = struct.unpack_from('<8siiIddQ', raw)
    assert magic == b'<SALEAE>' and version == 0 and kind == 0
    assert initial in (0, 1) and path.stat().st_size == 44 + count * 8
    edges = np.memmap(path, dtype='<f8', mode='r', shape=(count,), offset=44) if count else np.array([],dtype='<f8')
    return dict(initial=initial, start=start, end=end, edges=edges)


def sampled(channel, times):
    return (channel['initial'] ^ (np.searchsorted(channel['edges'], times, side='right') & 1)).astype(np.uint8)


def crc7(raw):
    crc = 0
    for byte in raw:
        for bit in range(7, -1, -1):
            top = ((crc >> 6) ^ (byte >> bit)) & 1
            crc = (crc << 1) & 127
            if top:
                crc ^= 9
    return crc


def bits_int(bits):
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return value


def commands(bits, times, limit=10000):
    """Parse native commands and 48/136-bit replies, preserving bad CRCs.

    R3/R4 have no meaningful CRC; R2 is retained without claiming a CRC check.
    A malformed CMD stream can lose framing, so records are observations.
    """
    frames = []
    pos = 0
    pending = None
    lows = np.flatnonzero(bits == 0)
    while pos + 48 <= len(bits) and len(frames) < limit:
        low_index = int(np.searchsorted(lows, pos))
        if low_index == len(lows):
            break
        pos = int(lows[low_index])
        if pos + 48 > len(bits):
            break
        host = bool(bits[pos + 1])
        length = 136 if not host and pending in (2, 9, 10) else 48
        if pos + length > len(bits):
            break
        packet = np.packbits(bits[pos:pos + length]).tobytes()
        index = packet[0] & 63
        no_crc = not host and pending in (1, 5, 41)
        frame = dict(clock_index=pos, end_clock_index=pos + length - 1,
                     time_s=float(times[pos]), end_time_s=float(times[pos + length - 1]),
                     direction='host' if host else 'card', index=index,
                     response_to=None if host else pending, length_bits=length,
                     raw_hex=packet.hex(), end_bit=int(bits[pos + length - 1]),
                     crc_ok=None if length != 48 or no_crc else bool(bits[pos + length - 1]) and (packet[-1] >> 1) == crc7(packet[:-1]))
        if length == 48:
            frame['argument_hex'] = f'0x{int.from_bytes(packet[1:5], "big"):08x}'
        frames.append(frame)
        pending = index if host else None
        pos += length
    return frames


def packet_at(lanes, times, pos):
    """512 bytes; one start, 1024 payload, 16 per-lane CRC, one end clock."""
    if pos + 1042 > lanes.shape[1]:
        return dict(clock_index=pos, time_s=float(times[pos]), truncated=True)
    payload_bits = lanes[:, pos + 1:pos + 1025]
    nibbles = sum(payload_bits[lane].astype(np.uint8) << lane for lane in range(4))
    payload = ((nibbles[::2] << 4) | nibbles[1::2]).tobytes()
    calculated = [binascii.crc_hqx(np.packbits(payload_bits[lane]).tobytes(), 0) for lane in range(4)]
    received = [bits_int(lanes[lane, pos + 1025:pos + 1041]) for lane in range(4)]
    return dict(clock_index=pos, end_clock_index=pos + 1041, time_s=float(times[pos]),
                end_time_s=float(times[pos + 1041]), truncated=False,
                start_bits=lanes[:, pos].tolist(), end_bits=lanes[:, pos + 1041].tolist(),
                crc_calculated=calculated, crc_received=received,
                crc_ok_by_lane=[a == b for a, b in zip(calculated, received)],
                payload_sha256=hashlib.sha256(payload).hexdigest(), payload_prefix_hex=payload[:16].hex())


def transactions(frames, lanes, times, max_packets=256):
    """Associate first data candidates with CMD17/18/24/25 responses.

    Uses all-four-low start candidate and fixed block geometry, not CRC-based
    resynchronization. Leaves invalid first candidates visible. CRC status on
    DAT0 is interpreted after writes; all trailing samples are also retained.
    """
    results = []
    for fi, frame in enumerate(frames):
        if frame['direction'] != 'card' or frame['response_to'] not in (17, 18, 24, 25):
            continue
        command = frame['response_to']
        begin = frame['end_clock_index'] + 1
        stop = len(times)
        for nxt in frames[fi + 1:]:
            if nxt['direction'] == 'host' and nxt['crc_ok'] and nxt['index'] == 12:
                stop = nxt['clock_index']
                break
        item = dict(command=command, response_time_s=frame['time_s'], response_crc_ok=frame['crc_ok'],
                    search_begin_clock=begin, search_end_clock=stop, packets=[])
        pos = begin
        all_low = np.flatnonzero(np.all(lanes[:, begin:stop] == 0, axis=0)) + begin
        packet_limit = 1 if command in (17, 24) else max_packets
        while pos < stop and len(item['packets']) < packet_limit:
            candidate_index = int(np.searchsorted(all_low, pos))
            if candidate_index == len(all_low):
                break
            pos = int(all_low[candidate_index])
            packet = packet_at(lanes, times, pos)
            if not packet['truncated'] and packet['end_clock_index'] >= stop:
                packet['interrupted_by_cmd12'] = True
                packet['qualification'] = 'Extends into explicit STOP; CRC failure is not a complete-block fault'
            item['packets'].append(packet)
            if packet['truncated']:
                break
            pos = packet['end_clock_index'] + 1
            if command in (24, 25):
                tail_stop = min(stop, pos + 64)
                tail = lanes[:, pos:tail_stop]
                packet['postpacket_dat0_bits'] = ''.join(str(int(x)) for x in tail[0])
                # A native write CRC token is 0,status[2:0],1 on DAT0.
                # DAT1..3 stay high. Preserve every candidate in this window.
                token_candidates = []
                for at in range(max(0, tail.shape[1] - 4)):
                    word = tail[0, at:at + 5]
                    if word[0] == 0 and word[4] == 1 and np.all(tail[1:, at:at + 5] == 1):
                        status = bits_int(word[1:4])
                        if status in (2, 5, 6):
                            token_candidates.append(dict(clock_index=pos + at, time_s=float(times[pos + at]),
                                status=status, meaning={2:'accepted', 5:'crc_error', 6:'write_error'}[status]))
                packet['crc_status_candidates'] = token_candidates
                if token_candidates:
                    token = token_candidates[0]
                    after = token['clock_index'] + 5
                    # Diagnostic only: busy interval includes quantized sampling.
                    lows = np.flatnonzero(lanes[0, after:min(stop, after + 8)] == 0)
                    if len(lows):
                        busy_start = after + int(lows[0])
                        highs = np.flatnonzero(lanes[0, busy_start:stop] == 1)
                        if len(highs):
                            busy_end = busy_start + int(highs[0])
                            packet['observed_busy'] = dict(start_s=float(times[busy_start]),
                                end_s=float(times[busy_end]), duration_s=float(times[busy_end] - times[busy_start]))
                    pos = after
        item['packet_limit_reached'] = len(item['packets']) == packet_limit
        results.append(item)
    return results


def analyze(folder, clock, cmd, dat, offset_ns, max_packets, start_s=None, end_s=None, cmd_offset_ns=None, glitch_filter_ns=None):
    files = {ch: digital(Path(folder) / f'digital_{ch}.bin') for ch in set([clock, cmd] + dat)}
    clk = files[clock]
    clock_edges = clk['edges']
    filter_record = None
    if glitch_filter_ns is not None:
        # Counterfactual offline diagnostic only; raw source remains untouched.
        # Remove both transitions bounding a narrow pulse, no CRC-based choice.
        widths = np.diff(clock_edges)
        candidates = np.flatnonzero(widths <= glitch_filter_ns * 1e-9 + 1e-14)
        remove = np.zeros(len(clock_edges),dtype=bool)
        for index in candidates:
            if not remove[index]:
                remove[index:index+2] = True
        filter_record = dict(threshold_ns=glitch_filter_ns,removed_edge_pairs=int(remove.sum())//2,
                             qualification='Counterfactual pulse filtering; not proof of what the card sampled')
        clock_edges = clock_edges[~remove]
    rising = clock_edges[0 if clk['initial'] == 0 else 1::2]
    if start_s is not None:
        rising = rising[np.searchsorted(rising,start_s):]
    if end_s is not None:
        rising = rising[:np.searchsorted(rising,end_s,side='right')]
    times = rising + offset_ns * 1e-9
    command_bits = sampled(files[cmd], rising + (offset_ns if cmd_offset_ns is None else cmd_offset_ns) * 1e-9)
    lane_bits = np.stack([sampled(files[ch], times) for ch in dat])
    frames = commands(command_bits, rising) if len(files[cmd]['edges']) else []
    # Same-tick transitions are ambiguous. Offset sweeps must be compared rather
    # than silently selecting whichever decode happens to pass.
    near = {}
    for name, ch in [('CMD', cmd)] + [(f'DAT{i}', ch) for i, ch in enumerate(dat)]:
        edges = files[ch]['edges']
        if len(edges):
            ix = np.searchsorted(edges, rising)
            left = np.abs(rising - edges[np.maximum(0, ix - 1)])
            right = np.abs(rising - edges[np.minimum(len(edges) - 1, ix)])
            distance = np.minimum(left, right)
            near[name] = {f'within_{ns}ns': int(np.sum(distance <= ns * 1e-9 + 1e-14)) for ns in (0, 2, 4, 8, 10)}
    periods = np.diff(rising)
    return dict(schema=1, channel_map=dict(CLK=clock, CMD=cmd, DAT0=dat[0], DAT1=dat[1], DAT2=dat[2], DAT3=dat[3]),
                offset_ns=offset_ns, clock_rising_count=len(rising),
                cmd_offset_ns=offset_ns if cmd_offset_ns is None else cmd_offset_ns,
                command_channel_edge_count=len(files[cmd]['edges']),
                counterfactual_clock_filter=filter_record,
                requested_time_window_s=[start_s,end_s],
                median_clock_period_s=float(np.median(periods)) if len(periods) else None,
                cmd_crc_good=sum(f['crc_ok'] is True for f in frames),
                cmd_crc_bad=sum(f['crc_ok'] is False for f in frames),
                transitions_near_clock_rising=near, commands=frames,
                transactions=transactions(frames, lane_bits, rising, max_packets),
                limitations=['Native SD SDR only, 512-byte four-bit data blocks.',
                    'Start candidates are not CRC-filtered. Framing after severe signal corruption may be invalid.',
                    'No analog voltage/setup/hold qualification; logic threshold samples only.',
                    'CRC status may contain multiple candidates; retain raw trailing bits.',
                    'R2 and R3/R4 response CRC not validated; no report upgrades absence of CRC to a pass.'])


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('binary_dir', type=Path)
    p.add_argument('--clock', type=int, default=2)
    p.add_argument('--cmd', type=int, default=3)
    p.add_argument('--dat', type=int, nargs=4, default=[7, 4, 5, 1], metavar=('D0','D1','D2','D3'))
    p.add_argument('--offset-ns', type=float, default=0)
    p.add_argument('--max-packets', type=int, default=256)
    p.add_argument('--start-s', type=float)
    p.add_argument('--end-s', type=float)
    p.add_argument('--cmd-offset-ns', type=float)
    p.add_argument('--glitch-filter-ns', type=float)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    assert len(set([a.clock, a.cmd] + a.dat)) == 6
    result = analyze(a.binary_dir, a.clock, a.cmd, a.dat, a.offset_ns, a.max_packets,a.start_s,a.end_s,a.cmd_offset_ns,a.glitch_filter_ns)
    a.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(command_frames=len(result['commands']), cmd_crc_good=result['cmd_crc_good'],
                         cmd_crc_bad=result['cmd_crc_bad'], transactions=len(result['transactions']),
                         packets=sum(len(t['packets']) for t in result['transactions']))))
