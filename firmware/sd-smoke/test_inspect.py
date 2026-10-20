"""Host verifier must not report successful SD readback on partial evidence."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import re
import struct
import sys
import tempfile
import unittest
import zlib

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("sd_smoke_inspect", HERE / "inspect.py")
inspect = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspect)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        fields = re.search(r"enum \{ (MAGIC,.*?)STATUS_WORDS \};",
                           (HERE / "smoke.c").read_text(), re.S).group(1)
        self.fields = [f.strip().lower() for f in fields.split(",") if f.strip()]
        self.manifest = {"status_words": len(self.fields), "status_fields": self.fields,
                         "buffer_order": [f"buffer_{i}" for i in range(6)]}
        (self.root / "manifest.json").write_text(json.dumps(self.manifest))
        self.s = {key: 0 for key in self.fields}
        self.s.update(magic=0x53445231, schema=1, words=len(self.fields), stage=9,
                      request_max_hz=25000000, read_count=6, read_match_mask=0x3C,
                      cleanup=3)
        sector0 = bytes(range(256)) * 2
        sector1 = bytes(reversed(range(256))) * 2
        self.data = (sector0 + sector1) * 3
        for i in range(6):
            self.s[f"read_crc{i}"] = zlib.crc32(self.data[i*512:(i+1)*512])

    def tearDown(self):
        self.temporary.cleanup()

    def report(self, with_data=True):
        status = self.root / "status.bin"
        status.write_bytes(struct.pack("<" + "I"*len(self.fields),
                                       *(self.s[f] for f in self.fields)))
        args = ["inspect.py", "--build", str(self.root), "--status", str(status)]
        if with_data:
            data = self.root / "data.bin"
            data.write_bytes(self.data)
            args += ["--data", str(data)]
        output = io.StringIO()
        old_argv = sys.argv
        try:
            sys.argv = args
            with contextlib.redirect_stdout(output):
                inspect.main()
        finally:
            sys.argv = old_argv
        return json.loads(output.getvalue())

    def test_complete_crc_verified_equal_reads_pass(self):
        self.assertTrue(self.report()["read_smoke_pass"])

    def test_device_status_without_data_is_not_verified_pass(self):
        report = self.report(False)
        self.assertTrue(report["device_reported_pass"])
        self.assertFalse(report["read_smoke_pass"])

    def test_corrupted_host_buffer_rejected(self):
        self.data = b"\xff" + self.data[1:]
        with self.assertRaisesRegex(ValueError, "CRC32 differs"):
            self.report()

    def test_equal_crc_to_firmware_does_not_hide_differing_repeat(self):
        self.data = self.data[:1024] + b"\xff" + self.data[1025:]
        self.s["read_crc2"] = zlib.crc32(self.data[1024:1536])
        self.assertFalse(self.report()["read_smoke_pass"])

    def test_incomplete_target_compare_evidence_does_not_pass(self):
        self.s["read_match_mask"] = 0x1C
        self.assertFalse(self.report()["read_smoke_pass"])

    def test_bad_request_status_can_be_inspected(self):
        self.s.update(request_max_hz=0, result=1, read_count=0, read_match_mask=0)
        self.assertFalse(self.report(False)["read_smoke_pass"])


if __name__ == "__main__":
    unittest.main()
