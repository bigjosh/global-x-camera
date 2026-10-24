"""Offline MIPI RAW10 decode, optional padded16 reference and preview."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image

WIDTH, HEIGHT = 1120, 1364
PIXELS = WIDTH * HEIGHT
PACKED_BYTES = PIXELS * 5 // 4


def unpack(raw):
    if len(raw) != PACKED_BYTES:
        raise ValueError('Expected exactly 1,909,600 RAW10 payload bytes')
    a = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 5).astype(np.uint16)
    out = np.empty((len(a), 4), dtype=np.uint16)
    for i in range(4):
        out[:, i] = (a[:, i] << 2) | ((a[:, 4] >> (2 * i)) & 3)
    return out.reshape(HEIGHT, WIDTH)


def pack(values):
    a = np.asarray(values, dtype=np.uint16).reshape(-1, 4)
    if np.any(a > 1023):
        raise ValueError('Input outside RAW10')
    out = np.zeros((len(a), 5), dtype=np.uint8)
    out[:, :4] = a >> 2
    for i in range(4):
        out[:, 4] |= ((a[:, i] & 3) << (2 * i)).astype(np.uint8)
    return out.tobytes()


def analyze(path, layout, reference=None):
    raw = path.read_bytes()
    if layout == 'packed':
        values = unpack(raw)
        if pack(values) != raw:
            raise ValueError('Packed roundtrip failed')
    else:
        if len(raw) != PIXELS * 2:
            raise ValueError('Wrong padded16 frame size')
        values = np.frombuffer(raw, dtype='<u2').reshape(HEIGHT, WIDTH)
        if np.any(values > 1023):
            raise ValueError('Padded16 frame has bits above bit9 set')
    result = dict(path=str(path), layout=layout, bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(), width=WIDTH, height=HEIGHT,
        decoded_le16_sha256=hashlib.sha256(values.astype('<u2').tobytes()).hexdigest(),
        minimum=int(values.min()), maximum=int(values.max()), mean=float(values.mean()),
        unique_samples=int(np.unique(values).size),
        low_two_bit_histogram=np.bincount((values.ravel() & 3), minlength=4).tolist())
    if reference:
        expected = np.frombuffer(reference.read_bytes(), dtype='<u2')
        if expected.size != PIXELS:
            raise ValueError('Reference size differs')
        mismatch = np.flatnonzero(values.ravel() != expected)
        result.update(reference=str(reference), mismatch_pixels=int(mismatch.size),
            exact_pixels_equal=not bool(mismatch.size), first_mismatches=mismatch[:16].tolist())
    return result, values


def self_test():
    # Known group exercises all low-bit positions, independently of pack().
    raw = bytes([0x00, 0x55, 0xAA, 0xFF, 0xE4]) * (PIXELS // 4)
    values = unpack(raw)
    assert values.ravel()[:4].tolist() == [0, 341, 682, 1023]
    assert pack(values) == raw
    sweep = (np.arange(PIXELS, dtype=np.uint32) % 1024).astype(np.uint16).reshape(HEIGHT, WIDTH)
    assert np.array_equal(unpack(pack(sweep)), sweep)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--input', type=Path)
    p.add_argument('--layout', choices=['packed', 'padded16'])
    p.add_argument('--reference', type=Path)
    p.add_argument('--out', type=Path)
    p.add_argument('--self-test', action='store_true')
    a = p.parse_args()
    if a.self_test:
        self_test()
        print('RAW10 known-group and full-frame ramp roundtrips passed')
    if a.input:
        if not a.layout or not a.out:
            p.error('--input requires --layout and --out')
        a.out.mkdir(parents=True, exist_ok=False)
        result, values = analyze(a.input, a.layout, a.reference)
        (a.out / 'analysis.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        Image.fromarray((values >> 2).astype(np.uint8)).save(a.out / 'preview.png')
        print(json.dumps(result))
