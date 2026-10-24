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
spec = importlib.util.spec_from_file_location("magic_slots", ROOT / "magic_slots.py")
magic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(magic)


class MagicSlotsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("clang") or shutil.which("gcc")
        if not compiler:
            raise RuntimeError("host clang/gcc required to test the actual C core")
        cls.temp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.temp.name)
        exe = cls.folder / "test_magic_core.exe"
        subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                        str(ROOT / "magic_slots.c"), str(ROOT / "test_magic_core.c"), "-o", str(exe)], check=True)
        fixture = cls.folder / "card.img"
        subprocess.run([str(exe), str(fixture)], check=True)
        cls.image = fixture.read_bytes()
        cls.layout = magic.layout(len(cls.image) // 512, 255)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_geometry_and_c_fixture_states(self):
        self.assertEqual(magic.PADDING_BYTES, 152)
        self.assertEqual(magic.OBJECT_BYTES, 1909608)
        self.assertEqual(self.layout["slot_count"], 3)
        self.assertEqual([magic.read_slot(io.BytesIO(self.image), self.layout, i)["state"] for i in range(3)],
                         ["COMPLETE", "PARTIAL", "FREE"])

    def test_occupancy_uses_all_four_bytes(self):
        for erased in (0, 255):
            header = bytearray([erased]) * 512
            self.assertEqual(magic.parse_probe(header, None, index=0, erased_byte=erased)["state"], "FREE")
            for byte in range(4):
                changed = header.copy()
                changed[byte] ^= 1
                record = magic.parse_probe(changed, None, index=0, erased_byte=erased)
                self.assertTrue(record["occupied"])
                self.assertEqual(record["state"], "OCCUPIED")

    def test_truncated_or_missing_trailer_never_complete(self):
        full = self.image[:magic.PADDED_BYTES]
        for size in (512, magic.TRAILER_OFFSET, magic.PADDED_BYTES - 1):
            record = magic.parse_slot(full[:size], erased_byte=255)
            self.assertTrue(record["occupied"])
            self.assertEqual(record["state"], "PARTIAL")
        damaged = bytearray(full)
        damaged[magic.TRAILER_OFFSET] ^= 1
        self.assertEqual(magic.parse_slot(damaged, erased_byte=255)["state"], "PARTIAL")
        damaged = bytearray(full)
        damaged[0] ^= 1
        self.assertEqual(magic.parse_slot(damaged, erased_byte=255)["state"], "OCCUPIED")

    def test_full_image_exact_raw_decode(self):
        result = self.folder / "exact.raw10"
        record = magic.extract(io.BytesIO(self.image), self.layout, 0, result, kind="raw")
        self.assertEqual(record["state"], "COMPLETE")
        self.assertTrue(record["tail_padding_zero"])
        self.assertEqual(result.read_bytes(), self.image[4:magic.TRAILER_OFFSET])
        values = magic.unpack_raw10(result.read_bytes(), shift=0)
        self.assertEqual(len(values), 1120 * 1364)
        self.assertTrue(all(value == (index & 1023) for index, value in enumerate(values)))
        with self.assertRaises(FileExistsError):
            magic.extract(io.BytesIO(self.image), self.layout, 0, result, kind="raw")

    def test_png_independent_crc_and_pixels(self):
        output = self.folder / "exact.png"
        magic.extract(io.BytesIO(self.image), self.layout, 0, output)
        data = output.read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        offset, compressed = 8, bytearray()
        while offset < len(data):
            length = struct.unpack_from(">I", data, offset)[0]
            kind = data[offset + 4:offset + 8]
            body = data[offset + 8:offset + 8 + length]
            self.assertEqual(zlib.crc32(kind + body), struct.unpack_from(">I", data, offset + length + 8)[0])
            if kind == b"IHDR":
                self.assertEqual(struct.unpack(">IIBBBBB", body), (1120, 1364, 16, 0, 0, 0, 0))
            if kind == b"sBIT":
                self.assertEqual(body, b"\x0a")
            if kind == b"IDAT":
                compressed.extend(body)
            offset += length + 12
        scanlines = zlib.decompress(compressed)
        self.assertEqual(len(scanlines), 1364 * 2241)
        for y in range(1364):
            row = scanlines[y * 2241:(y + 1) * 2241]
            self.assertEqual(row[0], 0)
            self.assertTrue(all(value == (((y * 1120 + x) & 1023) << 6)
                                for x, value in enumerate(struct.unpack(">1120H", row[1:]))))

    def test_partial_salvage_and_free_refused(self):
        for index in (1, 2):
            with self.assertRaises(magic.FormatError):
                magic.extract(io.BytesIO(self.image), self.layout, index, self.folder / f"refuse{index}.raw", kind="raw")
        output = self.folder / "recovered.raw10"
        record = magic.extract(io.BytesIO(self.image), self.layout, 1, output, kind="raw", allow_partial=True)
        self.assertEqual(record["state"], "PARTIAL")
        self.assertIn("corrupt", record["warning"])
        self.assertEqual(output.stat().st_size, magic.IMAGE_BYTES)
        with self.assertRaises(magic.FormatError):
            magic.extract(io.BytesIO(self.image), self.layout, 2, self.folder / "free.raw", kind="raw", allow_partial=True)

    def test_padding_damage_is_reported_without_hiding_data(self):
        image = bytearray(self.image)
        image[magic.OBJECT_BYTES] = 1
        record = magic.parse_slot(image[:magic.PADDED_BYTES], erased_byte=255)
        self.assertEqual(record["state"], "COMPLETE")
        self.assertFalse(record["tail_padding_zero"])
        self.assertIn("damaged", record["warning"])
        self.assertFalse(record["checksummed"])

    def test_bad_geometry_indexes_and_reads_fail(self):
        for capacity, erased in ((3729, 0), (1 << 33, 255), (3730, 1)):
            with self.assertRaises(magic.FormatError):
                magic.layout(capacity, erased)
        for index in (-1, 3):
            with self.assertRaises(magic.FormatError):
                magic.read_slot(io.BytesIO(self.image), self.layout, index)
        with self.assertRaises(magic.FormatError):
            magic.read_slot(io.BytesIO(self.image[:511]), self.layout, 0)
        with self.assertRaises(magic.FormatError):
            magic.read_slot(io.BytesIO(self.image[:512]), self.layout, 0)
        with self.assertRaises(magic.FormatError):
            magic.parse_slot(b"", erased_byte=255)


if __name__ == "__main__":
    unittest.main()
