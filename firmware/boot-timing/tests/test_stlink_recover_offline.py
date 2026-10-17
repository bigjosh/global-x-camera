"""Verify recovery guards and handle cleanup without loading any device API."""
from contextlib import redirect_stdout
import ctypes
import io
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stlink_recover as recover


class Function:
    def __init__(self, implementation):
        self.implementation = implementation

    def __call__(self, *args):
        return self.implementation(*args)


def fake_apis(wrong_endpoint=False):
    calls = []

    def initialize(handle, output):
        output._obj.value = 222
        return 1

    def descriptor(handle, alternate, output):
        output._obj.bInterfaceNumber = 0
        output._obj.bAlternateSetting = 0
        output._obj.bInterfaceClass = 255
        output._obj.bNumEndpoints = 3
        return 1

    def pipe(handle, alternate, index, output):
        output._obj.PipeType = 2
        output._obj.PipeId = (0x81, 0x01, 0x85 if wrong_endpoint else 0x82)[index]
        output._obj.MaximumPacketSize = 512
        return 1

    def record(name):
        def invoke(*args):
            calls.append((name, args[-1] if len(args) > 1 else None))
            return 1
        return Function(invoke)

    kernel = SimpleNamespace(CreateFileW=Function(lambda *args: 123), CloseHandle=record("close"))
    winusb = SimpleNamespace(
        WinUsb_Initialize=Function(initialize), WinUsb_QueryInterfaceSettings=Function(descriptor),
        WinUsb_QueryPipe=Function(pipe), WinUsb_AbortPipe=record("abort"),
        WinUsb_ResetPipe=record("reset"), WinUsb_Free=record("free"))
    return kernel, winusb, calls


class RecoveryGuardTests(unittest.TestCase):
    def test_default_does_not_validate_or_open_device(self):
        with patch.object(sys, "argv", ["stlink_recover.py"]), \
             patch.object(recover, "run_worker") as worker, \
             patch.object(recover.subprocess, "Popen") as process, redirect_stdout(io.StringIO()):
            self.assertEqual(recover.main(), 0)
        worker.assert_not_called()
        process.assert_not_called()

    def test_rejects_wrong_parent_driver_or_running_client(self):
        for parent, service, clients in (
            ("some-other-device", "WINUSB", []),
            (recover.PARENT, "wrong-driver", []),
            (recover.PARENT, "WINUSB", [{"Name": "STM32_Programmer_CLI.exe", "ProcessId": 123}]),
        ):
            with self.subTest(parent=parent, service=service, clients=clients):
                result = SimpleNamespace(stdout=json.dumps(dict(parent=parent, service=service, clients=clients)))
                with patch.object(recover.subprocess, "run", return_value=result), redirect_stdout(io.StringIO()):
                    with self.assertRaises(RuntimeError):
                        recover.validate_identity()

    def test_unexpected_pipe_set_closes_handles_without_mutating_pipes(self):
        kernel, winusb, calls = fake_apis(wrong_endpoint=True)
        with patch.object(recover, "validate_identity"), \
             patch.object(ctypes, "WinDLL", side_effect=[kernel, winusb], create=True), \
             redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "Unexpected endpoint set"):
                recover.run_worker()
        self.assertEqual([name for name, _ in calls], ["free", "close"])

    def test_valid_pipe_set_aborts_before_reset_and_closes(self):
        kernel, winusb, calls = fake_apis()
        with patch.object(recover, "validate_identity"), \
             patch.object(ctypes, "WinDLL", side_effect=[kernel, winusb], create=True), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(recover.run_worker(), 0)
        self.assertEqual(calls[:6], [("abort", 0x81), ("abort", 0x01), ("abort", 0x82),
                                    ("reset", 0x81), ("reset", 0x01), ("reset", 0x82)])
        self.assertEqual([name for name, _ in calls[-2:]], ["free", "close"])

    def test_worker_timeout_terminates_only_owned_process(self):
        worker = Mock(pid=123)
        worker.wait.side_effect = [subprocess.TimeoutExpired("worker", 15), 0]
        with patch.object(sys, "argv", ["stlink_recover.py", "--execute"]), \
             patch.object(recover.subprocess, "Popen", return_value=worker), redirect_stdout(io.StringIO()):
            self.assertEqual(recover.main(), 124)
        worker.kill.assert_called_once_with()
        self.assertEqual(worker.wait.call_count, 2)


if __name__ == "__main__":
    unittest.main()
