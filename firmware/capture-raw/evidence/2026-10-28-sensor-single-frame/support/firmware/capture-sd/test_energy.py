"""Independent numerical/negative checks; no instruments or hardware imports."""
from copy import deepcopy
from datetime import datetime, timezone
import itertools
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import energy


def chunk(values, start=0, rate=10):
    return dict(event="stream_chunk", signal="power", units="W", sample_id=start,
        sample_id_end_exclusive=start+len(values), sample_rate_hz=rate,
        decimate_factor=1, count=len(values), finite_count=len(values),
        nonfinite_count=0, min=min(values), max=max(values),
        sum=sum(values), mean=sum(values)/len(values), duration_s=len(values)/rate,
        gap_native_samples=None if start == 0 else 0,
        sample_utc=datetime.fromtimestamp(1700000000+start/rate, timezone.utc).isoformat(),
        time_map={"offset_counter": 0, "counter_rate": rate, "offset_time": 123})


def records(*chunks):
    return [dict(event="stream_start", schema=2), *chunks,
            dict(event="stream_stop", complete=True, error=None, dropped_chunks=0)]


class EnergyTests(unittest.TestCase):
    def test_whole_chunks_integrate_power_samples_not_mean_i_times_mean_v(self):
        # I=[1,3], V=[3,1] has mean(I)*mean(V)=4 W but mean(I*V)=3 W.
        report = energy.analyze(records(chunk([3,3], rate=2)),
                                dict(start_sample_id=0, end_sample_id=2))
        self.assertEqual(report["energy_bounds_j"], [3,3])
        self.assertFalse(report["physical_alignment_verified"])

    def test_partial_bounds_contain_every_compatible_sample_order(self):
        values = [0, 0, 1, 4, 5]
        report = energy.analyze(records(chunk(values)),
                                dict(start_sample_id=1, end_sample_id=4))
        low, high = report["energy_bounds_j"]
        # The log retains extrema and sum, not the histogram or sample order.
        possibilities = [sum(v[1:4])/10 for v in itertools.product(range(6), repeat=5)
                         if min(v)==0 and max(v)==5 and sum(v)==10]
        self.assertAlmostEqual(low, min(possibilities))
        self.assertAlmostEqual(high, max(possibilities))

    def test_boundary_uncertainty_also_handles_negative_power(self):
        values = [-2, 5, 1, -3, 4, 0, 7, -1]
        report = energy.analyze(records(chunk(values)),
            dict(start_sample_id=2, end_sample_id=6, boundary_uncertainty_samples=1))
        low, high = report["energy_bounds_j"]
        for start in range(1,4):
            for end in range(5,8):
                actual = sum(values[start:end])/10
                self.assertLessEqual(low, actual)
                self.assertGreaterEqual(high, actual)

    def test_baseline_is_separate_conditional_estimate(self):
        report = energy.analyze(records(chunk([1]*10), chunk([3]*10, start=10)),
            dict(start_sample_id=10, end_sample_id=20,
                 baseline=dict(start_sample_id=0, end_sample_id=10)))
        self.assertEqual(report["energy_bounds_j"], [3,3])
        self.assertEqual(report["baseline_subtracted_conditional_bounds_j"], [2,2])
        self.assertIn("applicable", report["baseline_assumption"])

    def test_reject_missing_nonfinite_duplicate_reset_and_rate_change(self):
        base = records(chunk([1]*10), chunk([2]*10, start=10))
        for field, value in [("sample_id", 11), ("sample_id", 9),
                             ("sample_id", 0), ("nonfinite_count", 1),
                             ("finite_count", 9), ("sum", float("nan")),
                             ("sum", 200), ("sample_rate_hz", 20),
                             ("gap_native_samples", 1), ("duration_s", 0.5)]:
            bad = deepcopy(base)
            bad[2][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(energy.EvidenceError):
                energy.analyze(bad, dict(start_sample_id=0, end_sample_id=20))

    def test_no_extrapolation_or_legacy_mean_energy(self):
        base = records(chunk([1]*10))
        for spec in [dict(start_sample_id=-1, end_sample_id=5),
                     dict(start_sample_id=0, end_sample_id=11),
                     dict(start_sample_id=1, end_sample_id=9, boundary_uncertainty_samples=2),
                     dict(start_sample_id=2, end_sample_id=8, target_duration_s=3)]:
            with self.subTest(spec=spec), self.assertRaises(energy.EvidenceError):
                energy.analyze(base, spec)
        base[0]["schema"] = 1
        with self.assertRaises(energy.EvidenceError):
            energy.analyze(base, dict(start_sample_id=0, end_sample_id=10))

    def test_dropped_or_incomplete_logging_refuses_energy(self):
        for key, value in [("complete", False), ("dropped_chunks", 1), ("error", "disk full")]:
            base = records(chunk([1]*10))
            base[-1][key] = value
            with self.subTest(key=key), self.assertRaises(energy.EvidenceError):
                energy.analyze(base, dict(start_sample_id=0, end_sample_id=10))
        # A live log can establish coverage inside its received intervals only.
        live = records(chunk([1]*10))[:-1]
        self.assertFalse(energy.analyze(live, dict(start_sample_id=0, end_sample_id=10))
                         ["recording_finalized"])

    def test_utc_requires_explicit_uncertainty_and_checks_map_drift(self):
        base = records(chunk([1]*10), chunk([2]*10, start=10))
        spec = dict(start_utc="2023-11-14T22:13:20.3+00:00",
                    end_utc="2023-11-14T22:13:21.7+00:00")
        with self.assertRaises(energy.EvidenceError):
            energy.analyze(base, spec)
        spec["boundary_uncertainty_s"] = 0.1
        report = energy.analyze(base, spec)
        self.assertIn("assumption", report["boundary_source"])
        base[2]["sample_utc"] = "2023-11-14T22:13:22+00:00"
        with self.assertRaises(energy.EvidenceError):
            energy.analyze(base, spec)

    def test_uncertain_baseline_cannot_overlap_operation(self):
        with self.assertRaises(energy.EvidenceError):
            energy.analyze(records(chunk([1]*30)),
                dict(start_sample_id=10, end_sample_id=20, boundary_uncertainty_samples=1,
                     baseline=dict(start_sample_id=1, end_sample_id=10)))

    def test_wrong_uncertainty_units_are_rejected_not_silently_ignored(self):
        base = records(chunk([1]*30))
        for spec in [
            dict(start_sample_id=10, end_sample_id=20, boundary_uncertainty_s=0.1),
            dict(start_utc="2023-11-14T22:13:20.3+00:00",
                 end_utc="2023-11-14T22:13:21.7+00:00",
                 boundary_uncertainty_s=0.1, boundary_uncertainty_samples=1),
        ]:
            with self.subTest(spec=spec), self.assertRaises(energy.EvidenceError):
                energy.analyze(base, spec)


if __name__ == "__main__":
    unittest.main()
