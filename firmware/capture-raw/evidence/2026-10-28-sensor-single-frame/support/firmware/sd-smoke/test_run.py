"""Guarded runner must not mistake cleared/stale/running evidence for a park."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("sd_smoke_run", HERE / "run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class TerminalTests(unittest.TestCase):
    def raw(self, **changes):
        status = {key: 0 for key in runner.FIELDS}
        status.update(magic=0x53445231, schema=1, words=78, request_max_hz=100000,
                      stage=9, result=0)
        status.update(changes)
        return struct.pack("<78I", *(status[key] for key in runner.FIELDS))

    def test_cleared_status_is_not_completion(self):
        self.assertIsNone(runner.checked_terminal(bytes(312), 100000))

    def test_running_status_is_not_completion(self):
        self.assertIsNone(runner.checked_terminal(self.raw(result=0x52554E4E), 100000))

    def test_result_published_before_final_stage_is_not_completion(self):
        self.assertIsNone(runner.checked_terminal(self.raw(stage=8), 100000))

    def test_different_request_is_not_completion(self):
        self.assertIsNone(runner.checked_terminal(self.raw(request_max_hz=25000000), 100000))

    def test_known_failure_is_terminal_for_diagnostic_park_verification(self):
        status = runner.checked_terminal(self.raw(result=11), 100000)
        self.assertEqual(status["result"], 11)

    def test_unknown_status_is_not_halt_authority(self):
        with self.assertRaises(ValueError):
            runner.checked_terminal(self.raw(result=24), 100000)


class ExecutionGuardTests(unittest.TestCase):
    """Inject failures at actual execution gates using an inert RAM transport."""

    def exercise(self, failure):
        calls, uploads, guard_calls = [], [], []
        binary = b"\x01\x02\x03\x04"

        class FakeBench:
            def __init__(self, output):
                self.output = output
                self.output.mkdir(parents=True, exist_ok=False)
                self.memory = {}

            def call(self, *args, **kwargs):
                calls.append(args)
                # Emulate only RAM downloads. No target, serial or instrument
                # backend is created, even if the runner regresses past a gate.
                for index, argument in enumerate(args):
                    if argument == "-w":
                        self.memory[int(args[index + 2], 0)] = Path(
                            args[index + 1]).read_bytes()
                return "Download verified successfully"

            def upload(self, address, length, name):
                uploads.append(address)
                data = self.memory[address]
                if len(data) != length:
                    raise AssertionError("Unexpected fake RAM read length")
                if ((failure == "helper" and address == runner.LOAD) or
                        (failure == "uncleared" and address == runner.STATUS)):
                    return bytes([data[0] ^ 1]) + data[1:]
                return data

        def fake_guard(arguments, **kwargs):
            guard_calls.append(arguments)
            self.assertEqual(Path(arguments[1]).name, "check_park.py")
            self.assertEqual(kwargs["timeout"], 180)
            if failure == "guard":
                return SimpleNamespace(returncode=1, stdout=b"guard refused", stderr=b"")
            folder = Path(arguments[arguments.index("--out") + 1])
            folder.mkdir()
            (folder / "result.json").write_text(json.dumps({"passed": True, "ccr": 0}))
            return SimpleNamespace(returncode=0, stdout=b"guard passed", stderr=b"")

        # execute() deliberately permits evidence only below this ignored
        # directory. Keep that real path guard active during the tests.
        (runner.REPO / "tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="sd-run-guards-", dir=runner.REPO / "tmp") as tmp:
            root = Path(tmp)
            build = root / "build"
            build.mkdir()
            (build / "sd-smoke.bin").write_bytes(binary)
            args = SimpleNamespace(
                out=root / "run", build=build,
                recovery_build=root / "recovery", max_hz=100000)
            messages = {
                "guard": "Fresh early-recovery guard failed",
                "helper": "Complete RAM helper readback differs",
                "uncleared": "Result buffer was not cleared",
            }
            with (mock.patch.object(runner, "Bench", FakeBench),
                  mock.patch.object(runner.subprocess, "run", fake_guard)):
                with self.assertRaisesRegex((RuntimeError, ValueError), messages[failure]):
                    runner.execute(args, {}, binary)

        self.assertEqual(len(guard_calls), 1)
        self.assertFalse(any("-run" in args or "-coreReg" in args for args in calls),
                         "A failed prerequisite must not reach target execution")
        return calls, uploads

    def test_failed_recovery_guard_prevents_all_ram_downloads(self):
        calls, uploads = self.exercise("guard")
        self.assertEqual(calls, [])
        self.assertEqual(uploads, [])

    def test_corrupt_helper_readback_prevents_request_and_execution(self):
        calls, uploads = self.exercise("helper")
        self.assertEqual(len(calls), 1)
        self.assertEqual(uploads, [runner.LOAD])
        self.assertIn(hex(runner.LOAD), calls[0])

    def test_uncleared_status_prevents_execution_despite_valid_helper(self):
        calls, uploads = self.exercise("uncleared")
        self.assertEqual(len(calls), 2)
        self.assertEqual(uploads, [runner.LOAD, runner.STATUS])
        self.assertIn(hex(runner.STATUS), calls[1])
        self.assertIn(hex(runner.REQUEST), calls[1])


if __name__ == "__main__":
    unittest.main()
