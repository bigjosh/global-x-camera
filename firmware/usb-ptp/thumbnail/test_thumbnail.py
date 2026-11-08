"""Offline portable-C thumbnail test, including Windows native decoder."""
import ctypes
import pathlib
import random
import shutil
import struct
import subprocess
import tempfile
import unittest
import json

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SIZE = 54 + 128 * 156 * 3


class ThumbnailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("clang") or shutil.which("gcc")
        if not compiler:
            raise unittest.SkipTest("MinGW C compiler unavailable")
        cls.tmp = tempfile.TemporaryDirectory(prefix="gx-thumb-")
        dll = pathlib.Path(cls.tmp.name) / "thumbnail.dll"
        subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-shared", "-Wl,--export-all-symbols", str(HERE / "thumbnail_bmp.c"),
                        "-o", str(dll)], check=True, capture_output=True)
        cls.lib = ctypes.CDLL(str(dll))
        cls.read = cls.lib.gx_thumbnail_bmp_read
        cls.read.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32,
                            ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
        cls.read.restype = ctypes.c_int
        raw = bytearray(1120 * 1364 * 5 // 4)
        for y in range(1364):
            for g in range(280):
                i = y * 1400 + g * 5
                vals = [((g * 4 + k) * 3 + y * 5) & 1023 for k in range(4)]
                raw[i:i + 5] = bytes([v >> 2 for v in vals] + [sum((v & 3) << (2 * k) for k, v in enumerate(vals))])
        cls.raw = (ctypes.c_uint8 * len(raw)).from_buffer_copy(raw)
        cls.raw_size = len(raw)

    @classmethod
    def tearDownClass(cls):
        # Windows keeps the DLL mapped until process exit; TemporaryDirectory's
        # cleanup cannot remove that file. Explicitly unload this test DLL first.
        import _ctypes
        _ctypes.FreeLibrary(cls.lib._handle)
        del cls.lib
        cls.tmp.cleanup()

    def render(self, offset=0, count=SIZE):
        dst = (ctypes.c_uint8 * count)()
        written = ctypes.c_size_t()
        rc = self.read(self.raw, self.raw_size, offset, dst, count, ctypes.byref(written))
        self.assertEqual(rc, 0)
        return bytes(dst[:written.value])

    def test_header_and_every_pixel(self):
        bmp = self.render()
        self.assertEqual(len(bmp), SIZE)
        self.assertEqual(bmp[:2], b"BM")
        self.assertEqual(struct.unpack_from("<I", bmp, 2)[0], SIZE)
        self.assertEqual(struct.unpack_from("<IIIHHI", bmp, 14), (40, 128, 156, 1, 24, 0))
        for file_y in range(156):
            y = 155 - file_y
            sy = ((2 * y + 1) * 1364) // 312
            for x in range(128):
                sx = ((2 * x + 1) * 1120) // 256
                value = ((sx * 3 + sy * 5) & 1023) >> 2
                p = 54 + (file_y * 128 + x) * 3
                self.assertEqual(bmp[p:p + 3], bytes([value] * 3))

    def test_arbitrary_chunk_boundaries(self):
        expected = self.render()
        offsets = list(range(0, SIZE, 509))
        random.Random(5).shuffle(offsets)
        for off in offsets:
            self.assertEqual(self.render(off, 509), expected[off:off + 509])
        self.assertEqual(self.render(SIZE, 20), b"")

    def test_invalid_inputs(self):
        dst = (ctypes.c_uint8 * 20)()
        n = ctypes.c_size_t(99)
        self.assertEqual(self.read(self.raw, self.raw_size - 1, 0, dst, 20, ctypes.byref(n)), -1)
        self.assertEqual(n.value, 0)
        self.assertEqual(self.read(self.raw, self.raw_size, SIZE + 1, dst, 20, ctypes.byref(n)), -1)

    def test_native_windows_decode(self):
        exe = ROOT / "tmp/usb-ptp-host/wpd_camera.exe"
        if not exe.exists():
            self.skipTest("Native WPD/WIC tool not built")
        out = pathlib.Path(self.tmp.name) / "thumbnail.bmp"
        out.write_bytes(self.render())
        result = subprocess.run([str(exe), "decode", "--file", str(out)], capture_output=True,
                                encoding="utf-8", check=True)
        result = json.loads(result.stdout)
        self.assertEqual((result["width"], result["height"]), (128, 156))
        self.assertGreater(result["max"], result["min"])


if __name__ == "__main__":
    unittest.main()
