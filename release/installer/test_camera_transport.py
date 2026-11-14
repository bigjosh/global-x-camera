"""Offline CubeProgrammer boundary tests; never execute a programmer."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import camera_install as install


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.transport = install.Transport(self.root / "fake-cli", "TEST123", self.root / "logs")

    def test_macos_upload_uses_binary_extension_and_no_windows_flags(self):
        def run(argv, **kwargs):
            self.assertNotIn("creationflags", kwargs)
            self.assertIn("sn=TEST123", argv)
            self.assertIn("ap=1", argv)
            self.assertNotIn("-el", argv)
            self.assertNotIn("-halt", argv)
            output = Path(argv[-1])
            self.assertEqual(output.suffix, ".bin")
            output.write_bytes(b"test")
            return subprocess.CompletedProcess(argv, 0, b"Upload complete")
        with patch.object(install.sys, "platform", "darwin"), patch.object(install.subprocess, "run", side_effect=run):
            self.assertEqual(self.transport.upload(0x341F7000, 4, "recovery-status"), b"test")

    def test_timeout_is_not_retried_or_followed_by_a_reset(self):
        error = subprocess.TimeoutExpired(["fake"], 5, output=b"partial log")
        with patch.object(install.subprocess, "run", side_effect=error) as run:
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                self.transport.call("-u", "0x341B4100", "224", "status.bin")
        self.assertEqual(run.call_count, 1)
        self.assertEqual(self.transport.halt_requests, 0)
        self.assertEqual((self.root / "logs/cli-0001.log").read_bytes(), b"partial log")

    def test_zero_exit_status_with_cli_error_is_failure(self):
        result = subprocess.CompletedProcess([], 0, b"Error: target unavailable")
        with patch.object(install.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "command failed"):
                self.transport.call("-u", "0x341B4100", "224", "status.bin")

    def test_short_upload_is_rejected(self):
        def run(argv, **kwargs):
            Path(argv[-1]).write_bytes(b"x")
            return subprocess.CompletedProcess(argv, 0, b"Upload complete")
        with patch.object(install.subprocess, "run", side_effect=run):
            with self.assertRaisesRegex(RuntimeError, "Incomplete"):
                self.transport.upload(0x341F7000, 4, "status.bin")

    def test_native_mac_application_path(self):
        app = self.root / "Programmer with spaces.app"
        cli = app / "Contents/Resources/bin/STM32_Programmer_CLI"
        cli.parent.mkdir(parents=True)
        cli.write_bytes(b"not executable")
        self.assertEqual(install.find_cube(app), cli)

    def test_intel_mac_application_path(self):
        app = self.root / "Intel.app"
        cli = app / "Contents/MacOs/bin/STM32_Programmer_CLI"
        cli.parent.mkdir(parents=True)
        cli.write_bytes(b"not executable")
        self.assertEqual(install.find_cube(app), cli)


if __name__ == "__main__":
    unittest.main()
