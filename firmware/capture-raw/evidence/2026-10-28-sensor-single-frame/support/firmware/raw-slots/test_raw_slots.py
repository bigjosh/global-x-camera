import importlib.util
import io
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("raw_slots", ROOT / "raw_slots.py")
raw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(raw)


class RawSlotsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("clang") or shutil.which("gcc")
        if not compiler:
            raise RuntimeError("host clang/gcc required to test the actual C core")
        cls.temp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.temp.name)
        exe = cls.folder / "test_core.exe"
        subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                        str(ROOT / "raw_slots.c"), str(ROOT / "test_core.c"), "-o", str(exe)], check=True)
        cls.fixture = cls.folder / "card.img"
        subprocess.run([str(exe), str(cls.fixture)], check=True)
        cls.image = cls.fixture.read_bytes()
        cls.volume = raw.parse_volume(cls.image[:512])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_c_format_and_states(self):
        self.assertEqual(self.volume["slot_count"], 3)
        self.assertEqual(self.volume["generation"], 0xABCDEF1212345678)
        source = io.BytesIO(self.image)
        self.assertEqual([raw.read_slot(source, self.volume, i)["state"] for i in range(3)],
                         ["FULL", "PARTIAL", "FREE"])

    def test_all_decoded_samples(self):
        start = (raw.FIRST_LBA + 1) * 512
        samples = raw.unpack_raw10(self.image[start:start + raw.PAYLOAD_BYTES], shift=0)
        self.assertEqual(len(samples), raw.WIDTH * raw.HEIGHT)
        self.assertTrue(all(value == (i & 1023) for i, value in enumerate(samples)))

    def test_png16_independent_chunk_and_pixel_decode(self):
        output = self.folder / "complete.png"
        record = raw.extract(io.BytesIO(self.image), self.volume, 0, output)
        self.assertTrue(record["tail_padding_zero"])
        data = output.read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        offset, compressed, kinds = 8, bytearray(), []
        while offset < len(data):
            size = struct.unpack_from(">I", data, offset)[0]
            kind = data[offset + 4:offset + 8]
            body = data[offset + 8:offset + 8 + size]
            checksum = struct.unpack_from(">I", data, offset + 8 + size)[0]
            self.assertEqual(zlib.crc32(kind + body), checksum)
            kinds.append(kind)
            if kind == b"IHDR":
                self.assertEqual(struct.unpack(">IIBBBBB", body), (1120, 1364, 16, 0, 0, 0, 0))
            if kind == b"sBIT":
                self.assertEqual(body, b"\x0a")
            if kind == b"IDAT":
                compressed.extend(body)
            offset += size + 12
        scanlines = zlib.decompress(compressed)
        self.assertEqual(len(scanlines), raw.HEIGHT * (1 + 2 * raw.WIDTH))
        for y in range(raw.HEIGHT):
            row = scanlines[y * 2241:(y + 1) * 2241]
            self.assertEqual(row[0], 0)
            samples = struct.unpack(">1120H", row[1:])
            self.assertTrue(all(value == (((y * 1120 + x) & 1023) << 6) for x, value in enumerate(samples)))
        self.assertEqual(kinds[-1], b"IEND")

    def test_extract_exact_raw_and_existing_destination_refused(self):
        output = self.folder / "complete.raw10"
        raw.extract(io.BytesIO(self.image), self.volume, 0, output, kind="raw")
        start = (raw.FIRST_LBA + 1) * 512
        self.assertEqual(output.read_bytes(), self.image[start:start + raw.PAYLOAD_BYTES])
        with self.assertRaises(FileExistsError):
            raw.extract(io.BytesIO(self.image), self.volume, 0, output, kind="raw")

    def test_partial_and_free_default_refusal(self):
        for i in (1, 2):
            with self.assertRaises(raw.FormatError):
                raw.extract(io.BytesIO(self.image), self.volume, i, self.folder / f"refuse{i}.raw", kind="raw")
        result = raw.extract(io.BytesIO(self.image), self.volume, 1, self.folder / "salvage.raw",
                             kind="raw", allow_partial=True)
        self.assertIn("stale", result["warning"])

    def test_corrupt_header(self):
        header = bytearray(self.image[raw.FIRST_LBA * 512:(raw.FIRST_LBA + 1) * 512])
        header[100] ^= 1
        with self.assertRaises(raw.FormatError):
            raw.parse_slot(header, self.volume, 0)
        for byte in (0, 255):
            with self.assertRaises(raw.FormatError):
                raw.parse_slot(bytes([byte]) * 512, self.volume, 0)

    def test_foreign_generation_and_invalid_index(self):
        header = bytearray(self.image[raw.FIRST_LBA * 512:(raw.FIRST_LBA + 1) * 512])
        header[16] ^= 1
        struct.pack_into("<I", header, 508, zlib.crc32(header[:508]))
        with self.assertRaises(raw.FormatError):
            raw.parse_slot(header, self.volume, 0)
        with self.assertRaises(raw.FormatError):
            raw.read_slot(io.BytesIO(self.image), self.volume, 3)
        with self.assertRaises(raw.FormatError):
            raw.read_slot(io.BytesIO(self.image), self.volume, -1)

    def test_prefix_image_extracts_known_complete_slot(self):
        # Only a volume prefix is present; do not mistake its size for verified
        # physical card capacity. A requested missing slot still fails short.
        prefix = self.image[:(raw.FIRST_LBA + raw.STRIDE) * 512]
        output = self.folder / "prefix.raw10"
        result = raw.extract(io.BytesIO(prefix), self.volume, 0, output, kind="raw")
        self.assertEqual(result["state"], "FULL")
        with self.assertRaises(raw.FormatError):
            raw.read_slot(io.BytesIO(prefix), self.volume, 1)

    def test_formatting_and_short_read(self):
        volume = bytearray(self.image[:512])
        struct.pack_into("<I", volume, 12, 1)
        struct.pack_into("<I", volume, 508, zlib.crc32(volume[:508]))
        with self.assertRaises(raw.FormatError):
            raw.parse_volume(volume)
        self.assertEqual(raw.parse_volume(volume, allow_formatting=True)["state"], "FORMATTING")
        with self.assertRaises(raw.FormatError):
            raw.read_sectors(io.BytesIO(b"x" * 511), 0)


if __name__ == "__main__":
    unittest.main()
