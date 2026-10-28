"""Offline queue backpressure and lifecycle tests; no device API is imported."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[2] / "capture-sd"))
import js110_session as session
from js110_raw import make_raw_stream, MEASUREMENT_TOPICS
from test_js110_power import PowerDriver
import cycle_energy


class QueueTests(unittest.TestCase):
    def test_invalid_capacity_rejected_before_output_creation(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            for value in (False, 0, -1, 1025, 1.5, "64"):
                with self.subTest(value=value):
                    with self.assertRaisesRegex(ValueError, "queue size"):
                        make_raw_stream(session.StreamLog, root / "raw", queue_chunks=value)
                    self.assertFalse((root / "raw").exists())
                    with self.assertRaisesRegex(ValueError, "queue size"):
                        session.StreamLog(root / "stream", queue_chunks=value)
                    self.assertFalse((root / "stream").exists())

    def test_larger_queue_preserves_burst_default_overflow_still_invalidates(self):
        # Stop the actual writer while callbacks continue. This creates the
        # observed failure mechanism deterministically without sleeps or disks
        # deliberately slowed at the operating-system level.
        for capacity in (None, 1024):
            with self.subTest(capacity=capacity), tempfile.TemporaryDirectory() as name:
                entered, release = threading.Event(), threading.Event()

                class PausedWriter(session.StreamLog):
                    def summarize(self, *args):
                        if not entered.is_set():
                            entered.set()
                            if not release.wait(5):
                                raise RuntimeError("Test writer was not released")
                        return super().summarize(*args)

                root = Path(name) / "raw"
                kwargs = {} if capacity is None else dict(queue_chunks=capacity)
                logger = make_raw_stream(PausedWriter, root, **kwargs)

                def send(signal, offset):
                    logger.receive("s/" + signal + "/!data", dict(
                        sample_id=offset, sample_rate=2000000,
                        decimate_factor=1, utc=0, time_map={},
                        data=np.arange(offset, offset + 4, dtype=np.float32)))

                try:
                    send("i", 0)
                    self.assertTrue(entered.wait(5))
                    send("v", 0)
                    send("p", 0)
                    for offset in range(4, 132, 4):
                        for signal in ("i", "v", "p"):
                            send(signal, offset)
                finally:
                    release.set()
                    status = logger.close()
                manifest = json.loads((root / "manifest.json").read_text())
                self.assertEqual(manifest["raw_queue_chunks"], capacity or 64)
                if capacity is None:
                    self.assertGreater(status["dropped_chunks"], 0)
                    self.assertFalse(manifest["finalized"])
                    with self.assertRaisesRegex(ValueError, "finalized"):
                        cycle_energy.Archive(root)
                else:
                    self.assertEqual(status["dropped_chunks"], 0)
                    self.assertTrue(manifest["finalized"])
                    with cycle_energy.Archive(root) as archive:
                        for signal in ("current", "voltage", "power"):
                            np.testing.assert_equal(archive.get(signal, 0, 132),
                                                    np.arange(132, dtype=np.float32))

    def test_session_forwards_capacity_and_preserves_settings(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            args = SimpleNamespace(device="u/js110/fake", duration=5,
                control=root / "control", response=root / "response", log=root / "log",
                stream_log=None, power_stream_log=None, cycle_raw_dir=root / "raw",
                raw_max_mib=1, raw_queue_chunks=1024, recovery_output=False)
            driver = PowerDriver()
            for topic in MEASUREMENT_TOPICS:
                driver.initial.setdefault(topic, 0)
                driver.settings.setdefault(topic, 0)
            emit_original = session.Reporter.emit

            def emit(reporter, event, **values):
                emit_original(reporter, event, **values)
                if event == "ready":
                    driver.deliver()
                    args.control.write_text(json.dumps(dict(id="stop", state="stop")))

            with patch.object(session.Reporter, "emit", emit), redirect_stdout(io.StringIO()):
                code = session.run_session(args, lambda: driver, "offline-fake")
            self.assertEqual(code, 0)
            self.assertEqual(driver.settings, driver.initial)
            self.assertEqual([v for v in driver.commands if v[0] == session.RANGE_TOPIC],
                             [(session.RANGE_TOPIC, 128)])
            manifest = json.loads((args.cycle_raw_dir / "manifest.json").read_text())
            self.assertEqual(manifest["raw_queue_chunks"], 1024)
            self.assertTrue(manifest["finalized"])
            first = json.loads((args.cycle_raw_dir / "chunks.jsonl").read_text().splitlines()[0])
            self.assertEqual(first["raw_queue_chunks"], 1024)

    def test_cli_rejects_bad_or_unused_override_before_device_import(self):
        for flags in (("--raw-queue-chunks", "0"),
                      ("--raw-queue-chunks", "1025"),
                      ("--raw-queue-chunks", "1024")):
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                argv = ["js110_session", "--control", str(root / "control"),
                        "--response", str(root / "response"), "--log", str(root / "log"),
                        *flags]
                with patch.object(sys, "argv", argv), redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as exc:
                        session.main()
                self.assertEqual(exc.exception.code, 2)
                self.assertEqual(list(root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
