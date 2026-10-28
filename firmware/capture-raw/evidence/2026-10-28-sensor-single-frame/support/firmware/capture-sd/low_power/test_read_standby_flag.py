"""Offline guarded SBF-reader tests. No real process or instrument is used."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import read_standby_flag as reader

CODE = bytes.fromhex("fee700bf")
APPROVED = dict(park=0x34180400, vcp=True)


def park():
    status = dict(zip(reader.check_park.FIELDS, [
        0x52475031, 1, 24, 3, 1, 0x40001, 400000000, 40000,
        6, 40082, 40076, 153, 66, 0xffffcff1, 0x1004,
        270424, 17825792, 0x80000001, 0, 0, 1, 0xb451b400, 0xb4, 2]))
    vcp = dict(zip(reader.check_park.VCP_FIELDS, [
        0x56504331, 1, 32, 0x40006, 400000000, 40000, 1000000,
        2400, 5200, 100, 1600, 3, 866, 40082, 19, 9, 0, 9,
        2952, 1136, 1, 12658, 1, 1, 2, 153, 0, 0, 0, 0, 0, 0]))
    return dict(passed=True, status=status, vcp_status=vcp,
                context=dict(PC=APPROVED["park"], CONTROL=0, PRIMASK=1,
                             FAULTMASK=0, XPSR=0x01000000),
                ccr=513, fpccr=0xc0000004, prefix_sha256=reader.sha(CODE),
                xspi_sr=2, park_context_observed_in_halt_command=True,
                ram_writes=False, nor_commands=False)


class FakeBench:
    def __init__(self, *, enabled=False, reset=False, cpucr=reader.SBF):
        self.events = []
        self.evidence = park()
        self.code = CODE
        self.context = self.evidence["context"].copy()
        self.ccr = 513
        self.fpccr = 0xc0000004
        self.enabled = reader.PWR_BIT if enabled else 0
        self.reset = reader.PWR_BIT if reset else 0
        self.cpucr = cpucr
        self.ignore_write = False
        self.reset_after_write = False
        self.fail_write = False
        self.mutate_after_read = False

    def upload(self, address, size, name):
        self.events.append(("read", address, size, name))
        if address == reader.check_park.STATUS_ADDRESS:
            result = self.evidence["status"].copy()
            if self.mutate_after_read and name.startswith("after"):
                result["polls"] -= 1
            return struct.pack("<24I", *(result[k] for k in reader.check_park.FIELDS))
        if address == reader.check_park.VCP_ADDRESS:
            return struct.pack("<32I", *(self.evidence["vcp_status"][k]
                                        for k in reader.check_park.VCP_FIELDS))
        if address == reader.check_park.PREFIX_ADDRESS:
            return self.code
        value = {
            reader.RCC_AHB4RSTR: self.reset,
            reader.RCC_AHB4ENR: self.enabled,
            reader.PWR_CPUCR: self.cpucr,
            reader.CCR: self.ccr,
            reader.FPCCR: self.fpccr,
        }[address]
        return struct.pack("<I", value)

    def call(self, *args):
        self.events.append(("call", args))
        if args == ("-halt", "-coreReg"):
            return "\n".join(f"{k} = 0x{v:08x}" for k, v in self.context.items())
        if args == ("-w32", hex(reader.RCC_AHB4ENSR), hex(reader.PWR_BIT)):
            if self.fail_write:
                raise RuntimeError("Uncertain write response")
            if not self.ignore_write:
                self.enabled |= reader.PWR_BIT
            if self.reset_after_write:
                self.reset |= reader.PWR_BIT
            return ""
        raise AssertionError("Unexpected or unsafe debugger command: " + str(args))


class FlagTests(unittest.TestCase):
    def execute(self, bench, result=None):
        result = {} if result is None else result
        return reader.read_flag(bench, CODE, APPROVED, park(), result)

    def writes(self, bench):
        return [e for e in bench.events if e[0] == "call" and "-w32" in e[1]]

    def pwr_reads(self, bench):
        return [e for e in bench.events if e[:2] == ("read", reader.PWR_CPUCR)]

    def test_valid_fixture_and_saved_proof_rejections(self):
        reader.validate_park_result(park(), CODE, APPROVED)
        for field, value in (("passed", False), ("prefix_sha256", "00"),
                             ("ram_writes", True), ("nor_commands", True),
                             ("park_context_observed_in_halt_command", False),
                             ("xspi_sr", 32)):
            with self.subTest(field=field):
                proof = park()
                proof[field] = value
                with self.assertRaises(ValueError):
                    reader.validate_park_result(proof, CODE, APPROVED)

    def test_clock_already_on_has_no_writes_and_reports_historical_flag(self):
        bench = FakeBench(enabled=True, cpucr=reader.SBF | reader.STOPF | 1)
        result = self.execute(bench)
        self.assertTrue(result["passed"])
        self.assertTrue(result["sbf"])
        self.assertTrue(result["stopf"])
        self.assertTrue(result["pdds"])
        self.assertFalse(result["trial_entry_proven"])
        self.assertIn("since the last POR", result["interpretation"])
        self.assertEqual(self.writes(bench), [])
        self.assertEqual(len(self.pwr_reads(bench)), 1)

    def test_clock_off_has_only_one_set_alias_write_and_readback_before_cpucr(self):
        bench = FakeBench()
        result = self.execute(bench)
        self.assertTrue(result["clock_enable_write_attempted"])
        self.assertTrue(result["clock_left_enabled"])
        self.assertEqual(self.writes(bench),
                         [("call", ("-w32", "0x56028a5c", "0x40000"))])
        access = [e[1] for e in bench.events if e[0] == "read"]
        cpu = access.index(reader.PWR_CPUCR)
        self.assertEqual(access[cpu-2:cpu], [reader.RCC_AHB4ENR, reader.RCC_AHB4RSTR])

    def test_pwr_held_in_reset_refuses_without_write_or_cpucr_read(self):
        bench = FakeBench(reset=True)
        with self.assertRaisesRegex(ValueError, "held in reset"):
            self.execute(bench)
        self.assertEqual(self.writes(bench), [])
        self.assertEqual(self.pwr_reads(bench), [])

    def test_failed_clock_enable_or_new_reset_prevents_cpucr_read(self):
        for changed in ("ignore_write", "reset_after_write"):
            with self.subTest(changed=changed):
                bench = FakeBench()
                setattr(bench, changed, True)
                with self.assertRaisesRegex(ValueError, "readback failed"):
                    self.execute(bench)
                self.assertEqual(len(self.writes(bench)), 1)
                self.assertEqual(self.pwr_reads(bench), [])

    def test_unknown_write_outcome_is_not_retried_or_followed_by_cpucr_read(self):
        bench = FakeBench()
        bench.fail_write = True
        result = {}
        with self.assertRaisesRegex(RuntimeError, "Uncertain"):
            self.execute(bench, result)
        self.assertTrue(result["clock_enable_write_attempted"])
        self.assertEqual(len(self.writes(bench)), 1)
        self.assertEqual(self.pwr_reads(bench), [])

    def test_changed_status_code_or_unsafe_context_blocks_rcc_and_writes(self):
        mutations = (
            lambda b: b.evidence["status"].update(polls=152),
            lambda b: b.evidence["vcp_status"].update(last_low=2951),
            lambda b: setattr(b, "code", b"changed"),
            lambda b: b.context.update(PC=0x34300000),
            lambda b: setattr(b, "ccr", b.ccr | 0x10000),
            lambda b: setattr(b, "fpccr", b.fpccr | 1))
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                bench = FakeBench()
                mutate(bench)
                with self.assertRaises(ValueError):
                    self.execute(bench)
                self.assertEqual(self.writes(bench), [])
                self.assertEqual(self.pwr_reads(bench), [])
                self.assertFalse(any(e[:2] == ("read", reader.RCC_AHB4RSTR)
                                     for e in bench.events))

    def test_sbf_zero_is_explicitly_inconclusive(self):
        result = self.execute(FakeBench(enabled=True, cpucr=0))
        self.assertFalse(result["sbf"])
        self.assertFalse(result["trial_entry_proven"])
        self.assertIn("inconclusive", result["interpretation"])
        self.assertIn("does not prove", result["interpretation"])

    def test_final_guard_change_does_not_claim_success(self):
        bench = FakeBench(enabled=True)
        bench.mutate_after_read = True
        result = {}
        with self.assertRaises(ValueError):
            self.execute(bench, result)
        self.assertNotEqual(result.get("passed"), True)
        self.assertIn("cpucr", result)  # Preserve the actual read for diagnosis.


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.build = self.root / "staged"
        self.prior = self.root / "prior.json"
        self.output = self.root / "output"
        self.prior.write_text(json.dumps(park()))

    def tearDown(self):
        self.temp.cleanup()

    def run_main(self, fresh=None, fresh_error=None, bench=None):
        argv = ["--build", str(self.build), "--park-result", str(self.prior),
                "--out", str(self.output)]
        with patch.object(reader.check_park, "checked_build",
                          return_value=(CODE, APPROVED)), \
             patch.object(reader, "fresh_park_check",
                          return_value=(fresh or park(), "f" * 64),
                          side_effect=fresh_error) as live, \
             patch.object(reader, "Bench", return_value=bench or FakeBench()) as factory, \
             redirect_stdout(io.StringIO()):
            try:
                result = reader.main(argv)
            finally:
                self.live = live
                self.factory = factory
        return result

    def test_invalid_prior_never_runs_fresh_check_or_register_client(self):
        proof = park()
        proof["passed"] = False
        self.prior.write_text(json.dumps(proof))
        with self.assertRaises(ValueError):
            self.run_main()
        self.live.assert_not_called()
        self.factory.assert_not_called()

    def test_fresh_failure_or_changed_park_never_constructs_register_client(self):
        proof = park()
        proof["status"]["polls"] = 152
        proof["vcp_status"]["polls"] = 152
        for case in ("error", "changed", "invalid"):
            with self.subTest(case=case):
                self.output = self.root / case
                bad = copy.deepcopy(proof if case == "changed" else park())
                if case == "invalid":
                    bad["passed"] = False
                with self.assertRaises((ValueError, RuntimeError)):
                    self.run_main(fresh=bad, fresh_error=RuntimeError("failed")
                                  if case == "error" else None)
                self.factory.assert_not_called()
                saved = json.loads((self.output / "result.json").read_text())
                self.assertFalse(saved["passed"])
                self.assertFalse(saved["clock_enable_write_attempted"])

    def test_success_saves_full_proof_and_provenance(self):
        result = self.run_main(bench=FakeBench(enabled=True))
        self.live.assert_called_once_with(self.build.resolve(), self.output.resolve())
        self.assertTrue(result["passed"])
        self.assertEqual(result["prior_park_result_sha256"], reader.sha(self.prior.read_bytes()))
        self.assertEqual((self.output / "prior-park-result.json").read_bytes(),
                         self.prior.read_bytes())
        saved = json.loads((self.output / "result.json").read_text())
        self.assertEqual(saved["fresh_park_result"], park())
        self.assertFalse(saved["cpucr_written"])
        self.assertFalse(saved["reset_or_power_changed"])


if __name__ == "__main__":
    unittest.main()
