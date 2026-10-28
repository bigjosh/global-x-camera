"""Mathematical counterexamples and independent brute-force checks; no hardware."""
import itertools
import math
import random
import unittest

import energy
import energy_sliding as sliding


def chunk(start, samples, rate=1, decimation=1):
    return energy.Chunk(
        start, start+len(samples)*decimation, rate, decimation, len(samples),
        min(samples), max(samples), sum(samples)*decimation/rate,
        1000+start/rate, {},
    )


def window(start, end, uncertainty=0):
    return {"start_sample_id": start, "end_sample_id": end,
            "boundary_uncertainty_samples": uncertainty}


def sample_energy(samples, start, end):
    return sum(value*max(0., min(end, index+1)-max(start, index))
               for index, value in enumerate(samples))


class SlidingTests(unittest.TestCase):
    def test_constant_power_discards_unknown_poll_tail(self):
        chunks = [chunk(0, [2.]*10)]
        got = sliding.fixed_duration_bounds(chunks, window(1, 9), 3.)
        self.assertAlmostEqual(got["energy_bounds_j"][0], 6.)
        self.assertAlmostEqual(got["energy_bounds_j"][1], 6.)
        self.assertEqual(got["feasible_start_sample_ids"], [1., 6.])

    def test_bound_extremum_inside_one_aggregated_chunk(self):
        # No preferred ordering: two units could be near either boundary.
        got = sliding.fixed_duration_bounds([chunk(0, [0., 0., 2., 2.])],
                                           window(0, 4), 2.)
        self.assertLessEqual(got["energy_bounds_j"][0], 0.)
        self.assertGreaterEqual(got["energy_bounds_j"][1], 4.)

    def test_negative_power_and_uncertainty_are_not_clamped(self):
        chunks = [chunk(0, [-3.]*4), chunk(4, [2.]*4), chunk(8, [-1.]*4)]
        got = sliding.fixed_duration_bounds(chunks, window(2, 10, 1), 3.)
        self.assertEqual(got["feasible_start_sample_ids"], [1., 8.])
        self.assertAlmostEqual(got["energy_bounds_j"][0], -9.)
        self.assertAlmostEqual(got["energy_bounds_j"][1], 6.)

    def test_all_small_chunk_permutations_and_fractional_starts(self):
        blocks = ([0., 1., 3.], [-2., 0., 2.], [1., 2., 4.])
        chunks = [chunk(i*3, values) for i, values in enumerate(blocks)]
        got = sliding.fixed_duration_bounds(chunks, window(0, 9), 3.5)
        low, high = got["energy_bounds_j"]
        for permuted in itertools.product(*(itertools.permutations(b) for b in blocks)):
            samples = sum((list(p) for p in permuted), [])
            for step in range(23):
                actual = sample_energy(samples, step/4, step/4+3.5)
                self.assertLessEqual(low, actual+1e-12)
                self.assertGreaterEqual(high, actual-1e-12)

    def test_piecewise_candidates_cover_dense_random_bound_search(self):
        rng = random.Random(48318)
        for _ in range(40):
            chunks = []
            start = 0
            for _ in range(5):
                samples = [rng.uniform(-2, 5) for _ in range(rng.randint(2, 7))]
                chunks.append(chunk(start, samples))
                start = chunks[-1].end
            duration = rng.uniform(.3, start-.2)
            got = sliding.fixed_duration_bounds(chunks, window(0, start), duration)
            low, high = got["energy_bounds_j"]
            for i in range(401):
                begin = (start-duration)*i/400
                a, b, _ = energy.integrate(chunks, begin, begin+duration)
                self.assertLessEqual(low, a+1e-10)
                self.assertGreaterEqual(high, b-1e-10)

    def test_decimated_units_use_native_rate(self):
        chunks = [chunk(100, [1., 3., 1., 3.], rate=4, decimation=2)]
        got = sliding.fixed_duration_bounds(chunks, window(100, 108), 1.5)
        self.assertAlmostEqual(got["energy_bounds_j"][0], 2.5)
        self.assertAlmostEqual(got["energy_bounds_j"][1], 3.5)

    def test_rejects_impossible_or_uncovered_duration_and_wrong_units(self):
        chunks = [chunk(0, [1.]*10)]
        for duration in (0., -1., math.nan, 11.):
            with self.assertRaises(energy.EvidenceError):
                sliding.fixed_duration_bounds(chunks, window(0, 10), duration)
        with self.assertRaises(energy.EvidenceError):
            sliding.fixed_duration_bounds(chunks, window(0, 10, 1), 2.)
        with self.assertRaises(energy.EvidenceError):
            sliding.fixed_duration_bounds(
                chunks, dict(window(0, 10), boundary_uncertainty_s=.1), 2.)


if __name__ == "__main__":
    unittest.main()
