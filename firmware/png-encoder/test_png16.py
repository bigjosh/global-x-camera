"""Offline C encoder tests, independently decoded by zlib and Pillow.

No hardware or filesystem image is touched. Test outputs stay in host memory.
The native DLL is compiled in a temporary directory and removed afterward.
"""
import ctypes as C
import hashlib
import io
import json
from pathlib import Path
import random
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

from PIL import Image

HERE = Path(__file__).resolve().parent
WRITE = C.CFUNCTYPE(C.c_int, C.c_void_p, C.POINTER(C.c_uint8), C.c_size_t)


class Stats(C.Structure):
    _fields_ = [("output_bytes", C.c_uint64), ("rows_encoded", C.c_uint32),
                ("idat_chunks", C.c_uint32), ("callback_calls", C.c_uint32)]


def compile_library(folder):
    compiler = shutil.which("clang") or shutil.which("gcc")
    if not compiler:
        raise RuntimeError("A native C compiler is required")
    library = Path(folder) / ("png16.dll" if hasattr(C, "windll") else "png16.so")
    subprocess.run([
        compiler, "-shared", "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-ffunction-sections", "-fdata-sections", str(HERE / "png16.c"),
        str(HERE / "png16_miniz.c"), "-Wl,--gc-sections", "-o", str(library),
    ], check=True, capture_output=True)
    lib = C.CDLL(str(library))
    lib.png16_workspace_size.restype = C.c_size_t
    lib.png16_workspace_alignment.restype = C.c_size_t
    lib.png16_encode.argtypes = [
        C.c_void_p, C.c_size_t, C.c_uint32, C.c_uint32, C.c_size_t,
        C.c_int, C.c_void_p, C.c_size_t, WRITE, C.c_void_p, C.POINTER(Stats)]
    lib.png16_encode.restype = C.c_int
    return lib


def close_library(lib):
    if hasattr(C, "windll"):
        C.windll.kernel32.FreeLibrary(C.c_void_p(lib._handle))


def parse_png(raw):
    """Parse chunks/check CRCs, inflate/unfilter independently of the encoder."""
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError("Bad signature")
    pos, chunks = 8, []
    while pos < len(raw):
        length, name = struct.unpack_from(">I4s", raw, pos)
        data = raw[pos+8:pos+8+length]
        crc = struct.unpack_from(">I", raw, pos+8+length)[0]
        if crc != zlib.crc32(name+data):
            raise AssertionError("Bad chunk CRC")
        chunks.append((name, data))
        pos += length+12
    if pos != len(raw) or chunks[-1] != (b"IEND", b""):
        raise AssertionError("No exact IEND")
    width, height, depth, color, comp, filt, interlace = struct.unpack(
        ">IIBBBBB", chunks[0][1])
    if (depth, color, comp, filt, interlace) != (16, 0, 0, 0, 0):
        raise AssertionError("Unexpected format")
    if chunks[1] != (b"sBIT", b"\x0a"):
        raise AssertionError("Missing ordered sBIT10")
    if any(name not in (b"IHDR", b"sBIT", b"IDAT", b"IEND") for name, _ in chunks):
        raise AssertionError("Unexpected chunk")
    stream = b"".join(data for name, data in chunks if name == b"IDAT")
    inflater = zlib.decompressobj()
    scanlines = inflater.decompress(stream)+inflater.flush()
    if not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
        raise AssertionError("Incomplete/extra zlib stream")
    if len(scanlines) != height*(1+2*width):
        raise AssertionError("Wrong decompressed length")
    pixels, filters = [], []
    for y in range(height):
        row = bytearray(scanlines[y*(1+2*width):(y+1)*(1+2*width)])
        filters.append(row[0])
        if row[0] == 1:
            for x in range(3, len(row)):
                row[x] = (row[x]+row[x-2]) & 255
        elif row[0] != 0:
            raise AssertionError("Unexpected filter")
        pixels.extend(struct.unpack(">"+"H"*width, row[1:]))
    return width, height, pixels, filters, chunks, stream


class EncoderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="png16-tests-")
        cls.lib = compile_library(cls.temp.name)

    @classmethod
    def tearDownClass(cls):
        close_library(cls.lib)
        del cls.lib
        cls.temp.cleanup()

    def encode(self, samples, width, height, mode, stride=None, fail_after=None,
               fill=0xA5, unaligned=False):
        stride = stride or width*2
        raw = bytearray([0xD3])*(stride*height)
        for y in range(height):
            struct.pack_into("<"+"H"*width, raw, y*stride,
                             *samples[y*width:(y+1)*width])
        input_owner = C.create_string_buffer(bytes([0xCD])+raw)
        input_address = C.addressof(input_owner)+int(unaligned)
        if not unaligned:
            C.memmove(input_address, bytes(raw), len(raw))
        original = C.string_at(input_address, len(raw))
        needed = self.lib.png16_workspace_size()
        owner = (C.c_uint64*((needed+64+7)//8))()
        C.memset(owner, fill, C.sizeof(owner))
        workspace = C.addressof(owner)+16
        pieces, calls = [], []

        @WRITE
        def sink(user, data, count):
            calls.append(count)
            if fail_after is not None and len(calls) > fail_after:
                return 0
            pieces.append(C.string_at(data, count))
            return 1

        stats = Stats()
        result = self.lib.png16_encode(
            input_address, len(raw), width, height, stride, mode, workspace,
            needed, sink, None, C.byref(stats))
        self.assertEqual(C.string_at(input_address, len(raw)), original)
        self.assertEqual(C.string_at(C.addressof(owner), 16), bytes([fill])*16)
        tail = C.sizeof(owner)-16-needed
        self.assertEqual(C.string_at(workspace+needed, tail), bytes([fill])*tail)
        self.assertTrue(all(0 < n <= 16384 for n in calls))
        self.assertEqual(stats.callback_calls, len(calls))
        self.assertEqual(stats.output_bytes, sum(map(len, pieces)))
        return result, b"".join(pieces), stats

    def check_roundtrip(self, samples, width, height, mode, **kwargs):
        result, encoded, stats = self.encode(samples, width, height, mode, **kwargs)
        self.assertEqual(result, 0)
        w, h, pixels, filters, chunks, stream = parse_png(encoded)
        self.assertEqual((w, h), (width, height))
        self.assertEqual(pixels, [v << 6 for v in samples])
        self.assertEqual([v >> 6 for v in pixels], samples)
        self.assertEqual(filters, [1 if mode == 2 else 0]*height)
        with Image.open(io.BytesIO(encoded)) as image:
            image.load()
            self.assertEqual(image.size, (width, height))
            values = getattr(image, "get_flattened_data", image.getdata)()
            self.assertEqual(list(values), pixels)
        self.assertEqual(stats.rows_encoded, height)
        self.assertEqual(stats.idat_chunks, sum(name == b"IDAT" for name, _ in chunks))
        if mode == 0:
            self.assertEqual((stream[2] >> 1) & 3, 0)  # first DEFLATE block stored
        return encoded

    def test_all_1024_sensor_values_and_extrema(self):
        samples = list(range(1024))+list(reversed(range(1024)))
        for mode in range(3):
            with self.subTest(mode=mode):
                self.check_roundtrip(samples, 1024, 2, mode)

    def test_odd_dimensions_padding_and_unaligned_input(self):
        samples = [0, 1, 1023, 256, 4, 511, 3, 7, 17, 99, 100, 101, 9, 8, 7]
        for mode in range(3):
            self.check_roundtrip(samples, 3, 5, mode, stride=11, unaligned=True)

    def test_single_pixel_and_constant_rows(self):
        for value in (0, 1, 511, 1023):
            for mode in range(3):
                self.check_roundtrip([value], 1, 1, mode)
                self.check_roundtrip([value]*67*4, 67, 4, mode)

    def test_full_frame_noise_and_multiple_idat_chunks(self):
        rng = random.Random(0x5943)
        samples = [rng.randrange(1024) for _ in range(1120*1364)]
        for mode in range(3):
            encoded = self.check_roundtrip(samples, 1120, 1364, mode)
            chunks = parse_png(encoded)[4]
            self.assertGreater(sum(n == b"IDAT" for n, _ in chunks), 10)
            self.assertTrue(all(len(d) <= 16384 for n, d in chunks if n == b"IDAT"))

    def test_fast_modes_compress_repetitive_image(self):
        samples = [x % 1024 for _ in range(128) for x in range(1120)]
        plain = self.check_roundtrip(samples, 1120, 128, 0)
        for mode in (1, 2):
            compressed = self.check_roundtrip(samples, 1120, 128, mode)
            self.assertLess(len(compressed), len(plain)//4)

    def test_reused_dirty_workspace_does_not_change_output(self):
        samples = [(i*127) % 1024 for i in range(181*61)]
        for mode in range(3):
            a = self.check_roundtrip(samples, 181, 61, mode, fill=0x00)
            b = self.check_roundtrip(samples, 181, 61, mode, fill=0xFF)
            self.assertEqual(a, b)

    def test_callback_failure_stops_without_iend(self):
        samples = [i % 1024 for i in range(1120*64)]
        for mode in range(3):
            for accepted in (0, 1, 4, 7, 10):
                with self.subTest(mode=mode, accepted=accepted):
                    result, partial, stats = self.encode(
                        samples, 1120, 64, mode, fail_after=accepted)
                    self.assertEqual(result, -4)
                    self.assertEqual(stats.callback_calls, accepted+1)
                    self.assertFalse(partial.endswith(b"\x00\x00\x00\x00IEND\xaeB`\x82"))

    def test_nonraw10_sample_is_rejected_without_modifying_source(self):
        for mode in range(3):
            result, partial, stats = self.encode([1, 2, 3, 0xFC00], 2, 2, mode)
            self.assertEqual(result, -3)
            self.assertEqual(stats.rows_encoded, 1)
            self.assertNotIn(b"IEND", partial)

    def test_invalid_extent_workspace_alias_and_options_never_call_sink(self):
        inp = C.create_string_buffer(b"\x00"*128)
        needed = self.lib.png16_workspace_size()
        workspace = (C.c_uint64*((needed+7)//8))()
        called = []

        @WRITE
        def sink(user, data, count):
            called.append(count)
            return 1

        defaults = [C.addressof(inp), 128, 4, 4, 8, 0,
                    C.addressof(workspace), needed, sink, None, None]
        changes = [
            (0, None, -1), (1, 31, -1), (2, 0, -1), (2, 1121, -1),
            (3, 0, -1), (3, 1365, -1), (4, 7, -1),
            (4, C.c_size_t(-1).value, -1), (5, -1, -1), (5, 3, -1),
            (6, None, -1), (6, C.addressof(inp), -2),
            (6, C.addressof(workspace)+1, -2), (7, needed-1, -2),
            (10, C.cast(workspace, C.POINTER(Stats)), -1),
        ]
        for index, value, expected in changes:
            with self.subTest(index=index, value=value):
                args = defaults.copy()
                args[index] = value
                self.assertEqual(self.lib.png16_encode(*args), expected)
                self.assertFalse(called)

    def test_workspace_budget(self):
        self.assertLessEqual(self.lib.png16_workspace_size(), 192*1024)
        self.assertLessEqual(self.lib.png16_workspace_alignment(), 8)

    def test_pinned_upstream_files_match_recorded_downloads(self):
        root = HERE / "vendor/miniz"
        info = json.loads((root / "UPSTREAM.json").read_text())
        self.assertEqual(info["commit"], "174573d60290f447c13a2b1b3405de2b96e27d6c")
        for record in info["files"]:
            data = (root / record["file"]).read_bytes()
            self.assertEqual(len(data), record["bytes"])
            self.assertEqual(hashlib.sha256(data).hexdigest(), record["sha256"])


if __name__ == "__main__":
    unittest.main()
