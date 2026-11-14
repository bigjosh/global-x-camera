"""Let the built capture receiver accept the exposure chosen by the knob.

The reviewed receiver reads back the exposure the sensor applied and fails the
photo with error 0x90 unless it is exactly 1428 lines:

    movw  r3, #1428
    cmp   r6, r3
    beq.n continue
    movs  r3, #0x90      reached only when the exposure differs
    b.n   fail

The receiver cannot be rebuilt here: its layout is pinned to the output of the
original compiler. This module edits the built bytes instead. The conditional
branch becomes unconditional, which leaves the two instructions after it
unreachable. Those four unreachable bytes are then chosen so that the CRC-32
of the late-loaded code range is unchanged. The checksum the loader compares
against, the early receiver and the boot prefix all stay exactly as reviewed.
Five bytes of flash change in total.

Pure Python, no hardware access.
"""
import struct
import zlib

ASSERTION = bytes.fromhex('40f29453' '9e42' '2fd0' '9023' '84e7')
BRANCH = 6           # offset of the beq.n halfword within ASSERTION
SPARE = 8            # offset of the four bytes that become unreachable
BEQ_N, B_N = 0xD0, 0xE0   # high byte: conditional (EQ) and unconditional short branch

_TABLE = []
for _n in range(256):
    _c = _n
    for _ in range(8):
        _c = (_c >> 1) ^ (0xEDB88320 if _c & 1 else 0)
    _TABLE.append(_c)
_REVERSE = {entry >> 24: index for index, entry in enumerate(_TABLE)}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def crc_compensation(data, offset, target):
    """Four bytes for data[offset:offset+4] that make zlib.crc32(data) == target."""
    before = zlib.crc32(data[:offset]) ^ 0xFFFFFFFF
    need = target ^ 0xFFFFFFFF
    # Run the register backwards through the bytes after the gap, then through
    # four zero bytes; the difference from the register before the gap is the
    # value the gap must hold.
    for byte in list(reversed(data[offset + 4:])) + [None] * 4:
        index = _REVERSE[need >> 24]
        need = ((need ^ _TABLE[index]) << 8) & 0xFFFFFFFF
        need |= index ^ (byte or 0)
    return struct.pack('<I', need ^ before)


def branch_targets(image, base):
    """Targets of everything that decodes as a direct Thumb branch, at every
    even offset. Data that happens to look like a branch is included, which
    only makes the unreachability check below stricter."""
    def signed(value, bits):
        return value - (1 << bits) if value >> (bits - 1) else value

    for offset in range(0, len(image) - 1, 2):
        address = base + offset
        first = struct.unpack_from('<H', image, offset)[0]
        if first & 0xF000 == 0xD000 and (first >> 8) & 15 < 14:        # B<cond>.N
            yield address, address + 4 + 2 * signed(first & 0xFF, 8)
        elif first & 0xF800 == 0xE000:                                  # B.N
            yield address, address + 4 + 2 * signed(first & 0x7FF, 11)
        elif first & 0xF500 == 0xB100:                                  # CBZ / CBNZ
            yield address, address + 4 + 2 * (((first >> 9) & 1) << 5 | (first >> 3) & 31)
        elif first & 0xF800 == 0xF000 and offset + 4 <= len(image):
            second = struct.unpack_from('<H', image, offset + 2)[0]
            sign, j1, j2 = (first >> 10) & 1, (second >> 13) & 1, (second >> 11) & 1
            if first & 0xFF80 == 0xF000 and second & 0xF001 == 0xC001:   # LE (back) / WLS (forward)
                distance = (second >> 1 & 0x3FF) << 2 | (second >> 11 & 1) << 1
                yield address, address + 4 + (-distance if first & 15 == 15 else distance)
            elif second & 0xD000 == 0x8000 and (first >> 6) & 15 < 14:   # B<cond>.W
                value = sign << 20 | j2 << 19 | j1 << 18 | (first & 0x3F) << 12 | (second & 0x7FF) << 1
                yield address, address + 4 + signed(value, 21)
            elif second & 0xD000 in (0x9000, 0xD000):                    # B.W / BL
                i1, i2 = 1 ^ j1 ^ sign, 1 ^ j2 ^ sign
                value = sign << 24 | i1 << 23 | i2 << 22 | (first & 0x3FF) << 12 | (second & 0x7FF) << 1
                yield address, address + 4 + signed(value, 25)


