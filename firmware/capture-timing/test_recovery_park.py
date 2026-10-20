"""Failure-path checks for authorization of early-park maintenance."""
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).parent/'recovery_gpio/check_park.py'
spec = importlib.util.spec_from_file_location('recovery_park_checks', MODULE)
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


class RecoveryParkTests(unittest.TestCase):
    def status(self):
        s = dict.fromkeys(checks.FIELDS, 0)
        s.update(magic=0x52475031, schema=1, words=24, state=3, reason=1,
                 pin=0x40001, nominal_hz=400000000, settle_cycles=40000,
                 begin_cycle=200, sample_cycle=40200, elapsed_cycles=40000,
                 polls=100, pupdr=4, ahb4enr=1 << 4, demcr=1 << 24, dwt_ctrl=1,
                 primask=1, dbgcr=0xB451B400, ap_unlock=0xB4)
        return [s[k] for k in checks.FIELDS]

    def test_valid_requested_park(self):
        self.assertEqual(checks.validate_status(self.status())['state'], 3)

    def test_reject_normal_timeout_or_high_input(self):
        for key, value in [('state', 2), ('reason', 2), ('idr', 2),
                           ('pupdr', 0), ('moder', 4), ('elapsed_cycles', 39999),
                           ('sample_cycle', 40201), ('primask', 0),
                           ('dwt_ctrl', 0), ('dwt_ctrl', 1 | (1 << 25)),
                           ('ahb4enr', 0), ('ap_unlock', 0)]:
            with self.subTest(key=key):
                s = self.status()
                s[checks.FIELDS.index(key)] = value
                with self.assertRaises(ValueError):
                    checks.validate_status(s)

    def test_wraparound_timer(self):
        s = self.status()
        s[checks.FIELDS.index('begin_cycle')] = 0xFFFFFF00
        s[checks.FIELDS.index('sample_cycle')] = (0xFFFFFF00+40000) & 0xFFFFFFFF
        checks.validate_status(s)

    def vcp_pair(self):
        s = self.status()
        s[checks.FIELDS.index('reserved')] = 2
        s[checks.FIELDS.index('idr')] = 0x42
        s[checks.FIELDS.index('pupdr')] = 0x1004
        guard = checks.validate_status(s, vcp=True)
        v = dict.fromkeys(checks.VCP_FIELDS, 0)
        v.update(magic=0x56504331, schema=1, words=32, pin=0x40006,
                 nominal_hz=400000000, window_cycles=40000, baud=1000000,
                 min_low=2400, max_low=5200, min_high=100, max_high=1600,
                 required=3, first_cycle=1000, last_cycle=guard['sample_cycle'],
                 edges=6, good_pulses=3, max_train=3, last_low=3600,
                 last_high=400, request=1, request_cycle=13000,
                 initial_level=1, final_level=1, source_bits=2, polls=guard['polls'])
        return s, guard, v

    def test_vcp_park_requires_correlated_pulse_evidence(self):
        _, guard, v = self.vcp_pair()
        checks.validate_vcp_status([v[k] for k in checks.VCP_FIELDS], guard)
        for key, value in [('magic', 0), ('required', 2), ('source_bits', 1),
                           ('request', 0), ('max_train', 2), ('edges', 5),
                           ('request_cycle', 40200), ('request_cycle', 999),
                           ('request_cycle', 8399),
                           ('first_cycle', 50000), ('reserved26', 1),
                           ('last_cycle', 40201), ('final_level', 0),
                           ('good_pulses', 4)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                bad = dict(v, **{key: value})
                checks.validate_vcp_status([bad[k] for k in checks.VCP_FIELDS], guard)

    def test_vcp_input_and_source_bits_must_agree(self):
        s, _, _ = self.vcp_pair()
        for key, value in [('reserved', 0), ('reserved', 1), ('reserved', 4),
                           ('moder', 0x1000), ('pupdr', 4), ('idr', 0x40)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                bad = s.copy()
                bad[checks.FIELDS.index(key)] = value
                checks.validate_status(bad, vcp=True)
        # Old allowlisted builds cannot select a VCP park by invented status.
        with self.assertRaises(ValueError):
            checks.validate_status(s)

    def test_exact_idle_context(self):
        c = dict(PC=0x3418078C, CONTROL=0, PRIMASK=1, FAULTMASK=0, XPSR=0x01000000)
        checks.validate_context(c, c['PC'], 0, 0)
        for key, value in [('PC', c['PC']+2), ('CONTROL', 1), ('PRIMASK', 0),
                           ('FAULTMASK', 1), ('XPSR', 0x01000003)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                checks.validate_context(dict(c, **{key: value}), c['PC'], 0, 0)
        for ccr, fpccr in [(0x10000, 0), (0x20000, 0), (0, 1)]:
            with self.assertRaises(ValueError):
                checks.validate_context(c, c['PC'], ccr, fpccr)

    def test_no_register_read_when_xspi_reset_or_unclocked(self):
        checks.validate_xspi_clock(0x2020, 0)
        for enabled, reset in [(0, 0), (0x20, 0), (0x2000, 0), (0x2020, 0x20), (0x2020, 0x2000)]:
            with self.assertRaises(ValueError):
                checks.validate_xspi_clock(enabled, reset)

    def test_rom_icache_state_is_rejected_until_disabled_without_relaxing_dcache(self):
        c = dict(PC=0x3418078C, CONTROL=0, PRIMASK=1, FAULTMASK=0, XPSR=0x01000000)
        # The actual v34b park retained ROM's CCR=0x20201. The revised firmware
        # clears only IC, preserving the other CCR bits and the host DC guard.
        with self.assertRaises(ValueError):
            checks.validate_context(c, c['PC'], 0x20201, 0)
        checks.validate_context(c, c['PC'], 0x201, 0)
        with self.assertRaises(ValueError):
            checks.validate_context(c, c['PC'], 0x10201, 0)


if __name__ == '__main__':
    unittest.main()
