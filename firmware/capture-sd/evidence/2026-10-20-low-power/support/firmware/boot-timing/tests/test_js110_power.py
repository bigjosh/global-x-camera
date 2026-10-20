"""Power-stream ownership and aggregation tests. Never import a device API."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import js110_session as session
from test_js110_recovery import FakeDriver


class PowerDriver(FakeDriver):
    def __init__(self, failures=None):
        super().__init__({"h/fs": 100000, "s/i/ctrl": 0, "s/v/ctrl": 1,
                          "s/p/ctrl": 0}, failures)
        self.callbacks = {}
        self.subscriptions = []
        self.unsubscriptions = []

    def subscribe(self, topic, flags, callback):
        self.callbacks[topic] = callback
        self.subscriptions.append(topic)

    def unsubscribe(self, topic, callback, **kwargs):
        self.unsubscriptions.append(topic)

    def deliver(self):
        for topic, callback in list(self.callbacks.items()):
            if topic.endswith("/!data"):
                callback(topic, dict(sample_id=100, sample_rate=2000000, decimate_factor=1,
                    utc=0, time_map={"offset_time":0, "offset_counter":100, "counter_rate":2000000},
                    data=np.array([1,2,3,4], dtype=np.float32)))


class PowerTests(unittest.TestCase):
    def run_session(self, power=True, failures=None):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            args = SimpleNamespace(device="u/js110/fake", duration=5,
                control=root/"control", response=root/"response", log=root/"log",
                stream_log=None if power else root/"stream",
                power_stream_log=root/"stream" if power else None, recovery_output=False)
            driver = PowerDriver(failures)
            old = session.Reporter.emit

            def emit(reporter, event, **values):
                old(reporter, event, **values)
                if event == "ready":
                    driver.deliver()
                    args.control.write_text(json.dumps(dict(id="stop", state="stop")))
            with patch.object(session.Reporter, "emit", emit), redirect_stdout(io.StringIO()):
                code = session.run_session(args, lambda: driver, "offline-fake")
            logs = [json.loads(line) for line in (root/"stream").read_text().splitlines()]
            return code, driver, logs

    def test_power_enabled_and_all_starting_settings_restored(self):
        code, driver, logs = self.run_session()
        self.assertEqual(code, 0)
        self.assertEqual(driver.settings, driver.initial)
        self.assertEqual(logs[0]["schema"], 2)
        power = next(v for v in logs if v.get("signal") == "power")
        self.assertEqual(power["sum"], 10)
        self.assertEqual(power["sample_id_end_exclusive"], 104)
        self.assertEqual(power["nonfinite_count"], 0)
        self.assertIn("u/js110/fake/s/p/!data", driver.unsubscriptions)
        self.assertEqual([v for v in driver.commands if v[0] == session.RANGE_TOPIC],
                         [(session.RANGE_TOPIC, 128)])
        self.assertTrue(logs[-1]["coverage"]["checks"]["power_sample_ids_contiguous"])
        # Independently consume the actual logger output through the analyzer.
        import importlib.util
        path = Path(__file__).resolve().parents[2]/"capture-sd"/"energy.py"
        spec = importlib.util.spec_from_file_location("energy_power_test", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        analysis = module.analyze(logs, {"start_sample_id":100, "end_sample_id":104})
        self.assertEqual(analysis["energy_bounds_j"], [5e-6, 5e-6])

    def test_legacy_stream_never_accesses_power_setting_or_changes_schema(self):
        code, driver, logs = self.run_session(power=False)
        self.assertEqual(code, 0)
        self.assertFalse(any("s/p/" in t for t in driver.queries+driver.subscriptions))
        self.assertFalse(any("s/p/" in t for t, _ in driver.commands))
        self.assertEqual(logs[0]["schema"], 1)
        self.assertTrue(all("sum" not in v for v in logs))

    def test_failed_power_enable_restores_even_if_device_changed_before_error(self):
        code, driver, _ = self.run_session(failures={("s/p/ctrl", 1): 1})
        self.assertEqual(code, 1)
        self.assertEqual(driver.settings, driver.initial)
        self.assertIn(("s/p/ctrl", 0), driver.commands)
        self.assertIn(("h/fs", 100000), driver.commands)
        self.assertIn(("s/sstats/ctrl", 0), driver.commands)

    def test_restore_failure_does_not_skip_other_restoration(self):
        code, driver, _ = self.run_session(failures={("s/p/ctrl", 0): 1})
        self.assertEqual(code, 1)
        self.assertEqual(driver.settings, driver.initial)
        self.assertIn(("h/fs", 100000), driver.commands)
        self.assertIn(("s/sstats/ctrl", 0), driver.commands)

    def test_nonfinite_power_is_explicit_not_silently_zero_energy(self):
        with tempfile.TemporaryDirectory() as name:
            logger = session.StreamLog(Path(name)/"power", include_power=True)
            try:
                result = logger.summarize("s/p/!data", session.stamp(),
                    dict(sample_id=0, sample_rate=2000000, decimate_factor=1, utc=0,
                         data=np.array([1, np.nan, 3], dtype=np.float32)))
                self.assertEqual(result["sum"], 4)
                self.assertEqual(result["nonfinite_count"], 1)
                self.assertEqual(result["finite_count"], 2)
            finally:
                logger.close()


if __name__ == "__main__":
    unittest.main()
