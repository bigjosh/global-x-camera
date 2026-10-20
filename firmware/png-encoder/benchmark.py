"""Host-only size/correctness comparison; no MCU, SD, or instrument access.

Host wall times include Python callbacks and are NOT MCU cycle measurements.
Only a JSON summary is saved; neither source pixels nor PNGs are published.
"""
import argparse
import ctypes as C
import hashlib
import io
import json
from pathlib import Path
import tempfile
import time

import numpy as np
from PIL import Image

from test_png16 import WRITE, Stats, compile_library, close_library, parse_png


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw", type=Path, action="append", default=[])
    p.add_argument("--width", type=int, default=1120)
    p.add_argument("--height", type=int, default=1364)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if not 1 <= a.width <= 1120 or not 1 <= a.height <= 1364:
        p.error("Dimensions exceed the reviewed encoder bounds")
    count = a.width*a.height
    cases = [
        ("black", np.zeros(count, dtype="<u2").tobytes()),
        ("ramp", (np.arange(count, dtype=np.uint32) % 1024).astype("<u2").tobytes()),
        ("noise_seed5943", np.random.default_rng(5943).integers(
            0, 1024, size=count, dtype=np.uint16).astype("<u2").tobytes()),
    ]
    for path in a.raw:
        raw = path.read_bytes()
        if len(raw) != count*2 or np.any(np.frombuffer(raw, dtype="<u2") > 1023):
            p.error(f"Not an exact {a.width}x{a.height} RAW10 LE16 frame: {path}")
        cases.append((str(path), raw))
    results = []
    with tempfile.TemporaryDirectory(prefix="png16-benchmark-") as folder:
        lib = compile_library(folder)
        try:
            needed = lib.png16_workspace_size()
            workspace = (C.c_uint64*((needed+7)//8))()
            for name, raw in cases:
                source = C.create_string_buffer(raw)
                expected = np.frombuffer(raw, dtype="<u2").astype(np.uint32) << 6
                for mode, mode_name in enumerate(("stored_none", "fast_none", "fast_sub")):
                    pieces = []

                    @WRITE
                    def sink(user, data, n):
                        pieces.append(C.string_at(data, n))
                        return 1

                    stats = Stats()
                    start = time.perf_counter()
                    status = lib.png16_encode(
                        source, len(raw), a.width, a.height, a.width*2, mode,
                        workspace, needed, sink, None, C.byref(stats))
                    elapsed = time.perf_counter()-start
                    assert status == 0
                    encoded = b"".join(pieces)
                    w, h, pixels, _, _, _ = parse_png(encoded)
                    assert (w, h) == (a.width, a.height)
                    assert np.array_equal(pixels, expected)
                    with Image.open(io.BytesIO(encoded)) as image:
                        assert np.array_equal(np.asarray(image).ravel(), expected)
                    assert C.string_at(source, len(raw)) == raw
                    results.append(dict(
                        source=name, input_sha256=hashlib.sha256(raw).hexdigest(),
                        mode=mode_name, input_bytes=len(raw), png_bytes=len(encoded),
                        ratio=len(encoded)/len(raw), host_encode_ms=elapsed*1000,
                        png_sha256=hashlib.sha256(encoded).hexdigest(),
                        callback_calls=stats.callback_calls, idat_chunks=stats.idat_chunks,
                        exact_pixel_roundtrip=True))
        finally:
            close_library(lib)
    report = dict(
        hardware_access=False, timing_scope="Host encode wall time including Python sink callbacks; not MCU cycles",
        workspace_bytes=needed, width=a.width, height=a.height,
        result_count=len(results), results=results)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
