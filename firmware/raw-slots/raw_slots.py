#!/usr/bin/env python3
"""Inspect/extract Global-X RAW slots from an image or read-only SD device.

No command writes to the source. On Windows a physical device may require an
elevated terminal and must be positively identified by the operator first.
This utility neither discovers disks automatically nor formats them.
"""
from __future__ import annotations

import argparse
import array
import json
from pathlib import Path
import struct
import sys
import zlib

SECTOR = 512
FIRST_LBA = 8
STRIDE = 3731
WIDTH, HEIGHT = 1120, 1364
ROW_BYTES = 1400
PAYLOAD_BYTES = 1909600
PAYLOAD_SECTORS = 3730
FREE, PARTIAL, FULL = 0x45455246, 0x54524150, 0x4C4C5546
STATES = {FREE: "FREE", PARTIAL: "PARTIAL", FULL: "FULL"}


class FormatError(ValueError):
    pass


def u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def u64(data, offset):
    return struct.unpack_from("<Q", data, offset)[0]


def check_crc(data):
    if len(data) != SECTOR or zlib.crc32(data[:508]) != u32(data, 508):
        raise FormatError("missing/torn header or CRC mismatch")


def read_sectors(source, lba, count=1):
    source.seek(lba * SECTOR)
    data = source.read(count * SECTOR)
    if len(data) != count * SECTOR:
        raise FormatError(f"short read at LBA {lba}: {len(data)} / {count * SECTOR} bytes")
    return data


def parse_volume(data, *, allow_formatting=False):
    check_crc(data)
    if data[:8] != b"GXRWVOL1" or u32(data, 8) != 1:
        raise FormatError("not a supported Global-X RAW volume")
    if u32(data, 12) not in (1, 2):
        raise FormatError("unknown format state")
    if u32(data, 12) == 1 and not allow_formatting:
        raise FormatError("format was not completed; volume is not allocatable")
    geometry = (FIRST_LBA, STRIDE, PAYLOAD_BYTES, WIDTH, HEIGHT, ROW_BYTES, 1, SECTOR)
    actual = tuple(u32(data, offset) for offset in (32, 36, 44, 48, 52, 56, 60, 64))
    if actual != geometry or any(data[68:508]):
        raise FormatError("unsupported volume geometry or reserved fields")
    generation, capacity, slots = u64(data, 16), u64(data, 24), u32(data, 40)
    if not generation or not slots or capacity > (1 << 32) or FIRST_LBA + slots * STRIDE > capacity:
        raise FormatError("invalid generation/capacity/slot count")
    return {"version": 1, "state": "READY" if u32(data, 12) == 2 else "FORMATTING",
            "generation": generation, "sector_count": capacity, "slot_count": slots,
            "first_lba": FIRST_LBA, "slot_sectors": STRIDE, "width": WIDTH,
            "height": HEIGHT, "payload_bytes": PAYLOAD_BYTES, "packing": "MIPI_RAW10"}


def parse_slot(data, volume, index):
    check_crc(data)
    lba = FIRST_LBA + index * STRIDE
    if not 0 <= index < volume["slot_count"]:
        raise FormatError("slot index outside volume")
    if data[:8] != b"GXRAWSL1" or u32(data, 8) != 1:
        raise FormatError("unknown slot header")
    if u64(data, 16) != volume["generation"] or u32(data, 24) != index:
        raise FormatError("foreign generation or wrong slot index")
    actual = tuple(u32(data, off) for off in (28, 32, 36, 40, 44, 48))
    if actual != (PAYLOAD_BYTES, lba + 1, WIDTH, HEIGHT, ROW_BYTES, 1) or any(data[92:508]):
        raise FormatError("unsupported slot geometry or reserved fields")
    state = u32(data, 12)
    if state not in STATES or u32(data, 88) != (PAYLOAD_BYTES if state == FULL else 0):
        raise FormatError("invalid slot state or completion length")
    if state == FREE and any(data[52:88]):
        raise FormatError("FREE header contains object metadata")
    return {"index": index, "state": STATES[state], "header_lba": lba,
            "payload_lba": lba + 1, "payload_bytes": PAYLOAD_BYTES,
            "metadata_flags": u32(data, 52), "capture_id": u64(data, 56),
            "timestamp_us": u64(data, 64), "exposure_us": u32(data, 72),
            "analog_gain_milli": u32(data, 76), "digital_gain_milli": u32(data, 80),
            "orientation": u32(data, 84), "generation": volume["generation"]}


