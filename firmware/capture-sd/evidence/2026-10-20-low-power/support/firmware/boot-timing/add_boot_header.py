#!/usr/bin/env python3
"""Wrap a RAM-linked STM32N6 FSBL in an unsigned STM32 v2.3 boot image.

This tool only reads/writes local files. It neither connects to a board nor
programs flash, OTP, keys, or security settings. Use only on an unlocked device.
See header-evidence.md for the ST specification and independent binary check.
The executable vector table must be linked at 0x34180400.
"""

import argparse
import hashlib
import json
import struct
from pathlib import Path

HEADER_SIZE = 0x240
VECTOR_OFFSET = 0x400
VECTOR_ADDRESS = 0x34180400
MAX_IMAGE_SIZE = 0x80000


def u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def validate_payload(payload):
    if len(payload) < 8:
        raise ValueError("Payload must begin with stack and reset vectors")
    stack, reset = struct.unpack_from("<II", payload)
    if stack & 7 or not 0x30000000 < stack <= 0x34200000:
        raise ValueError(f"Invalid secure internal-RAM stack pointer: {stack:#010x}")
    if not reset & 1:
        raise ValueError("Reset vector must select Thumb state (bit 0 set)")
    if not VECTOR_ADDRESS <= (reset & ~1) < VECTOR_ADDRESS + len(payload):
        raise ValueError(f"Reset vector {reset:#010x} lies outside the linked payload")
    if VECTOR_OFFSET + ((len(payload) + 31) & ~31) > MAX_IMAGE_SIZE:
        raise ValueError("Header plus aligned payload exceeds ROM's 512 KiB limit")
    return stack, reset


def make_image(payload):
    _, reset = validate_payload(payload)
    # UM2543 --align equivalent: these 448 leading zero bytes are part of the
    # payload length/checksum, not part of the 576-byte header.
    aligned = bytes(VECTOR_OFFSET - HEADER_SIZE) + payload
    aligned += bytes((-len(aligned)) % 32)
    header = bytearray(HEADER_SIZE)
    header[:4] = b"STM2"
    for offset, value in (
        (0x64, sum(aligned) & 0xFFFFFFFF),
        (0x68, 0x00020300),
        (0x6C, len(aligned)),
        (0x70, reset),
        (0x78, 0xFFFFFFFF),  # ROM's default internal-RAM loading address.
        (0x80, 0),           # Version zero; no antirollback increment requested.
        (0x84, 0x80000000),  # Padding extension only; no authentication/encryption.
        (0x88, HEADER_SIZE - 0xA0),
        (0x8C, 0x10),        # FSBL.
        (0xA4, HEADER_SIZE - 0xA0),
    ):
        struct.pack_into("<I", header, offset, value)
    header[0xA0:0xA4] = b"ST\xff\xff"
    image = bytes(header) + aligned
    inspect_image(image)
    return image


def inspect_image(image):
    """Validate this restricted unsigned FSBL format, including an ST reference.

    Extension padding may be zero (ST's Python generator) or arbitrary (ST's
    SigningTool). All reserved base fields must be zero in this restricted mode.
    """
    if not VECTOR_OFFSET + 8 <= len(image) <= MAX_IMAGE_SIZE:
        raise ValueError("Image size is outside supported ROM limits")
    if image[:4] != b"STM2" or u32(image, 0x68) != 0x00020300:
        raise ValueError("Expected STM32 header version 2.3")
    if any(image[4:0x64]):
        raise ValueError("This tool handles unsigned images only")
    for offset, expected in (
        (0x74, 0), (0x78, 0xFFFFFFFF), (0x7C, 0), (0x80, 0),
        (0x84, 0x80000000), (0x88, 0x1A0), (0x8C, 0x10),
        (0x90, 0), (0x94, 0), (0x98, 0), (0x9C, 0), (0xA4, 0x1A0),
    ):
        if u32(image, offset) != expected:
            raise ValueError(f"Unexpected header field at {offset:#x}")
    if image[0xA0:0xA4] != b"ST\xff\xff":
        raise ValueError("Missing padding-extension signature")
    if any(image[HEADER_SIZE:VECTOR_OFFSET]):
        raise ValueError("Alignment padding before vectors must be zero")
    if len(image) % 32:
        raise ValueError("Image must end at a 32-byte boundary")
    if u32(image, 0x6C) != len(image) - HEADER_SIZE:
        raise ValueError("Payload length does not match file length")
    if u32(image, 0x64) != sum(image[HEADER_SIZE:]) & 0xFFFFFFFF:
        raise ValueError("Payload checksum mismatch")
    stack, reset = validate_payload(image[VECTOR_OFFSET:])
    if u32(image, 0x70) != reset:
        raise ValueError("Header entry point differs from payload reset vector")
    return {
        "image_bytes": len(image),
        "payload_bytes_including_alignment": u32(image, 0x6C),
        "vector_address": f"{VECTOR_ADDRESS:#010x}",
        "stack_pointer": f"{stack:#010x}",
        "entry_point": f"{reset:#010x}",
        "checksum": f"{u32(image, 0x64):#010x}",
        "sha256": hashlib.sha256(image).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Raw vector-first binary, or image with --inspect")
    parser.add_argument("output", type=Path, nargs="?", help="New boot-image file")
    parser.add_argument("--inspect", action="store_true", help="Validate an existing unsigned image")
    parser.add_argument("--force", action="store_true", help="Replace an existing output file")
    args = parser.parse_args()
    try:
        if args.inspect:
            if args.output:
                raise ValueError("--inspect does not take an output path")
            print(json.dumps(inspect_image(args.input.read_bytes()), indent=2))
            return
        if not args.output:
            raise ValueError("Output path is required unless --inspect is used")
        if args.input.resolve() == args.output.resolve():
            raise ValueError("Input and output paths must differ")
        image = make_image(args.input.read_bytes())
        with args.output.open("wb" if args.force else "xb") as target:
            target.write(image)
        # Verify bytes actually saved, rather than only the in-memory image.
        saved = args.output.read_bytes()
        if saved != image:
            raise ValueError("Output readback differs from generated image")
        print(json.dumps(inspect_image(saved), indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
