"""Exact host-side request and success checks for the RAM RAW10 experiment."""
import struct

REQUEST = 0x343FD000
PROOF = 0x343FD100
MAGIC = 0x52505231
DONE = 0x5250444E
FIELDS = '''magic schema words nonce mode pattern state result expected_bytes
frame width height dma_bytes canary_mask frames errors sensor_format sensor_dt
p0ppcr vc0cfgr1 p0fscr p0fctcr cmsr1 csi_sr0 csi_sr1 post_frame_begin stop_end
ccr control ipsr primask fpccr cpacr systick reset_begin reset_end start_begin
start_end terminal pattern_register'''.split()
assert len(FIELDS) == 40


def request(nonce, mode, pattern):
    if not 1 <= nonce <= 0xFFFFFFFF or mode not in (0, 1) or pattern not in (0, 1):
        raise ValueError('Invalid nonce/mode/pattern')
    return struct.pack('<4I', 0x52505131, nonce, mode, pattern)


def decode(raw):
    if len(raw) != 160:
        raise ValueError('Incomplete RAW experiment proof')
    return dict(zip(FIELDS, struct.unpack('<40I', raw)))


def success(raw, nonce, mode, pattern):
    request(nonce, mode, pattern)
    p = decode(raw)
    size = 1120 * 1364 * (5 if mode else 8) // 4
    exact = dict(magic=MAGIC, schema=1, words=40, nonce=nonce, mode=mode,
        pattern=pattern, state=3, result=0, expected_bytes=size, frame=0x34000000,
        width=1120, height=1364, dma_bytes=size, canary_mask=0, frames=1,
        errors=0, sensor_format=10, sensor_dt=0x30 if mode else 0x2B,
        control=0, ipsr=0, primask=1, cpacr=0, terminal=DONE,
        pattern_register=0x121 if pattern else 0)
    if any(p[k] != v for k, v in exact.items()):
        raise ValueError('RAW proof exact field mismatch')
    if (p['ccr'] & 0x30000 or p['fpccr'] & 1 or p['systick'] & 3 or
        p['p0ppcr'] & 0x20 or p['p0fctcr'] & 8 or p['cmsr1'] & 0x8000 or
        p['csi_sr0'] & 0x20000 or p['p0fscr'] & 0x3F != exact['sensor_dt']):
        raise ValueError('RAW proof context/idle/format mismatch')
    # Original HAL selects ALLDT and the common datatype format (bits8..12).
    if p['vc0cfgr1'] != (((2 if mode else 3) << 8) | 1):
        raise ValueError('CSI format readback mismatch')
    if ((p['reset_end'] - p['reset_begin']) & 0xFFFFFFFF) < 40800:
        raise ValueError('Sensor reset pulse too short')
    return p
