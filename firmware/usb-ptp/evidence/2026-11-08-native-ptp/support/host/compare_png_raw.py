"""Independently verify a downloaded PNG16 against a historical RAW10 slot.

Reads only the supplied files. Writes new evidence/preview files; the exported
PNG and historical slot remain untouched. No device or instrument access.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import pathlib
import struct
import zlib

import numpy as np
from PIL import Image


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compare(png_path: pathlib.Path, slot_path: pathlib.Path, output: pathlib.Path) -> dict:
    png = png_path.read_bytes()
    slot = slot_path.read_bytes()
    if len(slot) != 3730 * 512:
        raise ValueError("Historical source is not one complete 3730-sector slot")
    if slot[:4] == b"GXR2":
        raw_offset, end_offset = 156, 1909756
    elif slot[:4] == b"GXRS":
        raw_offset, end_offset = 4, 1909604
    else:
        raise ValueError("Unrecognized slot layout")
    if slot[end_offset:end_offset + 4] != b"GXRE":
        raise ValueError("Historical source slot does not have its completion marker")
    raw = slot[raw_offset:raw_offset + 1909600]
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("PNG signature mismatch")
    offset = 8
    chunks = []
    idat = []
    header = None
    while offset < len(png):
        if offset + 12 > len(png):
            raise ValueError("Truncated PNG chunk")
        size = struct.unpack_from(">I", png, offset)[0]
        kind = png[offset + 4:offset + 8]
        body = png[offset + 8:offset + 8 + size]
        if offset + 12 + size > len(png):
            raise ValueError("Truncated PNG chunk body")
        crc = struct.unpack_from(">I", png, offset + 8 + size)[0]
        if zlib.crc32(kind + body) != crc:
            raise ValueError(f"Bad PNG CRC for {kind!r}")
        chunks.append({"type": kind.decode("ascii"), "bytes": size, "crc_valid": True})
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        if kind == b"IDAT":
            idat.append(body)
        offset += size + 12
        if kind == b"IEND":
            break
    if offset != len(png) or not chunks or chunks[-1]["type"] != "IEND":
        raise ValueError("PNG end boundary mismatch")
    if header != (1120, 1364, 16, 0, 0, 0, 0):
        raise ValueError(f"Unexpected PNG header: {header}")
    decompressor = zlib.decompressobj()
    scanlines = decompressor.decompress(b"".join(idat)) + decompressor.flush()
    if not decompressor.eof or decompressor.unused_data or decompressor.unconsumed_tail:
        raise ValueError("PNG zlib stream boundary mismatch")
    if len(scanlines) != 1364 * (1 + 1120 * 2):
        raise ValueError("PNG decoded byte count mismatch")
    # This firmware currently emits filter zero. Pillow independently decodes
    # the same image; the two routes must agree before comparing to RAW10.
    rows = np.frombuffer(scanlines, dtype=np.uint8).reshape(1364, 2241)
    if np.any(rows[:, 0] != 0):
        raise ValueError("This verifier expects the backend's unfiltered PNG rows")
    direct = np.frombuffer(rows[:, 1:].copy().tobytes(), dtype=">u2").reshape(1364, 1120)
    with Image.open(png_path) as image:
        independent = np.asarray(image)
    if not np.array_equal(direct, independent):
        raise ValueError("Independent PNG decoders disagree")
    groups = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 5).astype(np.uint16)
    expected = np.empty((groups.shape[0], 4), dtype=np.uint16)
    for lane in range(4):
        expected[:, lane] = ((groups[:, lane] * 4) + ((groups[:, 4] >> (lane * 2)) & 3)) * 64
    expected = expected.reshape(1364, 1120)
    mismatch = np.flatnonzero(direct.ravel() != expected.ravel())
    output.mkdir(parents=True, exist_ok=True)
    # A display-only sRGB transfer curve, without contrast stretching. Keep
    # exact PNG16 as the measurement artifact and state the preview transform.
    linear = direct.astype(np.float64) / 65535.0
    srgb = np.where(linear <= 0.0031308, 12.92 * linear, 1.055 * np.power(linear, 1 / 2.4) - 0.055)
    preview = Image.fromarray(np.rint(np.clip(srgb, 0, 1) * 255).astype(np.uint8))
    preview = preview.resize((560, 682), Image.Resampling.LANCZOS)
    preview_path = output / "preview-srgb.png"
    if preview_path.exists():
        raise FileExistsError(preview_path)
    preview.save(preview_path)
    summary = {
        "png": str(png_path.resolve()), "png_bytes": len(png), "png_sha256": sha(png),
        "historical_slot": str(slot_path.resolve()), "slot_sha256": sha(slot),
        "slot_magic": slot[:4].decode("ascii"), "raw_offset": raw_offset,
        "raw_bytes": len(raw), "raw_sha256": sha(raw),
        "width": 1120, "height": 1364, "samples_compared": int(direct.size),
        "all_png_crcs_valid": True, "independent_png_decoders_agree": True,
        "pixel_equality": len(mismatch) == 0, "mismatched_samples": len(mismatch),
        "first_mismatch_flat_index": int(mismatch[0]) if len(mismatch) else None,
        "sample_scaling": "raw10 << 6", "nonzero_low_six_bits": int(np.count_nonzero(direct & 63)),
        "minimum_16bit": int(direct.min()), "maximum_16bit": int(direct.max()),
        "mean_16bit": float(direct.mean()), "png_chunks": chunks,
        "preview": str(preview_path.resolve()), "preview_sha256": sha(preview_path.read_bytes()),
        "preview_transform": "linear 16-bit /65535 -> sRGB transfer -> 8-bit -> Lanczos560x682; no contrast stretch",
        "limit": "Compared against previously verified SD slot readback, not original capture-time camera RAM; no new hardware access.",
    }
    with (output / "comparison.json").open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2)
        stream.write("\n")
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--png", required=True, type=pathlib.Path)
    p.add_argument("--slot", required=True, type=pathlib.Path)
    p.add_argument("--out-dir", required=True, type=pathlib.Path)
    args = p.parse_args()
    result = compare(args.png, args.slot, args.out_dir)
    print(json.dumps({k: result[k] for k in ("pixel_equality", "samples_compared", "mismatched_samples", "png_sha256", "raw_sha256", "minimum_16bit", "maximum_16bit", "preview")}))
    return 0 if result["pixel_equality"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
