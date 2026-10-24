"""Independent scalar CSI RAW10 decoding to check the numpy bench analyzer."""
import argparse
import array
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent


def decode_scalar(data):
    if len(data) % 5:
        raise ValueError('RAW10 requires complete five-byte groups')
    pixels = array.array('H')
    for i in range(0, len(data), 5):
        residual = data[i+4]
        for j in range(4):
            pixels.append(data[i+j]*4 + residual%4)
            residual //= 4
    if sys.byteorder != 'little':
        pixels.byteswap()
    return pixels.tobytes()


def self_test():
    for j in range(4):
        for value in range(1024):
            group = bytearray(5)
            group[j] = value // 4
            group[4] = (value % 4) * 4**j
            expected = array.array('H', [0]*4)
            expected[j] = value
            if sys.byteorder != 'little': expected.byteswap()
            assert decode_scalar(group) == expected.tobytes()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--packed',type=Path)
    p.add_argument('--padded',type=Path)
    p.add_argument('--out',type=Path)
    a=p.parse_args()
    self_test()
    if not a.packed:
        print('4096 scalar single-pixel-position/value vectors passed')
        return
    raw=a.packed.read_bytes();decoded=decode_scalar(raw)
    spec=importlib.util.spec_from_file_location('analyze_raw',ROOT/'analyze_raw.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    reference_numpy=module.unpack(raw).astype('<u2').tobytes()
    if decoded!=reference_numpy:raise ValueError('Independent decoders disagree')
    result=dict(packed_sha256=hashlib.sha256(raw).hexdigest(),pixels=len(decoded)//2,
        decoded_le16_sha256=hashlib.sha256(decoded).hexdigest(),
        independent_numpy_exact=True,scalar_vectors_passed=4096)
    if a.padded:
        expected=a.padded.read_bytes()
        if len(expected)!=len(decoded):raise ValueError('Padded reference length differs')
        result['reference_exact']=decoded==expected
        result['reference_sha256']=hashlib.sha256(expected).hexdigest()
        if decoded!=expected:raise ValueError('Padded reference differs')
    if a.out:a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
