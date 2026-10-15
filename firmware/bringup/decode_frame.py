"""Decode the bring-up's exact 640x480 Y8 frame without image enhancement."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("png", type=Path)
    args = parser.parse_args()
    pixels = args.raw.read_bytes()
    if len(pixels) != 640 * 480:
        parser.error(f"expected 307200 bytes, received {len(pixels)}")
    fnv = 2166136261
    for pixel in pixels:
        fnv = ((fnv ^ pixel) * 16777619) & 0xFFFFFFFF
    Image.frombytes("L", (640, 480), pixels).save(args.png, format="PNG")
    print(json.dumps({
        "width": 640, "height": 480, "format": "Y8",
        "bytes": len(pixels), "minimum": min(pixels), "maximum": max(pixels),
        "sum": sum(pixels), "mean": sum(pixels) / len(pixels),
        "fnv1a": f"0x{fnv:08x}", "sha256": hashlib.sha256(pixels).hexdigest(),
    }, indent=2))


if __name__ == "__main__":
    main()