def read_slot(source, volume, index):
    if not 0 <= index < volume["slot_count"]:
        raise FormatError("slot index outside volume")
    return parse_slot(read_sectors(source, FIRST_LBA + index * STRIDE), volume, index)


def unpack_raw10(data, *, shift=6):
    """Return native-endian uint16 samples; four MSBs then packed low pairs."""
    if len(data) % 5 or shift not in (0, 6):
        raise FormatError("RAW10 length must be a multiple of five; shift must be 0 or 6")
    pixels = array.array("H")
    for i in range(0, len(data), 5):
        a, b, c, d, low = data[i:i + 5]
        pixels.extend((((a << 2) | (low & 3)) << shift,
                       ((b << 2) | ((low >> 2) & 3)) << shift,
                       ((c << 2) | ((low >> 4) & 3)) << shift,
                       ((d << 2) | ((low >> 6) & 3)) << shift))
    return pixels


def png16(data, metadata):
    if len(data) != PAYLOAD_BYTES:
        raise FormatError("wrong frame payload length")
    pixels = unpack_raw10(data)
    if sys.byteorder == "little":
        pixels.byteswap()
    packed = pixels.tobytes()
    scanlines = b"".join(b"\0" + packed[y * WIDTH * 2:(y + 1) * WIDTH * 2] for y in range(HEIGHT))

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 16, 0, 0, 0, 0))
            + chunk(b"sBIT", b"\x0a")
            + chunk(b"tEXt", b"Global-X RAW slot\0" + json.dumps(metadata, sort_keys=True).encode("ascii"))
            + chunk(b"IDAT", zlib.compress(scanlines, 6)) + chunk(b"IEND", b""))


def extract(source, volume, index, output, *, kind="png", allow_partial=False):
    slot = read_slot(source, volume, index)
    if slot["state"] != "FULL" and not (allow_partial and slot["state"] == "PARTIAL"):
        raise FormatError(f"slot {index} is {slot['state']}; not extracting")
    data = read_sectors(source, slot["payload_lba"], PAYLOAD_SECTORS)
    slot["tail_padding_zero"] = not any(data[PAYLOAD_BYTES:])
    if slot["state"] == "PARTIAL":
        slot["warning"] = "Interrupted capture: payload can contain stale sectors from older data."
    payload = data[:PAYLOAD_BYTES]
    result = payload if kind == "raw" else png16(payload, slot)
    with open(output, "xb") as destination:
        destination.write(result)
    return slot


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="raw image file or explicitly identified read-only physical device")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="show volume and occupied/error slots (source read-only)")
    listing.add_argument("--all", action="store_true", help="include FREE slots")
    listing.add_argument("--limit", type=int, help="inspect at most this many slots")
    extraction = commands.add_parser("extract", help="extract one slot; refuse existing destination")
    extraction.add_argument("slot", type=int)
    extraction.add_argument("output", type=Path)
    extraction.add_argument("--kind", choices=("png", "raw"), default="png")
    extraction.add_argument("--allow-partial", action="store_true", help="salvage with explicit stale-data warning")
    args = parser.parse_args(argv)
    try:
        with open(args.source, "rb") as source:
            volume = parse_volume(read_sectors(source, 0))
            if args.command == "list":
                print(json.dumps({"volume": volume}, sort_keys=True))
                count = volume["slot_count"] if args.limit is None else min(volume["slot_count"], max(0, args.limit))
                for i in range(count):
                    try:
                        record = read_slot(source, volume, i)
                    except FormatError as exc:
                        record = {"index": i, "state": "INVALID", "error": str(exc)}
                    if args.all or record["state"] != "FREE":
                        print(json.dumps(record, sort_keys=True))
            else:
                result = extract(source, volume, args.slot, args.output, kind=args.kind,
                                 allow_partial=args.allow_partial)
                print(json.dumps(result, sort_keys=True))
    except (OSError, FormatError) as exc:
        parser.exit(1, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
