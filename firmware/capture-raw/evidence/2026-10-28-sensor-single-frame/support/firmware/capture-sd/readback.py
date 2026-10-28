"""Read a complete PNG through the guarded RAM helper and verify every pixel.

No reset, power control, formatting, deletion, or retry is performed. An error
stops the download and leaves the target's diagnostic state available.
"""
import argparse
import array
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

import bench


def verify(png_path, frame_path):
    """Independent PNG decoding plus chunk CRC and exact RAW10 comparison."""
    from PIL import Image

    png = png_path.read_bytes()
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Invalid PNG signature")
    offset, chunks, significant_bits = 8, [], None
    while offset < len(png):
        if offset + 12 > len(png):
            raise ValueError("Truncated PNG chunk")
        count, = struct.unpack_from(">I", png, offset)
        end = offset + 12 + count
        if end > len(png):
            raise ValueError("PNG chunk exceeds file")
        kind = png[offset + 4:offset + 8]
        data = png[offset + 8:end - 4]
        crc, = struct.unpack_from(">I", png, end - 4)
        if zlib.crc32(kind + data) & 0xFFFFFFFF != crc:
            raise ValueError("PNG chunk CRC mismatch")
        chunks.append(kind.decode("ascii"))
        if kind == b"IHDR":
            if struct.unpack(">IIBBBBB", data) != (1120, 1364, 16, 0, 0, 0, 0):
                raise ValueError("Unexpected PNG format")
        if kind == b"sBIT":
            significant_bits = data
        offset = end
    if (not chunks or chunks[0] != "IHDR" or chunks[-1] != "IEND"
            or significant_bits != b"\x0a"):
        raise ValueError("Required PNG structure/sBIT is missing")
    raw = frame_path.read_bytes()
    if len(raw) != bench.FRAME_BYTES:
        raise ValueError("Unexpected RAW10 frame length")
    frame = array.array("H", raw)
    if sys.byteorder != "little":
        frame.byteswap()
    with Image.open(png_path) as image:
        image.load()
        if image.size != (1120, 1364):
            raise ValueError("Decoded image dimensions differ")
        pixels = (image.get_flattened_data() if hasattr(image, "get_flattened_data")
                  else image.getdata())
        if len(pixels) != len(frame):
            raise ValueError("Decoded pixel count differs")
        for index, (saved, sample) in enumerate(zip(pixels, frame)):
            if sample > 1023 or saved != sample << 6:
                raise ValueError(f"Pixel {index} differs: PNG={saved}, RAW10={sample}")
    return dict(bytes=len(png), sha256=hashlib.sha256(png).hexdigest(),
                frame_sha256=hashlib.sha256(raw).hexdigest(),
                all_png_chunk_crcs_valid=True, exact_pixels_sample_shift_left_6=True,
                pixels=len(frame), format="PNG grayscale16", sBIT=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame", type=Path, required=True)
    parser.add_argument("--file", type=Path, help="Verify an existing PNG offline")
    parser.add_argument("--build", type=Path)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--name")
    parser.add_argument("--bytes", type=int)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.file:
        if args.execute:
            parser.error("--file verification does not use --execute")
        print(json.dumps(verify(args.file, args.frame), indent=2))
        return
    if not (args.execute and args.build and args.expected_sha256 and args.out
            and args.name and args.bytes and 0 < args.bytes <= 3100000):
        parser.error("Downloading requires --execute, build/hash/out/name/bytes and frame")
    manifest, _ = bench.checked_build(args.build.resolve(), args.expected_sha256)
    chunk_size = bench.module_buffer(manifest, bench.OPERATIONS["read"])[1]
    args.out.mkdir(parents=True, exist_ok=False)
    png, reads = bytearray(), 0
    for offset in range(0, args.bytes, chunk_size):
        count = min(chunk_size, args.bytes - offset)
        folder = args.out / f"chunk-{offset:08x}"
        bench.run_request(args.build, folder, args.expected_sha256,
                          bench.OPERATIONS["read"], bench.MODES["fast-none"],
                          offset=offset, length=count, name=args.name)
        data = (folder / "data.bin").read_bytes()
        if len(data) != count:
            raise ValueError("Short SD readback")
        png.extend(data)
        reads += 1
        print(json.dumps(dict(downloaded=len(png), total=args.bytes)), flush=True)
    path = args.out / args.name
    path.write_bytes(png)
    result = dict(verify(path, args.frame), hardware_reads=reads, file=str(path))
    (args.out / "verified.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
