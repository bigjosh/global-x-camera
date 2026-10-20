"""Actual recorder-to-analyzer tests, with no device import or hardware access."""
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "boot-timing"))
sys.path.insert(0, str(HERE.parent / "boot-timing" / "tests"))
import js110_session
from js110_raw import make_raw_stream, MEASUREMENT_TOPICS
from test_js110_power import PowerDriver
import cycle_energy


CRITERIA = dict(bin_s=.01, off_baseline_s=.5, off_abs_max_a=.0001, onset_a=.05,
                pretrigger_s=.1, plateau_min_s=.5, plateau_mean_min_a=.001,
                plateau_mean_max_a=.01, plateau_peak_abs_max_a=.015,
                plateau_mean_span_a=.002, current_valid_abs_max_a=1.9)


def waveform():
    current = np.zeros(3200, dtype="<f4")
    current[1200] = 1
    current[1201:2100] = .2
    current[2100:] = .005
    return current


def record(root, current=None, *, max_bytes=1000000, gap=False, decimation=1):
    current = waveform() if current is None else current
    signals = dict(current=current, voltage=np.full(len(current), 5, dtype="<f4"),
                   power=(current * np.float32(5)).astype("<f4"))
    logger = make_raw_stream(js110_session.StreamLog, root, max_bytes)
    # Different boundaries across signals deliberately test native sample
    # alignment rather than pairing arrival order or driver chunk number.
    for short, name, size in (("p", "power", 1000), ("i", "current", 733), ("v", "voltage", 1259)):
        for offset in range(0, len(current), size):
            logger.receive("s/" + short + "/!data",
                dict(sample_id=offset*decimation + (1 if gap and offset else 0),
                     sample_rate=1000*decimation, decimate_factor=decimation,
                     utc=offset, time_map={}, data=signals[name][offset:offset+size]))
    return logger.close()


class RawCycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.evidence = self.root / "terminal.json"
        self.evidence.write_text('{"qualified": "fixture only"}')
        self.window = dict(name="first", start_sample_id=0, end_sample_id=3200,
                           terminal_state_qualified=True, terminal_evidence=str(self.evidence))

    def tearDown(self):
        self.temp.cleanup()

    def analyze(self, current=None, criteria=None, decimation=1):
        record(self.root / "raw", current, decimation=decimation)
        window = dict(self.window, end_sample_id=3200*decimation)
        with cycle_energy.Archive(self.root / "raw") as archive:
            return cycle_energy.analyze_cycle(archive, window, criteria or CRITERIA)

    def test_exact_startup_spike_and_sustained_plateau_without_utc(self):
        result = self.analyze()
        self.assertEqual(result["boundaries"]["current_onset_sample_id"], 1200)
        self.assertEqual(result["boundaries"]["terminal_plateau_start_sample_id"], 2100)
        self.assertAlmostEqual(result["onset_to_plateau_energy_j"], .904, places=6)
        self.assertAlmostEqual(result["plateau_confirmation_energy_j"], .0125, places=6)
        self.assertAlmostEqual(result["pretrigger_through_confirmed_plateau_energy_j"], .9165, places=6)

    def test_decimated_native_ticks_integrate_with_effective_rate(self):
        result = self.analyze(decimation=2)
        self.assertEqual(result["boundaries"]["current_onset_sample_id"], 2400)
        self.assertAlmostEqual(result["pretrigger_through_confirmed_plateau_energy_j"], .9165, places=6)

    def test_early_precharge_must_not_be_dropped(self):
        current = waveform()
        current[900:1200] = .001
        with self.assertRaisesRegex(ValueError, "precedes"):
            self.analyze(current)

    def test_quiet_midcycle_is_not_a_terminal_plateau(self):
        current = waveform()
        current[1500:1800] = .005
        current[3100:] = .2
        with self.assertRaisesRegex(ValueError, "terminal plateau"):
            self.analyze(current)

    def test_nonfinite_or_measurement_limit_is_rejected(self):
        for bad in (np.nan, np.inf, 2.0):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as name:
                current = waveform()
                current[1200] = bad
                record(Path(name)/"raw", current)
                with cycle_energy.Archive(Path(name)/"raw") as archive:
                    with self.assertRaises(ValueError):
                        cycle_energy.analyze_cycle(archive, self.window, CRITERIA)

    def test_current_onset_alone_does_not_qualify_firmware_completion(self):
        record(self.root/"raw")
        self.window["terminal_state_qualified"] = False
        with cycle_energy.Archive(self.root/"raw") as archive:
            with self.assertRaisesRegex(ValueError, "qualification"):
                cycle_energy.analyze_cycle(archive, self.window, CRITERIA)

    def test_gap_and_byte_budget_invalidate_whole_recording(self):
        for name, kwargs in (("gap", dict(gap=True)), ("budget", dict(max_bytes=100))):
            result = record(self.root/name, **kwargs)
            self.assertFalse(result["complete"] and result["coverage"]["passed"])
            with self.assertRaisesRegex(ValueError, "finalized"):
                cycle_energy.Archive(self.root/name)

    def test_corruption_and_unindexed_tail_are_rejected(self):
        record(self.root/"raw")
        path = self.root/"raw"/"power.f32"
        with path.open("ab") as output:
            output.write(b"\0\0\0\0")
        with self.assertRaisesRegex(ValueError, "length/hash"):
            cycle_energy.Archive(self.root/"raw")

    def test_two_cycles_preserve_independent_start_and_end(self):
        record(self.root/"raw", np.concatenate((waveform(), waveform())))
        second = dict(self.window, name="second", start_sample_id=3200, end_sample_id=6400)
        result = cycle_energy.analyze(self.root/"raw",
            dict(criteria=CRITERIA, cycles=[self.window, second]))
        self.assertFalse(result["uses_host_utc_alignment"])
        self.assertEqual(len(result["cycles"]), 2)
        self.assertEqual(result["cycles"][1]["boundaries"]["current_onset_sample_id"], 4400)
        self.assertAlmostEqual(result["cycles"][0]["whole_window_energy_j"],
                               result["cycles"][1]["whole_window_energy_j"])

    def test_existing_directory_is_never_overwritten(self):
        path = self.root / "raw"
        path.mkdir()
        (path/"keep").write_text("original")
        with self.assertRaises(FileExistsError):
            make_raw_stream(js110_session.StreamLog, path)
        self.assertEqual((path/"keep").read_text(), "original")

    def test_session_hook_preserves_one_owner_settings_and_records_raw(self):
        args = SimpleNamespace(device="u/js110/fake", duration=5, control=self.root/"control",
                               response=self.root/"response", log=self.root/"log",
                               stream_log=None, power_stream_log=None,
                               cycle_raw_dir=self.root/"raw", raw_max_mib=1,
                               recovery_output=False)
        driver = PowerDriver()
        for topic in MEASUREMENT_TOPICS:
            driver.initial.setdefault(topic, 0)
            driver.settings.setdefault(topic, 0)
        old = js110_session.Reporter.emit

        def emit(reporter, event, **values):
            old(reporter, event, **values)
            if event == "ready":
                driver.deliver()
                args.control.write_text(json.dumps(dict(id="stop", state="stop")))

        with patch.object(js110_session.Reporter, "emit", emit), redirect_stdout(io.StringIO()):
            result = js110_session.run_session(args, lambda: driver, "offline-fake")
        self.assertEqual(result, 0)
        self.assertEqual(driver.settings, driver.initial)
        self.assertEqual([v for v in driver.commands if v[0] == js110_session.RANGE_TOPIC],
                         [(js110_session.RANGE_TOPIC, 128)])
        with cycle_energy.Archive(args.cycle_raw_dir) as archive:
            np.testing.assert_equal(archive.get("power", 100, 104), [1, 2, 3, 4])
        manifest=json.loads((args.cycle_raw_dir/"manifest.json").read_text())
        self.assertEqual(manifest["starting_measurement_settings"]["s/i/range/select"],128)
        self.assertEqual(manifest["range_commands"], [])

    def test_raw_enable_failure_restores_all_owned_settings_without_power_cycle(self):
        args = SimpleNamespace(device="u/js110/fake", duration=5, control=self.root/"control",
                               response=self.root/"response", log=self.root/"log",
                               stream_log=None, power_stream_log=None,
                               cycle_raw_dir=self.root/"raw", raw_max_mib=1,
                               recovery_output=False)
        driver=PowerDriver({("s/p/ctrl",1):1})
        for topic in MEASUREMENT_TOPICS:
            driver.initial.setdefault(topic,0)
            driver.settings.setdefault(topic,0)
        with redirect_stdout(io.StringIO()):
            result=js110_session.run_session(args,lambda:driver,"offline-fake")
        self.assertEqual(result,1)
        self.assertEqual(driver.settings,driver.initial)
        self.assertNotIn((js110_session.RANGE_TOPIC,0),driver.commands)
        self.assertFalse(json.loads((args.cycle_raw_dir/"manifest.json").read_text())["finalized"])


if __name__ == "__main__":
    unittest.main()
