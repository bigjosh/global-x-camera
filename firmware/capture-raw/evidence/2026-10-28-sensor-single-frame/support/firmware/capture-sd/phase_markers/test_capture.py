"""Mock-only API contract tests; no saleae/USB/device import is required."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import capture


class FakeAPI:
    LogicDeviceConfiguration = SimpleNamespace
    CaptureConfiguration = SimpleNamespace
    TimedCaptureMode = SimpleNamespace

    def __init__(self, fail_wait=False, simulation=False):
        self.calls = []
        self.fail_wait = fail_wait
        self.simulation = simulation
        self.Manager = SimpleNamespace(connect=self.connect)

    def connect(self, **kwargs):
        self.calls.append(("connect", kwargs)); return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.calls.append(("close", None))

    def get_devices(self):
        return [SimpleNamespace(device_id=capture.DEVICE, is_simulation=self.simulation)]

    def get_app_info(self):
        return "offline mock only"

    def start_capture(self, **kwargs):
        self.calls.append(("start", kwargs)); return self

    def wait(self):
        self.calls.append(("wait", None))
        if self.fail_wait:
            raise RuntimeError("mock capture failed")

    def save_capture(self, path):
        self.calls.append(("save", path)); Path(path).write_bytes(b"mock")

    def export_raw_data_binary(self, directory, **kwargs):
        self.calls.append(("export", kwargs))
        for channel in kwargs["digital_channels"]:
            (Path(directory) / f"digital_{channel}.bin").write_bytes(b"mock")
        for channel in kwargs["analog_channels"]:
            (Path(directory) / f"analog_{channel}.bin").write_bytes(b"mock")


class CaptureTests(unittest.TestCase):
    def test_configuration_timed_order_and_no_stimulus(self):
        for analog in (False, True):
            with tempfile.TemporaryDirectory() as name, redirect_stdout(io.StringIO()):
                api = FakeAPI()
                out = Path(name) / "new"
                result = capture.capture(out, probes_confirmed=True, analog_power=analog, api=api)
                names = [c[0] for c in api.calls]
                self.assertEqual(names, ["connect", "start", "wait", "save", "export", "close", "close"])
                start = api.calls[1][1]
                dc, cc = start["device_configuration"], start["capture_configuration"]
                self.assertEqual(dc.enabled_digital_channels, [0, 1, 4, 6])
                self.assertEqual(dc.digital_sample_rate, 100000000)
                self.assertEqual(dc.enabled_analog_channels, [4] if analog else [])
                self.assertEqual(dc.analog_sample_rate, 31250 if analog else None)
                self.assertEqual(cc.capture_mode.duration_seconds, 10)
                self.assertEqual(result["target_stimulus"], "none")
                self.assertTrue((out / "started").is_file())
                self.assertNotIn("actual_standby_verified", result)

    def test_failure_retained_without_export_or_retry(self):
        with tempfile.TemporaryDirectory() as name, redirect_stdout(io.StringIO()):
            api = FakeAPI(fail_wait=True); out = Path(name) / "new"
            with self.assertRaisesRegex(RuntimeError, "mock capture failed"):
                capture.capture(out, probes_confirmed=True, api=api)
            result = json.loads((out / "capture-config.json").read_text())
            self.assertIn("error", result)
            self.assertNotIn("save", [x[0] for x in api.calls])
            self.assertEqual([x[0] for x in api.calls].count("start"), 1)

    def test_bad_configuration_rejected_before_output_or_api(self):
        with tempfile.TemporaryDirectory() as name:
            out = Path(name) / "new"; api = FakeAPI()
            for kwargs in (dict(probes_confirmed=False), dict(probes_confirmed=True, seconds=11),
                           dict(probes_confirmed=True, seconds=float("nan")),
                           dict(probes_confirmed=True, analog_power=1)):
                with self.assertRaises(ValueError):
                    capture.capture(out, api=api, **kwargs)
                self.assertFalse(out.exists())
            self.assertEqual(api.calls, [])

    def test_simulated_device_never_started_and_existing_output_never_overwritten(self):
        with tempfile.TemporaryDirectory() as name:
            out = Path(name) / "new"; api = FakeAPI(simulation=True)
            with self.assertRaisesRegex(RuntimeError, "physical"):
                capture.capture(out, probes_confirmed=True, api=api)
            self.assertNotIn("start", [x[0] for x in api.calls])
            before = (out / "capture-config.json").read_bytes()
            with self.assertRaises(FileExistsError):
                capture.capture(out, probes_confirmed=True, api=api)
            self.assertEqual(before, (out / "capture-config.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
