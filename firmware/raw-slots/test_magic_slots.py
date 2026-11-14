import importlib.util
import io
import json
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


class ControlsMetadataTest(unittest.TestCase):
    """Independent serialized fixtures, without importing the firmware decoder."""

    def fixture(self, state=3, requested=1000, asa=100):
        coarse = (requested * 160800000 + 1279999999) // 1280000000
        gain = {100: 0, 200: 16, 400: 24, 800: 28}[asa]
        asa_raw = {100: 0, 200: 1280, 400: 2560, 800: 3840}[asa]
        exposure_raw = 3840 if requested == 1000 else 0
        words = [0] * 32
        words[:16] = [0x314E4B43, 1, 128, state, 0, 23 if state == 3 else 31,
                      0, 3840, 3840, exposure_raw, asa_raw,
                      0 if exposure_raw else 65535, (asa_raw * 65535 + 1920) // 3840,
                      requested, 1280, max(4336, coarse + 2000)]
        words[19:25] = [asa, 160800000, coarse if state == 4 else 0,
                        gain if state == 4 else 0, 256 if state == 4 else 0, 34]
        data = bytearray(struct.pack("<32I", *words) + bytes(24))
        data[64:76] = bytes((2, gain)) + struct.pack("<H", coarse) + b"\0\1" * 4
        return self.crc(data)

    @staticmethod
    def crc(data):
        struct.pack_into("<I", data, 124, zlib.crc32(data[:124]))
        return data

    def header(self, metadata):
        return magic.START_MAGIC + metadata + bytes(512 - magic.IMAGE_OFFSET)

    def test_configured_and_applied_are_distinct(self):
        for state in (3, 4):
            for asa in (100, 200, 400, 800):
                with self.subTest(state=state, asa=asa):
                    record = magic.parse_header(self.header(self.fixture(state, asa=asa)), index=0, erased_byte=0)
                    controls = record["controls"]
                    self.assertEqual(record["state"], "OCCUPIED")
                    self.assertIsNone(record["completion_marker_valid"])
                    self.assertFalse(record["checksummed"])
                    self.assertEqual(controls["asa"], asa)
                    self.assertTrue(controls["asa_provisional"])
                    self.assertEqual(controls["analog_gain"], asa // 100)
                    self.assertEqual(controls["sensor_readback_verified"], state == 4)
                    self.assertEqual("applied_registers" in controls, state == 4)

    def test_half_second_register_rounding_is_visible(self):
        record = magic.decode_controls_record(self.fixture(4, 500000, 800))
        self.assertEqual(record["coarse_lines"], 62813)
        self.assertEqual(record["frame_length"], 64813)
        self.assertAlmostEqual(record["nominal_exposure_us"], 500003.9800995025)

    def test_bad_crc_does_not_change_occupancy_or_completion(self):
        metadata = self.fixture()
        metadata[40] ^= 1
        last = bytes(508) + magic.END_MAGIC
        record = magic.parse_probe(self.header(metadata), last, index=0, erased_byte=0)
        self.assertEqual(record["state"], "COMPLETE")
        self.assertNotIn("controls", record)
        self.assertIsNone(record["metadata_schema"])
        self.assertIn("CRC", record["metadata_warning"])
        self.assertEqual(record["metadata_hex"], metadata.hex())
        partial = magic.parse_probe(self.header(metadata), bytes(512), index=0, erased_byte=0)
        self.assertIn("metadata_warning", partial)
        self.assertIn("warning", partial)

    def test_crc_correct_but_invalid_semantics_are_rejected(self):
        # State, flags, ADC range/normalization, time, line, frame, digital gain,
        # ASA, clock, applied readback, reserve and unchecksummed tail.
        for offset, value in ((12, 2), (20, 23), (24, 129), (44, 1), (52, 500001),
                              (56, 1236), (60, 65536), (68, 0), (76, 1600),
                              (80, 160000000), (84, 0), (116, 1), (128, 1)):
            with self.subTest(offset=offset):
                data = self.fixture(4)
                struct.pack_into("<I", data, offset, value)
                self.crc(data)
                with self.assertRaises(magic.FormatError):
                    magic.decode_controls_record(data)

    def test_old_and_unknown_metadata_stays_opaque(self):
        unknown = self.fixture()
        struct.pack_into("<I", unknown, 4, 2)
        for metadata in (bytes(152), bytes(range(152)), unknown):
            record = magic.parse_header(self.header(metadata), index=0, erased_byte=0)
            self.assertIsNone(record["metadata_schema"])
            self.assertNotIn("controls", record)
            self.assertEqual(record["metadata_hex"], metadata.hex())

    def test_png_comment_includes_validated_controls_and_bad_record_warning(self):
        for damaged in (False, True):
            metadata = self.fixture(4, 500000, 800)
            if damaged:
                metadata[124] ^= 1
            record = magic.parse_header(self.header(metadata), index=0, erased_byte=0)
            png = magic.png16(bytes(magic.IMAGE_BYTES), record)
            offset, found = 8, None
            while offset < len(png):
                length = struct.unpack_from(">I", png, offset)[0]
                if png[offset + 4:offset + 8] == b"tEXt":
                    body = png[offset + 8:offset + 8 + length]
                    found = json.loads(body.split(b"\0", 1)[1])
                offset += 12 + length
            self.assertEqual(found, record)
            self.assertEqual("controls" in found, not damaged)
            self.assertEqual("metadata_warning" in found, damaged)


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
        self.assertEqual(magic.PADDING_BYTES, 0)
        self.assertEqual(magic.METADATA_BYTES, 152)
        self.assertEqual(magic.IMAGE_OFFSET, 156)
        self.assertEqual(magic.OBJECT_BYTES, 1909760)
        self.assertEqual(magic.TRAILER_OFFSET, magic.PADDED_BYTES - 4)
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
        self.assertNotIn("tail_padding_zero", record)
        self.assertEqual(result.read_bytes(), self.image[magic.IMAGE_OFFSET:magic.TRAILER_OFFSET])
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

    def test_arbitrary_metadata_is_preserved_and_not_treated_as_padding(self):
        image = bytearray(self.image[:magic.PADDED_BYTES])
        metadata = bytes((i ^ 0x5a) for i in range(magic.METADATA_BYTES))
        record = magic.parse_slot(image, erased_byte=255)
        self.assertEqual(record["state"], "COMPLETE")
        self.assertEqual(record["metadata_hex"], metadata.hex())
        self.assertIsNone(record["metadata_schema"])
        self.assertNotIn("warning", record)
        self.assertFalse(record["checksummed"])

    def legacy_fixture(self):
        image = bytearray(magic.PADDED_BYTES)
        image[:4] = magic.LEGACY_START_MAGIC
        image[magic.LEGACY_IMAGE_OFFSET:magic.LEGACY_TRAILER_OFFSET] = self.image[
            magic.IMAGE_OFFSET:magic.TRAILER_OFFSET]
        image[magic.LEGACY_TRAILER_OFFSET:magic.LEGACY_OBJECT_BYTES] = magic.END_MAGIC
        return image

    def test_mixed_format_offsets_and_legacy_extraction(self):
        legacy = self.legacy_fixture()
        mixed = legacy + self.image[:magic.PADDED_BYTES]
        volume = magic.layout(len(mixed) // 512, 0)
        old = magic.read_slot(io.BytesIO(mixed), volume, 0)
        new = magic.read_slot(io.BytesIO(mixed), volume, 1)
        self.assertEqual((old["state"], new["state"]), ("COMPLETE", "COMPLETE"))
        self.assertEqual((old["image_offset"], new["image_offset"]), (4, 156))
        self.assertEqual((old["metadata_bytes"], new["metadata_bytes"]), (0, 152))
        self.assertEqual((old["format_revision"], new["format_revision"]), (1, 2))
        self.assertTrue(old["tail_padding_zero"])
        out = self.folder / "legacy.raw10"
        magic.extract(io.BytesIO(mixed), volume, 0, out, kind="raw")
        self.assertEqual(out.read_bytes(), self.image[magic.IMAGE_OFFSET:magic.TRAILER_OFFSET])
        legacy[magic.LEGACY_OBJECT_BYTES] = 1
        record = magic.parse_slot(legacy, erased_byte=0)
        self.assertEqual(record["state"], "COMPLETE")
        self.assertFalse(record["tail_padding_zero"])
        self.assertIn("damaged", record["warning"])

    def test_one_sector_directory_listing_never_claims_completion(self):
        class Counted(io.BytesIO):
            def __init__(self, data):
                super().__init__(data)
                self.read_calls = []

            def read(self, size=-1):
                self.read_calls.append(size)
                return super().read(size)

        for first in (self.image[:512], self.legacy_fixture()[:512]):
            source = Counted(first)
            record = magic.read_header(source, self.layout, 0)
            self.assertEqual(source.read_calls, [512])
            self.assertEqual(record["state"], "OCCUPIED")
            self.assertFalse(record["completion_checked"])
            self.assertIsNone(record["completion_marker_valid"])
        record = magic.read_header(io.BytesIO(self.image[:512]), self.layout, 0)
        self.assertEqual(len(bytes.fromhex(record["metadata_hex"])), 152)

    def test_unknown_magic_cannot_guess_an_extraction_offset(self):
        image = bytearray(self.image)
        image[:4] = b"bad!"
        with self.assertRaisesRegex(magic.FormatError, "offset"):
            magic.extract(io.BytesIO(image), self.layout, 0,
                          self.folder / "unknown.raw10", kind="raw", allow_partial=True)

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