def open_gate(sector, manifest):
    """Return (patched sector 0, record). `manifest` is the capture build's."""
    late = manifest['late_load']
    stage2 = int(manifest['stage2_flash_offset'], 16)
    load = int(manifest['stage2_load_address'], 16)
    total = manifest['stage2_full_bytes']
    late_offset, late_bytes, late_crc = late['late_flash_offset'], late['late_bytes'], late['late_crc32']
    require(late_offset + late_bytes == stage2 + total <= len(sector), 'Late range is not the end of the receiver')
    image = sector[stage2:stage2 + total]
    region = sector[late_offset:late_offset + late_bytes]
    require(zlib.crc32(region) == late_crc, 'Late receiver code differs from its recorded CRC')

    require(image.count(ASSERTION) == 1, 'Fixed-exposure assertion not found exactly once')
    site = image.index(ASSERTION)
    flash = stage2 + site
    require(not site & 1 and late_offset <= flash and flash + len(ASSERTION) <= late_offset + late_bytes,
            'Fixed-exposure assertion is outside the late-loaded range')
    address = load + site
    # The conditional branch must really skip the failure path it guards.
    targets = dict(branch_targets(image[site + BRANCH:site + BRANCH + 2], address + BRANCH))
    resume = targets.get(address + BRANCH)
    require(resume is not None and resume >= address + len(ASSERTION), 'Unexpected assertion branch')

    spare = range(address + SPARE, address + SPARE + 4)
    for source, target in branch_targets(image, load):
        require(target not in spare, f'{source:#x} branches into the bytes that would become unreachable')
    for offset in range(0, len(image) - 3, 2):
        word = struct.unpack_from('<I', image, offset)[0]
        require(word & ~1 not in spare, f'{load + offset:#x} holds the address of the bytes that would become unreachable')

    patched = bytearray(region)
    start = flash - late_offset
    require(patched[start + BRANCH + 1] == BEQ_N, 'Assertion branch encoding changed')
    patched[start + BRANCH + 1] = B_N
    patched[start + SPARE:start + SPARE + 4] = crc_compensation(bytes(patched), start + SPARE, late_crc)
    require(zlib.crc32(bytes(patched)) == late_crc, 'CRC compensation failed')
    # Same destination, now taken always.
    after = dict(branch_targets(bytes(patched[start + BRANCH:start + BRANCH + 2]), address + BRANCH))
    require(after == {address + BRANCH: resume}, 'Patched branch does not reach the original continuation')

    result = bytearray(sector)
    result[late_offset:late_offset + late_bytes] = patched
    changed = [i for i in range(len(sector)) if result[i] != sector[i]]
    require(changed and set(changed) <= set(range(flash + BRANCH + 1, flash + SPARE + 4)),
            'Change is not confined to the assertion')
    record = dict(schema=1, address=hex(address), flash_offset=flash, resumes_at=hex(resume),
                  original=bytes(sector[flash:flash + len(ASSERTION)]).hex(),
                  patched=bytes(result[flash:flash + len(ASSERTION)]).hex(),
                  changed_flash_offsets=changed, late_crc32=late_crc,
                  meaning='beq.n to b.n: the receiver no longer requires 1428 exposure lines; '
                          'the four unreachable bytes after it keep the late-range CRC-32 unchanged')
    return bytes(result), record


def close_gate(sector, record):
    """Undo open_gate using its record; used to prove nothing else changed."""
    flash = record['flash_offset']
    original = bytes.fromhex(record['original'])
    require(bytes(sector[flash:flash + len(original)]) == bytes.fromhex(record['patched']), 'Sector does not hold the recorded patch')
    result = bytearray(sector)
    result[flash:flash + len(original)] = original
    return bytes(result)
