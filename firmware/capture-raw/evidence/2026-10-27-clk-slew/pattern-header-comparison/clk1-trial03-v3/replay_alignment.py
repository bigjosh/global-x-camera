"""Replay one CRC-failed SD sector's symbol-deletion alignment, offline only.

Place this script beside historical-header.bin and untrusted-current-header.bin, then run
python replay_alignment.py.  These are retained RAM/media artifacts, not a new
successful SD read or a waveform; an exact match does not identify root cause.
"""

import argparse
import binascii
import difflib
import hashlib
import json
from pathlib import Path


def symbols(data):
    return [n for b in data for n in (b >> 4, b & 15)]


def pack(values):
    assert len(values) % 2 == 0
    return bytes((values[i] << 4) | values[i + 1]
                 for i in range(0, len(values), 2))


def crc16(bits):
    value = 0
    for bit in bits:
        feedback = ((value >> 15) & 1) ^ bit
        value = (value << 1) & 0xffff
        if feedback:
            value ^= 0x1021
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path,
                        default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    old_bytes = (args.directory / 'historical-header.bin').read_bytes()
    new_bytes = (args.directory / 'untrusted-current-header.bin').read_bytes()
    assert len(old_bytes) == len(new_bytes) == 512, 'Expected two 512-byte sectors'
    old, new = symbols(old_bytes), symbols(new_bytes)

    deleted = []
    appended = []
    for tag, i, j, k, l in difflib.SequenceMatcher(
            None, old, new, autojunk=False).get_opcodes():
        if tag == 'equal':
            continue
        if tag == 'delete':
            deleted.extend(range(i, j))
        elif tag == 'insert' and i == j == len(old):
            appended.extend(new[k:l])
        else:
            raise AssertionError('Alignment needs substitutions or non-tail insertions')
    assert len(deleted) == len(appended) == 8, 'Expected eight omitted/tail symbols'

    lane_crc = []
    for lane in range(4):
        bits = [(n >> lane) & 1 for n in old]
        crc = crc16(bits)
        lane_bytes = bytes(sum(bits[i + k] << (7 - k) for k in range(8))
                           for i in range(0, len(bits), 8))
        assert crc == binascii.crc_hqx(lane_bytes, 0), 'Independent CRC check failed'
        lane_crc.append(crc)
    crc_wire = [sum(((lane_crc[lane] >> bit) & 1) << lane
                    for lane in range(4)) for bit in range(15, -1, -1)]
    omitted = set(deleted)
    model = [n for i, n in enumerate(old) if i not in omitted] + crc_wire[:8]
    assert model == new, 'Deletion plus computed CRC prefix does not match'
    assert appended == crc_wire[:8]

    report = {
        'hardware_access': False,
        'historical_header_sha256': hashlib.sha256(old_bytes).hexdigest(),
        'failed_header_sha256': hashlib.sha256(new_bytes).hexdigest(),
        'raw_differing_bytes': sum(a != b for a, b in zip(old_bytes, new_bytes)),
        'exact_prefix_bytes': next((i for i, (a, b) in enumerate(
            zip(old_bytes, new_bytes)) if a != b), 512),
        'deleted_reference_nibble_indices_zero_based': deleted,
        'deleted_reference_nibble_values': [old[i] for i in deleted],
        'remaining_data_nibbles_exactly_equal': len(old) - len(deleted),
        'lane_crc16_hex': [f'{v:04x}' for v in lane_crc],
        'computed_full_crc_wire_hex': pack(crc_wire).hex(),
        'observed_last_four_bytes_hex': new_bytes[-4:].hex(),
        'entire_failed_512_bytes_equal_deletion_plus_crc_prefix_model': True,
        'limitation': ('An exact eight-symbol deletion alignment, not root-cause '
                       'proof. Repeated symbols may make local deletion positions '
                       'ambiguous. No waveform or fresh valid media read is implied.'),
    }
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
