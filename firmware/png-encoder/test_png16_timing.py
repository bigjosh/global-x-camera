"""Offline timing-accounting tests using the real encoder and an injected clock.

Injected sink latency distinguishes nested from disjoint counters without
pretending to measure MCU performance. Every successful output is independently
CRC-checked, inflated and compared with the existing untimed API.
"""
import ctypes as C
import tempfile
import unittest

from test_png16 import Stats, WRITE, close_library, compile_library, parse_png


NOW = C.CFUNCTYPE(C.c_uint64, C.c_void_p)
COUNTERS = (
    "total_cycles", "conversion_cycles", "deflate_cycles", "framing_cycles",
    "callback_cycles", "other_cycles", "deflate_inclusive_cycles",
    "deflate_output_cycles", "framing_inclusive_cycles", "framing_callback_cycles",
)


class Timing(C.Structure):
    _fields_ = [(name, C.c_uint64) for name in COUNTERS] + [
        ("clock_calls", C.c_uint32), ("clock_error", C.c_uint32)]


class Config(C.Structure):
    _fields_ = [("now", NOW), ("user", C.c_void_p), ("out", C.POINTER(Timing))]


class TimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="png16-timing-")
        cls.lib = compile_library(cls.temp.name)
        cls.lib.png16_encode_timed.argtypes = cls.lib.png16_encode.argtypes + [
            C.POINTER(Config)]
        cls.lib.png16_encode_timed.restype = C.c_int

    @classmethod
    def tearDownClass(cls):
        close_library(cls.lib)
        del cls.lib
        cls.temp.cleanup()

    def encode(self, mode, *, width=1120, height=64, delay=0, fail_after=None,
               bad_sample=False, timed=True, regression=False):
        values = [(i*127+(i//width)*43) % 1024 for i in range(width*height)]
        if bad_sample:
            values[-1] = 4096
        source = (C.c_uint16*len(values))(*values)
        original = bytes(source)
        needed = self.lib.png16_workspace_size()
        workspace = (C.c_uint64*((needed+7)//8))()
        C.memset(workspace, 0xA5, C.sizeof(workspace))
        timing, stats = Timing(), Stats()
        state = dict(tick=0, reads=0, calls=0)
        pieces = []

        @NOW
        def now(user):
            self.assertEqual(user, 0x5943)
            state["reads"] += 1
            state["tick"] += 1
            if regression and state["reads"] == 5:
                return 0
            return state["tick"]

        @WRITE
        def sink(user, data, count):
            state["calls"] += 1
            state["tick"] += delay
            if fail_after is not None and state["calls"] > fail_after:
                return 0
            pieces.append(C.string_at(data, count))
            return 1

        args = [source, C.sizeof(source), width, height, width*2, mode,
                workspace, needed, sink, None, C.byref(stats)]
        config = Config(now, 0x5943, C.pointer(timing))
        if timed is True:
            result = self.lib.png16_encode_timed(*args, C.byref(config))
        elif timed is None:
            result = self.lib.png16_encode_timed(*args, None)
        else:
            result = self.lib.png16_encode(*args)
        self.assertEqual(bytes(source), original)
        self.assertEqual(stats.callback_calls, state["calls"])
        if timed is True:
            self.assertEqual(timing.clock_calls, state["reads"])
        else:
            self.assertEqual(state["reads"], 0)
        return result, b"".join(pieces), stats, timing, values

    def partition(self, timing):
        self.assertEqual(timing.clock_error, 0)
        self.assertEqual(timing.total_cycles,
                         sum(getattr(timing, key) for key in COUNTERS[1:6]))
        self.assertEqual(timing.deflate_cycles,
                         timing.deflate_inclusive_cycles-timing.deflate_output_cycles)
        self.assertEqual(timing.framing_cycles,
                         timing.framing_inclusive_cycles-timing.framing_callback_cycles)

    def test_all_modes_keep_bytes_and_pixels_and_default_api(self):
        for mode in range(4):
            with self.subTest(mode=mode):
                old = self.encode(mode, timed=False)
                disabled = self.encode(mode, timed=None)
                timed = self.encode(mode)
                self.assertEqual(old[:2], disabled[:2])
                self.assertEqual(old[:2], timed[:2])
                self.assertEqual(timed[0], 0)
                self.assertEqual(parse_png(timed[1])[2], [v << 6 for v in timed[4]])
                self.partition(timed[3])

    def test_sink_delay_is_counted_once_and_excluded_from_cpu_categories(self):
        for mode in range(4):
            with self.subTest(mode=mode):
                baseline = self.encode(mode)
                delayed = self.encode(mode, delay=997)
                self.assertEqual(baseline[:2], delayed[:2])
                a, b = baseline[3], delayed[3]
                self.partition(a)
                self.partition(b)
                injected = 997*delayed[2].callback_calls
                self.assertEqual(b.total_cycles-a.total_cycles, injected)
                self.assertEqual(b.callback_cycles-a.callback_cycles, injected)
                self.assertEqual(b.callback_cycles, 998*delayed[2].callback_calls)
                for key in ("conversion_cycles", "deflate_cycles", "framing_cycles",
                            "other_cycles", "clock_calls"):
                    self.assertEqual(getattr(a, key), getattr(b, key), key)
                # PNG signature is a callback outside any PNG chunk, so it
                # must not accidentally be subtracted from chunk-only time.
                self.assertEqual(b.callback_cycles-b.framing_callback_cycles, 998)
                if mode:
                    self.assertGreater(b.deflate_output_cycles, a.deflate_output_cycles)
                else:
                    self.assertEqual(b.deflate_output_cycles, 0)

    def test_failed_callbacks_and_late_bad_samples_keep_partial_accounting(self):
        for mode in range(4):
            last = self.encode(mode)[2].callback_calls-1
            for accepted in sorted({0, 1, 4, min(8, last), last}):
                with self.subTest(mode=mode, accepted=accepted):
                    a = self.encode(mode, fail_after=accepted)
                    b = self.encode(mode, fail_after=accepted, delay=101)
                    self.assertEqual(a[0], -4)
                    self.assertEqual(a[:2], b[:2])
                    self.partition(a[3])
                    self.partition(b[3])
                    self.assertEqual(b[3].callback_cycles-a[3].callback_cycles,
                                     101*b[2].callback_calls)
                    self.assertEqual(b[3].total_cycles-a[3].total_cycles,
                                     101*b[2].callback_calls)
            result, partial, stats, timing, _ = self.encode(mode, bad_sample=True)
            self.assertEqual(result, -3)
            self.assertEqual(stats.rows_encoded, 63)
            self.assertNotIn(b"IEND", partial)
            self.partition(timing)
            self.assertGreater(timing.conversion_cycles, 0)

    def test_clock_regression_invalidates_timing_without_changing_image(self):
        good = self.encode(1)
        bad = self.encode(1, regression=True)
        self.assertEqual(good[:2], bad[:2])
        self.assertNotEqual(bad[3].clock_error & 1, 0)

    def test_timer_calls_scale_by_rows_and_chunks_not_pixels(self):
        # Stored mode emits the same number of chunks for each row regardless
        # of width, giving a direct test that no per-pixel timer was inserted.
        small = self.encode(0, width=1, height=17)
        large = self.encode(0, width=1120, height=17)
        self.assertEqual(small[3].clock_calls, large[3].clock_calls)
        self.assertLess(large[3].clock_calls, 400)

    def test_invalid_timer_configuration_and_aliases_never_call_sink_or_clock(self):
        source = (C.c_uint16*256)(*([3]*256))
        needed = self.lib.png16_workspace_size()
        workspace = (C.c_uint64*((needed+7)//8))()
        stats, timing = Stats(), Timing()
        calls = []

        @NOW
        def now(user):
            calls.append("clock")
            return 1

        @WRITE
        def sink(user, data, count):
            calls.append("sink")
            return 1

        args = [source, C.sizeof(source), 16, 16, 32, 1, workspace, needed,
                sink, None, C.byref(stats)]
        for out in (None, C.cast(source, C.POINTER(Timing)),
                    C.cast(workspace, C.POINTER(Timing)),
                    C.cast(C.byref(stats), C.POINTER(Timing))):
            config = Config(now, None, out)
            self.assertEqual(self.lib.png16_encode_timed(*args, C.byref(config)), -1)
        config = Config(NOW(), None, C.pointer(timing))
        self.assertEqual(self.lib.png16_encode_timed(*args, C.byref(config)), -1)
        config = Config(now, None, C.pointer(timing))
        config.out = C.cast(C.byref(config), C.POINTER(Timing))
        self.assertEqual(self.lib.png16_encode_timed(*args, C.byref(config)), -1)
        for address in (C.addressof(source), C.addressof(workspace), C.addressof(stats)):
            alias = C.cast(address, C.POINTER(Config))
            self.assertEqual(self.lib.png16_encode_timed(*args, alias), -1)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
