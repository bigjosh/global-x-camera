"""Native-compiled tests of the exact pulse detector used by the ARM prefix."""
import bisect
import csv
import ctypes as C
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('vcp_build', HERE/'build.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
FIELDS = ('last_level saw_high low_started falling rising train max_train '
          'good_pulses bad_pulses edges last_low last_high request request_cycle '
          'first_cycle').split()

# Compact edge fixture from the successful warm C0 request:
# tmp/bringup/vcp-install-20261019/recovery-request-c0-02/digital.csv, Channel 6.
# Whole source SHA-256:
# 7deb61e368c5ae28901c1c26d68e7c5625bf396f9e2bcfedd4c41804706f7336
# Origin = 0.780005720 seconds. Values are round(Saleae seconds * 400 MHz)
# minus the origin. They are nominal-cycle waveform coordinates, NOT observed
# MCU sample times or alignment with the actual boot guard. Embedding this small
# excerpt makes replay independent of ignored files and preserves edge jitter.
C0_MEASURED_EDGES = (
    (0, 1), (400, 0), (3216, 1), (4432, 0),
    (7184, 1), (8400, 0), (11216, 1), (12432, 0),
    (15184, 1), (16400, 0), (19216, 1), (20432, 0),
    (23184, 1), (24400, 0), (27216, 1), (28432, 0),
    (31184, 1), (32400, 0), (35216, 1), (36432, 0),
    (39184, 1), (40400, 0), (43216, 1), (44432, 0),
    (47184, 1),
)


class Detector(C.Structure):
    _fields_ = [(name, C.c_uint32) for name in FIELDS]


class VcpDetectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('clang') or shutil.which('gcc')
        if not compiler:
            raise RuntimeError('Native compiler required to test actual C detector')
        cls.temp = tempfile.TemporaryDirectory(prefix='vcp-detector-')
        lib = Path(cls.temp.name)/'vcp-test.dll'
        subprocess.run([compiler, '-shared', '-O2', '-Wall', '-Wextra', '-Werror',
                        str(HERE/'test_bridge.c'), '-o', str(lib)], check=True)
        cls.lib = C.CDLL(str(lib))
        cls.lib.vcp_test_run.argtypes = [C.POINTER(C.c_uint32), C.POINTER(C.c_uint32),
                                        C.c_uint32, C.c_uint32, C.POINTER(Detector)]
        cls.lib.vcp_test_run.restype = None

    @classmethod
    def tearDownClass(cls):
        # Free native DLL before Windows removes its directory.
        if hasattr(C, 'windll'):
            handle = cls.lib._handle
            del cls.lib
            C.windll.kernel32.FreeLibrary(C.c_void_p(handle))
        cls.temp.cleanup()

    def run_samples(self, samples, start=0):
        times, levels = zip(*samples)
        result = Detector()
        self.lib.vcp_test_run((C.c_uint32*len(times))(*times),
                             (C.c_uint32*len(times))(*levels),
                             len(times), start, C.byref(result))
        return result

    @staticmethod
    def train(count=4, first=400, low=3600, high=400):
        samples = [(0, 1)]
        for i in range(count):
            fall = first+i*(low+high)
            samples.extend(((fall, 0), (fall+low, 1)))
        return samples

    @staticmethod
    def c0_sample_times(steps=(256, 257, 256, 257, 256), first=860):
        """Modeled polling only; observed mean 0.641 us is not a max-gap bound.

        The first-sample offset models the successful guard's diagnostic setup
        consuming ~2.15 us of the original 100 us deadline. Sampling does not
        restart or extend that deadline.
        """
        times = []
        now, index = first, 0
        while now < 40000:
            times.append(now)
            now += steps[index % len(steps)]
            index += 1
        return times

    def test_c0_requires_three_complete_pulses(self):
        # 1 Mbaud 8N1 C0 = start + six zero data bits LOW, then two one
        # data bits + stop HIGH: nominal 7 us LOW / 3 us HIGH.
        for count in (1, 2):
            self.assertFalse(self.run_samples(
                self.train(count, low=2800, high=1200)).request)
        result = self.run_samples(self.train(3, low=2800, high=1200))
        self.assertEqual((result.request, result.max_train, result.good_pulses), (1, 3, 3))
        self.assertEqual(result.request_cycle, 11200)

    def test_c0_all_cycle_phases_at_modeled_average_cadence(self):
        times = self.c0_sample_times()
        # These integer intervals average exactly 256.4 cycles = 0.641 us.
        # This deterministic cadence models the measured mean; it does not
        # claim that the target's individual intervals have this distribution.
        for phase in range(4000):
            samples = [(t, int((t+phase) % 4000 >= 2800)) for t in times]
            result = self.run_samples(samples)
            self.assertTrue(result.request, f'C0 phase={phase}')
            self.assertLess(result.request_cycle, 40000)

    def test_c0_phase_and_bounded_poll_jitter_models(self):
        # Explicit synthetic maximum intervals of 0.8, 0.88 and 0.96 us.
        # None is asserted to bound the hardware; these explore timing margin.
        for steps in ((192, 320), (160, 352, 256), (128, 384)):
            for rotation in range(len(steps)):
                shifted = steps[rotation:]+steps[:rotation]
                times = self.c0_sample_times(shifted)
                for phase in range(0, 4000, 40):
                    samples = [(t, int((t+phase) % 4000 >= 2800)) for t in times]
                    self.assertTrue(self.run_samples(samples).request,
                                    f'C0 steps={shifted}, phase={phase}')

    def test_c0_fast_average_alone_does_not_guarantee_detection(self):
        # Synthetic adversarial cadence: average 0.625 us, faster than the
        # observed 0.641 us mean, but each 3.1 us gap misses the entire HIGH.
        # This demonstrates why the observed mean is not a sampling guarantee.
        steps = (184,)*15+(1240,)
        self.assertEqual(sum(steps)/len(steps), 250)
        times = self.c0_sample_times(steps, first=0)
        samples = [(t, int(t % 4000 >= 2800)) for t in times]
        self.assertTrue(all(level == 0 for _, level in samples))
        self.assertFalse(self.run_samples(samples).request)

    def test_c0_jittered_sampling_rejects_static_and_partial_input(self):
        times = self.c0_sample_times((128, 384))
        for level in (0, 1):
            self.assertFalse(self.run_samples([(t, level) for t in times]).request)
        samples = self.train(3, low=2800, high=1200)
        # Begin inside the first LOW; only two later complete pulses exist.
        samples = [(0, 0)]+samples[2:]
        result = self.run_samples(samples)
        self.assertFalse(result.request)
        self.assertEqual(result.good_pulses, 2)

    def test_c0_deadline_boundary_and_counter_wrap(self):
        # The third rising edge at exactly the deadline must not count.
        self.assertFalse(self.run_samples(
            self.train(3, first=29200, low=2800, high=1200)).request)
        result = self.run_samples(
            self.train(3, first=29199, low=2800, high=1200))
        self.assertEqual((result.request, result.request_cycle), (1, 39999))
        base = 0xFFFFF000
        samples = [((base+t) & 0xFFFFFFFF, int((t+717) % 4000 >= 2800))
                   for t in self.c0_sample_times()]
        self.assertTrue(self.run_samples(samples, start=base).request)

    def test_measured_c0_excerpt_replay_with_modeled_sampling(self):
        edge_times, edge_levels = zip(*C0_MEASURED_EDGES)
        times = self.c0_sample_times()
        selected = 0
        for phase in range(0, 4000, 40):
            self.assertLess(times[-1]+phase, edge_times[-1])
            samples = [
                (t, edge_levels[bisect.bisect_right(edge_times, t+phase)-1])
                for t in times
            ]
            selected += bool(self.run_samples(samples).request)
        self.assertEqual(selected, 100)
        print('Measured C0 excerpt: 100/100 phase-grid windows selected at a '
              'modeled 0.641us mean cadence; not a hardware reliability bound')

    def test_static_high_low_and_single_edges_never_select(self):
        for samples in ([(0, 0), (39999, 0)], [(0, 1), (39999, 1)],
                        [(0, 0), (9000, 1)], [(0, 1), (100, 0)]):
            self.assertFalse(self.run_samples(samples).request)

    def test_three_complete_zero_bytes_required(self):
        self.assertFalse(self.run_samples(self.train(1)).request)
        self.assertFalse(self.run_samples(self.train(2)).request)
        result = self.run_samples(self.train(3))
        self.assertEqual((result.request, result.max_train, result.good_pulses), (1, 3, 3))
        self.assertEqual(result.request_cycle, 12000)

    def test_partial_first_low_does_not_count(self):
        samples = self.train(3)
        samples[0] = (0, 0)
        samples = [samples[0]]+samples[2:]
        result = self.run_samples(samples)
        self.assertFalse(result.request)
        self.assertEqual(result.good_pulses, 2)

    def test_glitches_wrong_baud_and_out_of_range_widths_rejected(self):
        for width in (1, 40, 2399, 5201, 31250):
            self.assertFalse(self.run_samples(self.train(8, low=width)).request)

    def test_high_gap_limits_break_consecutive_train(self):
        for high in (40, 99, 1601, 41856):
            self.assertFalse(self.run_samples(self.train(4, high=high)).request)

    def test_all_clock_phases_sampled_at_0_4us(self):
        for phase in range(0, 4000, 40):
            samples = [(t, int((t+phase) % 4000 >= 3600))
                       for t in range(0, 40000, 160)]
            self.assertTrue(self.run_samples(samples).request, f'phase={phase}')

    def test_late_window_is_not_extended_and_wrap_is_safe(self):
        self.assertFalse(self.run_samples(self.train(3, first=30000)).request)
        base = 0xFFFFF000
        samples = [((base+t) & 0xFFFFFFFF, level) for t, level in self.train(3)]
        self.assertTrue(self.run_samples(samples, start=base).request)

    def test_measured_1mbaud_trace_replay_and_gap_misses(self):
        source = HERE.parent/'evidence/2026-10-19-vcp-recovery/uart-zero1m/digital.csv'
        with source.open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        times = [round(float(r['Time [s]'])*400000000) for r in rows]
        levels = [int(r['Channel 6']) for r in rows]
        lo, hi = times[1], times[-2]
        outcomes = []
        for i in range(1001):
            begin = lo+(hi-lo-40000)*i//1000
            samples = [(delta, levels[bisect.bisect_right(times, begin+delta)-1])
                       for delta in range(0, 40000, 160)]
            outcomes.append(bool(self.run_samples(samples).request))
        # Replaying measured edges cannot establish the MCU sampling rate or
        # hardware reliability; it checks the code against the actual waveform.
        self.assertGreater(sum(outcomes), 950)
        gaps = [(times[i]-times[i-1], times[i-1]) for i in range(1, len(times))
                if levels[i-1] == 1 and i > 1 and i < len(times)-1]
        width, begin = max(gaps)
        self.assertGreater(width, 40000)
        samples = [(delta, levels[bisect.bisect_right(times, begin+delta)-1])
                   for delta in range(0, 40000, 160)]
        self.assertFalse(self.run_samples(samples).request)
        print(f'Measured 1Mbaud replay: {sum(outcomes)}/{len(outcomes)} windows selected; '
              f'longest {width/400:.2f}us HIGH gap correctly missed')


class BuildBoundaryTests(unittest.TestCase):
    def test_prefix_composition_preserves_every_later_byte(self):
        source = bytes(range(256))*256
        boot = b'\x55'*6176
        result = builder.compose_sector(source, boot)
        self.assertEqual(result[:len(boot)], boot)
        self.assertEqual(result[len(boot):], source[len(boot):])

    def test_oversize_and_truncated_inputs_fail_closed(self):
        for source, boot in ((bytes(65535), bytes(100)), (bytes(65536), bytes(8193))):
            with self.assertRaises(ValueError):
                builder.compose_sector(source, boot)


if __name__ == '__main__':
    unittest.main()
