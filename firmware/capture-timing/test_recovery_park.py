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


if __name__ == '__main__':
    unittest.main()
