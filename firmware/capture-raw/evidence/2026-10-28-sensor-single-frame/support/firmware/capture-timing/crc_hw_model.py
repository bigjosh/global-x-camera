"""Offline model of RM0486 CRC word/byte input reversal, checked against zlib.

This validates arithmetic and byte order, not peripheral access or silicon.
Use CRC_POL=0x04C11DB7, CRC_INIT=0xFFFFFFFF, RTYPE_IN/OUT=0,
REV_IN=3 for little-endian words (1 for final byte writes), REV_OUT=1.
XOR the read result with 0xFFFFFFFF. REV_OUT is a two-bit field on STM32N6:
setting the whole field mask (3) does NOT enable output bit reversal.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import zlib


def reverse_bits(value: int, width: int) -> int:
    return int(f"{value:0{width}b}"[::-1], 2)


def write_dr(crc: int, value: int, width: int) -> int:
    value = reverse_bits(value, width)
    for shift in range(width - 1, -1, -1):
        feedback = (crc >> 31) ^ ((value >> shift) & 1)
        crc = (crc << 1) & 0xFFFFFFFF
        if feedback:
            crc ^= 0x04C11DB7
    return crc


def hardware_model(data: bytes) -> int:
    crc = 0xFFFFFFFF
    words_end = len(data) & ~3
    for index in range(0, words_end, 4):
        crc = write_dr(crc, int.from_bytes(data[index:index + 4], "little"), 32)
    for value in data[words_end:]:
        crc = write_dr(crc, value, 8)
    return reverse_bits(crc, 32) ^ 0xFFFFFFFF


def check(data: bytes) -> dict:
    actual = hardware_model(data)
    expected = zlib.crc32(data) & 0xFFFFFFFF
    assert actual == expected, (len(data), hex(actual), hex(expected))
    return {"bytes": len(data), "crc32": f"0x{actual:08X}"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", nargs="*", type=Path)
    args = parser.parse_args()
    assert hardware_model(b"123456789") == 0xCBF43926
    cases = [bytes((i * 137 + 29) & 255 for i in range(n)) for n in range(258)]
    for data in cases:
        check(data)
    print(json.dumps({
        "known_answer_123456789": check(b"123456789"),
        "deterministic_lengths_checked": [0, 257],
        "binaries": {str(path): check(path.read_bytes()) for path in args.binary},
        "scope": "Offline arithmetic only; hardware known-answer test still required.",
    }, indent=2))


if __name__ == "__main__":
    main()
