"""Offline CLI guards and native WIC PNG16 decode; never contacts a WPD device."""
import json
import pathlib
import struct
import subprocess
import tempfile
import time
import unittest
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
EXE = ROOT / "tmp/usb-ptp-host/wpd_camera.exe"


def invoke(*args):
    return subprocess.run([str(EXE), *args], capture_output=True, text=True,
                          encoding="utf-8", check=False, timeout=15)


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


@unittest.skipUnless(EXE.exists(), "Build native host executable first")
class OfflineHostTests(unittest.TestCase):
    def test_json_selftest(self):
        result = invoke("selftest")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(json.loads(result.stdout)["hardware_access"])

    def test_unknown_action_rejected_before_com(self):
        result = invoke("not-a-command")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["where"], "unknown command")

    def test_missing_delete_confirmation_rejected_before_com(self):
        result = invoke("delete", "--device", "NEVER_OPEN", "--object", "PHOTO")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["where"], "missing required argument")

    def test_wrong_delete_confirmation_rejected_before_com(self):
        result = invoke("delete", "--device", "NEVER_OPEN", "--object", "PHOTO", "--confirm-object", "OTHER")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["where"], "delete object confirmation differs")

    def test_duplicate_arg_rejected_before_com(self):
        result = invoke("get", "--device", "NEVER_OPEN", "--device", "OTHER")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["where"], "invalid/duplicate argument")

    def test_async_cancel_overlaps_pending_scope_and_disarms(self):
        result = invoke("async-selftest")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        events = [json.loads(line) for line in result.stdout.splitlines()]
        starts = [e for e in events if e["event"] == "async_cancel_begin"]
        self.assertEqual(len(starts), 1)
        self.assertTrue(starts[0]["api_scope_active_observed"])
        read_start = next(e for e in events if e["event"] == "wpd_api_begin")
        read_end = next(e for e in events if e["event"] == "wpd_api_end")
        self.assertLess(read_start["mono_us"], starts[0]["mono_us"])
        self.assertLessEqual(starts[0]["mono_us"], read_end["mono_us"])
        self.assertNotEqual(read_start["thread_id"], starts[0]["thread_id"])
        summaries = [e for e in events if e["event"] == "async_cancel_summary"]
        self.assertEqual([s["attempted"] for s in summaries], [True, False])
        self.assertTrue(all(s["worker_joined"] for s in summaries))
        self.assertFalse(events[-1]["hardware_access"])

    def test_stalled_cancel_worker_has_bounded_cleanup(self):
        start = time.monotonic()
        result = invoke("async-stall-selftest")
        elapsed = time.monotonic() - start
        self.assertEqual(result.returncode, 124, result.stdout + result.stderr)
        self.assertLess(elapsed, 3)
        events = [json.loads(line) for line in result.stdout.splitlines()]
        timeout = next(e for e in events if e["event"] == "async_cancel_worker_timeout")
        self.assertEqual(timeout["join_timeout_ms"], 30)
        self.assertFalse(timeout["device_idle_proven"])

    def test_invalid_async_thresholds_rejected_before_com(self):
        for value in ("0", "-1", "100x", "60001", "999999999999999999999999999"):
            with self.subTest(value=value):
                result = invoke("get", "--device", "NEVER_OPEN", "--object", "PHOTO",
                                "--out", "NEVER_CREATE", "--cancel-ms", value)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(json.loads(result.stdout)["where"], "invalid cancellation threshold")

    def test_two_cancel_modes_rejected_before_com(self):
        result = invoke("get", "--device", "NEVER_OPEN", "--object", "PHOTO",
                        "--out", "NEVER_CREATE", "--cancel-ms", "100", "--cancel-after", "1024")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["where"], "choose one cancellation mode")

    def test_wic_gray16_and_shift6_preserved(self):
        samples = [0, 64, 32768, 65472]
        png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 1, 16, 0, 0, 0, 0))
        png += chunk(b"sBIT", b"\x0a") + chunk(b"gAMA", struct.pack(">I", 100000))
        png += chunk(b"IDAT", zlib.compress(b"\x00" + struct.pack(">4H", *samples))) + chunk(b"IEND", b"")
        with tempfile.TemporaryDirectory(prefix="wpd-offline-") as tmp:
            path = pathlib.Path(tmp) / "gray16.png"
            path.write_bytes(png)
            result = invoke("decode", "--file", str(path))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            decoded = json.loads(result.stdout)
            self.assertTrue(decoded["native_gray16"])
            self.assertEqual(decoded["sum"], sum(samples))
            self.assertEqual(decoded["max"], 65472)
            self.assertEqual(decoded["nonzero_low6_pixels"], 0)


if __name__ == "__main__":
    unittest.main()
