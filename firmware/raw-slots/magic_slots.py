#!/usr/bin/env python3
"""Read/extract fixed GXR2 metadata/RAW10/GXRE slots; never modify the source.

The erased byte must come from the card's SCR, or its recorded commissioning
result. There is no superblock to identify the capacity or format automatically.
The previous GXRS/tail-padding slots can coexist at the same stride. The older
superblock-based version-1 images use the separate raw_slots.py utility.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import struct
import sys
import zlib

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
METADATA_OFFSET, METADATA_BYTES = 4, 152
IMAGE_OFFSET = METADATA_OFFSET + METADATA_BYTES
TRAILER_OFFSET = IMAGE_OFFSET + IMAGE_BYTES
OBJECT_BYTES = TRAILER_OFFSET + 4
PADDED_BYTES = STRIDE * SECTOR
PADDING_BYTES = PADDED_BYTES - OBJECT_BYTES
START_MAGIC, END_MAGIC = b"GXR2", b"GXRE"
LEGACY_START_MAGIC = b"GXRS"
LEGACY_IMAGE_OFFSET = 4
LEGACY_TRAILER_OFFSET = LEGACY_IMAGE_OFFSET + IMAGE_BYTES
LEGACY_OBJECT_BYTES = LEGACY_TRAILER_OFFSET + 4
LEGACY_PADDING_BYTES = PADDED_BYTES - LEGACY_OBJECT_BYTES


def decode_controls_record(metadata):
    """Validate known CKN1/v1 controls; its CRC never covers image pixels.

    State 3 is a pre-stream configuration snapshot, not applied sensor readback.
    The caller leaves unknown schemas opaque and catches invalid known records
    without changing slot occupancy, completion or image-recovery eligibility.
    """
    if len(metadata) != METADATA_BYTES:
        raise FormatError("Controls metadata reservation has the wrong size")
    data = bytes(metadata[:128])
    words = struct.unpack("<32I", data)
    if words[:3] != (0x314E4B43, 1, 128):
        raise FormatError("Controls metadata identity or size differs")
    if zlib.crc32(data[:124]) != words[31]:
        raise FormatError("Controls metadata CRC mismatch; controls are unknown")
    state, error, flags = words[3:6]
    if (state not in (3, 4) or error or flags != (23 if state == 3 else 31)
            or any(words[29:31]) or any(metadata[128:])):
        raise FormatError("Controls metadata state, flags or reserved bytes differ")
    low, exposure_high, asa_high, exposure_raw, asa_raw = words[6:11]
    exposure_q16, asa_q16, requested_us, line, frame = words[11:16]
    if (low > 128 or not low + 3000 <= exposure_high <= 4095
            or not low + 3000 <= asa_high <= 4095
            or exposure_raw > 4095 or asa_raw > 4095):
        raise FormatError("Controls ADC samples or endpoint bounds differ")

    def normalize(raw, high):
        if raw <= low:
            return 0
        if raw >= high:
            return 65535
        return ((raw - low) * 65535 + (high - low) // 2) // (high - low)

    if (exposure_q16 != 65535 - normalize(exposure_raw, exposure_high)
            or asa_q16 != normalize(asa_raw, asa_high)):
        raise FormatError("Controls normalized positions differ from ADC samples")
    manual = data[64:76]
    coarse = int.from_bytes(manual[2:4], "little")
    asa, vt_hz, applied_coarse, applied_gain, applied_digital, margin = words[19:25]
    gain = {100: 0, 200: 16, 400: 24, 800: 28}.get(asa)
    expected_coarse = (requested_us * 160800000 + 1280000000 - 1) // 1280000000
    asa_sector = sum(asa_q16 * 6 >= threshold for threshold in (65535, 196605, 327675))
    if (not 1000 <= requested_us <= 500000 or line != 1280 or vt_hz != 160800000
            or coarse != expected_coarse or coarse < 21
            or frame != max(4336, coarse + 2000) or frame > 65535 or margin > 1993
            or coarse > frame - margin - 7 or manual[0] != 2 or manual[1] != gain
            or asa != 100 << asa_sector or manual[4:] != b"\x00\x01" * 4):
        raise FormatError("Controls exposure, frame or gain bounds differ")
    if state == 4 and (applied_coarse, applied_gain, applied_digital) != (coarse, gain, 256):
        raise FormatError("Controls applied readback differs from configuration")
    result = {
        "schema": "CKN1/v1", "state": state,
        "validation": "applied" if state == 4 else "configured",
        "sensor_readback_verified": state == 4,
        "record_crc32_valid": True, "record_crc32": f"{words[31]:08x}",
        "requested_exposure_us": requested_us,
        "nominal_exposure_us": coarse * line * 1000000 / vt_hz,
        "line_length": line, "coarse_lines": coarse, "frame_length": frame,
        "frame_margin": margin, "vt_hz": vt_hz,
        "analog_gain": 32 // (32 - gain), "analog_code": gain, "digital_gain": 1,
        "asa": asa, "asa_provisional": True,
        "adc": {"low": low, "exposure_high": exposure_high, "asa_high": asa_high,
                "exposure_raw": exposure_raw, "asa_raw": asa_raw},
        "exposure_fraction_q16": exposure_q16, "asa_fraction_q16": asa_q16,
    }
    if state == 4:
        result["applied_registers"] = {"coarse": applied_coarse, "analog": applied_gain,
                                       "digital": applied_digital}
    return result


def _format(first_word):
    if first_word == START_MAGIC:
        return {"format": "GXR2_METADATA_RAW10_GXRE", "format_revision": 2,
                "image_offset": IMAGE_OFFSET, "trailer_offset": TRAILER_OFFSET,
                "metadata_offset": METADATA_OFFSET, "metadata_bytes": METADATA_BYTES,
                "padding_bytes": PADDING_BYTES}
    if first_word == LEGACY_START_MAGIC:
        return {"format": "GXRS_RAW10_GXRE", "format_revision": 1,
                "image_offset": LEGACY_IMAGE_OFFSET, "trailer_offset": LEGACY_TRAILER_OFFSET,
                "metadata_offset": None, "metadata_bytes": 0,
                "padding_bytes": LEGACY_PADDING_BYTES}
    return None


def layout(sector_count, erased_byte):
    if erased_byte not in (0, 255):
        raise FormatError("erased byte must be SCR-reported 0x00 or 0xff")
    if not isinstance(sector_count, int) or not STRIDE <= sector_count <= (1 << 32):
        raise FormatError("capacity must contain a slot and be at most 2^32 sectors")
    return {"format": "GXR2_METADATA_RAW10_GXRE", "sector_count": sector_count,
            "slot_count": sector_count // STRIDE, "erased_byte": erased_byte,
            "first_lba": FIRST_LBA, "slot_sectors": STRIDE, "width": WIDTH,
            "height": HEIGHT, "image_bytes": IMAGE_BYTES, "image_offset": IMAGE_OFFSET,
            "trailer_offset": TRAILER_OFFSET, "padding_bytes": PADDING_BYTES,
            "metadata_offset": METADATA_OFFSET, "metadata_bytes": METADATA_BYTES,
            "supported_slot_formats": ["GXR2_METADATA_RAW10_GXRE", "GXRS_RAW10_GXRE"],
            "packing": "MIPI_RAW10", "checksummed": False}


def parse_header(first_sector, *, index, erased_byte):
    """One-sector directory record: occupancy and metadata, not completion.

    Known controls records are validated; metadata_hex preserves every byte.
    No timestamp schema exists; zero bytes never imply a valid capture date.
    """
    if erased_byte not in (0, 255) or index < 0:
        raise FormatError("invalid erased byte or slot index")
    if len(first_sector) != SECTOR:
        raise FormatError("short first-sector read; occupancy is unknown")
    record = {"index": index, "slot_lba": index * STRIDE, "slot_sectors": STRIDE,
              "image_bytes": IMAGE_BYTES, "start_magic_valid": False,
              "completion_marker_valid": None, "completion_checked": False,
              "checksummed": False}
    if first_sector[:4] == bytes([erased_byte]) * 4:
        record.update(state="FREE", occupied=False)
        return record
    record["occupied"] = True
    detected = _format(first_sector[:4])
    record["state"] = "OCCUPIED"
    if detected:
        record.update(detected)
        record["start_magic_valid"] = True
        if detected["metadata_bytes"]:
            metadata = bytes(first_sector[METADATA_OFFSET:IMAGE_OFFSET])
            record["metadata_hex"] = metadata.hex()
            record["metadata_schema"] = None
            if metadata[:4] == b"CKN1":
                if struct.unpack_from("<I", metadata, 4)[0] != 1:
                    record["metadata_warning"] = "Unsupported controls metadata schema; left opaque."
                else:
                    try:
                        record["controls"] = decode_controls_record(metadata)
                        record["metadata_schema"] = "CKN1/v1"
                    except FormatError as exc:
                        record["metadata_warning"] = str(exc)
    else:
        record.update(format=None, warning="Unknown or damaged leading magic; occupied, not free.")
    return record


def parse_probe(first_sector, last_sector, *, index, erased_byte):
    """Inspect both markers. COMPLETE is not a checksum or an atomicity claim."""
    record = parse_header(first_sector, index=index, erased_byte=erased_byte)
    if not record["occupied"]:
        return record
    if last_sector is None or len(last_sector) != SECTOR:
        record.update(state="PARTIAL" if record["start_magic_valid"] else "OCCUPIED",
                      warning="Missing final sector; this occupied slot is not complete.")
        return record
    if not record["start_magic_valid"]:
        record.update(state="OCCUPIED", warning="Unknown or damaged leading magic; occupied, not free.")
        return record
    tail = record["trailer_offset"] % SECTOR
    record["completion_checked"] = True
    record["completion_marker_valid"] = last_sector[tail:tail + 4] == END_MAGIC
    if record["padding_bytes"]:
        record["tail_padding_zero"] = not any(last_sector[tail + 4:])
    if not record["completion_marker_valid"]:
        record.update(state="PARTIAL", warning="No completion marker; image may be incomplete or damaged.")
    else:
        record["state"] = "COMPLETE"
        if record.get("tail_padding_zero") is False:
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


def read_header(source, volume, index):
    """Directory listing requires exactly one logical-sector read per slot."""
    if not 0 <= index < volume["slot_count"]:
        raise FormatError("slot index outside supplied capacity")
    first = read_sectors(source, index * STRIDE)
    return parse_header(first, index=index, erased_byte=volume["erased_byte"])


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
    if not record["start_magic_valid"]:
        raise FormatError(f"slot {index} has unknown magic; image offset cannot be determined safely")
    if kind not in ("png", "raw"):
        raise FormatError("output kind must be png or raw")
    if record["state"] != "COMPLETE":
        record["warning"] = "Recovered occupied slot: pixels can be missing, erased, or corrupt."
    image = data[record["image_offset"]:record["trailer_offset"]]
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
    listing.add_argument("--check-completion", action="store_true",
                         help="also read occupied slots' last sector; default reads only their first sector")
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
                        reader = read_slot if args.check_completion else read_header
                        record = reader(source, volume, index)
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
