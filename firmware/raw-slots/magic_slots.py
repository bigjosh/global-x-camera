#!/usr/bin/env python3
"""Read/extract fixed GXRS + RAW10 + GXRE slots; never modify the source.

The erased byte must come from the card's SCR, or its recorded commissioning
result. There is no superblock to identify the capacity or format automatically.
Legacy version-1 images remain supported by the separate raw_slots.py utility.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys

_spec = importlib.util.spec_from_file_location("_magic_slots_raw_codec", Path(__file__).with_name("raw_slots.py"))
_codec = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_codec)
FormatError = _codec.FormatError
png16 = _codec.png16
unpack_raw10 = _codec.unpack_raw10
read_sectors = _codec.read_sectors

SECTOR = 512
FIRST_LBA = 0
STRIDE = 3730
WIDTH, HEIGHT = 1120, 1364
ROW_BYTES = 1400
IMAGE_BYTES = PAYLOAD_BYTES = 1909600
IMAGE_OFFSET = 4
TRAILER_OFFSET = IMAGE_OFFSET + IMAGE_BYTES
OBJECT_BYTES = TRAILER_OFFSET + 4
PADDED_BYTES = STRIDE * SECTOR
PADDING_BYTES = PADDED_BYTES - OBJECT_BYTES
START_MAGIC, END_MAGIC = b"GXRS", b"GXRE"


def layout(sector_count, erased_byte):
    if erased_byte not in (0, 255):
        raise FormatError("erased byte must be SCR-reported 0x00 or 0xff")
    if not isinstance(sector_count, int) or not STRIDE <= sector_count <= (1 << 32):
        raise FormatError("capacity must contain a slot and be at most 2^32 sectors")
    return {"format": "GXRS_RAW10_GXRE", "sector_count": sector_count,
            "slot_count": sector_count // STRIDE, "erased_byte": erased_byte,
            "first_lba": FIRST_LBA, "slot_sectors": STRIDE, "width": WIDTH,
            "height": HEIGHT, "image_bytes": IMAGE_BYTES, "image_offset": IMAGE_OFFSET,
            "trailer_offset": TRAILER_OFFSET, "padding_bytes": PADDING_BYTES,
            "packing": "MIPI_RAW10", "checksummed": False}


def parse_probe(first_sector, last_sector, *, index, erased_byte):
    """Classify occupancy from first word; the trailing marker describes completion.

    COMPLETE means both markers exist, not that pixel data passed a checksum or
    that an interrupted write was atomic. Any non-erased first word is occupied.
    """
    if erased_byte not in (0, 255) or index < 0:
        raise FormatError("invalid erased byte or slot index")
    if len(first_sector) != SECTOR:
        raise FormatError("short first-sector read; occupancy is unknown")
    record = {"index": index, "slot_lba": index * STRIDE, "slot_sectors": STRIDE,
              "image_offset": IMAGE_OFFSET, "image_bytes": IMAGE_BYTES,
              "start_magic_valid": first_sector[:4] == START_MAGIC,
              "completion_marker_valid": False, "checksummed": False}
    if first_sector[:4] == bytes([erased_byte]) * 4:
        record.update(state="FREE", occupied=False)
        return record
    record["occupied"] = True
    if last_sector is None or len(last_sector) != SECTOR:
        record.update(state="PARTIAL" if record["start_magic_valid"] else "OCCUPIED",
                      warning="Missing final sector; this occupied slot is not complete.")
        return record
    tail = TRAILER_OFFSET % SECTOR
    record["completion_marker_valid"] = last_sector[tail:tail + 4] == END_MAGIC
    record["tail_padding_zero"] = not any(last_sector[tail + 4:])
    if not record["start_magic_valid"]:
        record.update(state="OCCUPIED", warning="Unknown or damaged leading magic; occupied, not free.")
    elif not record["completion_marker_valid"]:
        record.update(state="PARTIAL", warning="No completion marker; image may be incomplete or damaged.")
    else:
        record["state"] = "COMPLETE"
        if not record["tail_padding_zero"]:
            record["warning"] = "Completion markers exist but padding is damaged; no payload checksum is stored."
    return record


def parse_slot(data, *, index=0, erased_byte):
    if len(data) < SECTOR:
        raise FormatError("slot dump lacks its first complete sector")
    last = data[-SECTOR:] if len(data) == PADDED_BYTES else None
    result = parse_probe(data[:SECTOR], last, index=index, erased_byte=erased_byte)
    result["read_bytes"] = len(data)
    if len(data) != PADDED_BYTES:
        result["warning"] = "Slot dump is truncated or has the wrong extent; completion is not established."
    return result


def read_slot(source, volume, index):
    if not 0 <= index < volume["slot_count"]:
        raise FormatError("slot index outside supplied capacity")
    first = read_sectors(source, index * STRIDE)
    if first[:4] == bytes([volume["erased_byte"]]) * 4:
        return parse_probe(first, None, index=index, erased_byte=volume["erased_byte"])
    last = read_sectors(source, (index + 1) * STRIDE - 1)
    return parse_probe(first, last, index=index, erased_byte=volume["erased_byte"])


def extract(source, volume, index, output, *, kind="png", allow_partial=False):
    if not 0 <= index < volume["slot_count"]:
        raise FormatError("slot index outside supplied capacity")
    data = read_sectors(source, index * STRIDE, STRIDE)
    record = parse_slot(data, index=index, erased_byte=volume["erased_byte"])
    if record["state"] == "FREE" or (record["state"] != "COMPLETE" and not allow_partial):
        raise FormatError(f"slot {index} is {record['state']}; not extracting")
    if kind not in ("png", "raw"):
        raise FormatError("output kind must be png or raw")
    if record["state"] != "COMPLETE":
        record["warning"] = "Recovered occupied slot: pixels can be missing, erased, or corrupt."
    image = data[IMAGE_OFFSET:TRAILER_OFFSET]
    encoded = image if kind == "raw" else png16(image, record)
    with open(output, "xb") as target:
        target.write(encoded)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="raw image file or explicitly identified read-only device")
    parser.add_argument("--erased-byte", required=True, type=lambda s: int(s, 0), choices=(0, 255),
                        help="SCR DATA_STAT_AFTER_ERASE converted to byte 0x00 or 0xff")
    parser.add_argument("--sectors", type=int,
                        help="known device capacity; otherwise infer extent from an ordinary image file")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list")
    listing.add_argument("--all", action="store_true")
    listing.add_argument("--limit", type=int)
    extraction = commands.add_parser("extract")
    extraction.add_argument("slot", type=int)
    extraction.add_argument("output", type=Path)
    extraction.add_argument("--kind", choices=("png", "raw"), default="png")
    extraction.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args(argv)
    try:
        sectors = args.sectors
        if sectors is None:
            path = Path(args.source)
            if not path.is_file():
                raise FormatError("supply --sectors for an explicitly identified physical device")
            size = path.stat().st_size
            if size % SECTOR:
                raise FormatError("image file size is not a whole number of logical sectors")
            sectors = size // SECTOR
        volume = layout(sectors, args.erased_byte)
        with open(args.source, "rb") as source:
            if args.command == "list":
                print(json.dumps({"layout": volume}, sort_keys=True))
                count = volume["slot_count"] if args.limit is None else min(volume["slot_count"], max(0, args.limit))
                for index in range(count):
                    try:
                        record = read_slot(source, volume, index)
                    except (OSError, FormatError) as exc:
                        record = {"index": index, "state": "UNKNOWN", "error": str(exc)}
                    if args.all or record["state"] != "FREE":
                        print(json.dumps(record, sort_keys=True))
            else:
                record = extract(source, volume, args.slot, args.output,
                                 kind=args.kind, allow_partial=args.allow_partial)
                print(json.dumps(record, sort_keys=True))
    except (OSError, FormatError) as exc:
        parser.exit(1, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
