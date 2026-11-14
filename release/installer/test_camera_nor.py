"""Offline protocol/failure tests; never constructs a real hardware transport."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

import camera_nor as nor


class FakeTransport:
    def __init__(self):
        self.calls = []
        self.events = []
        self.memory = {}
        self.flash = {0: bytes([3]) * 65536, 65536: bytes([4]) * 65536,
                      131072: bytes([5]) * 4096}
        self.status = b""
        self.commands = []
        self.status_filter = None
        self.upload_error = None
        self.readback_filter = None
        self.last_command = None
        self.writes = 0
        self.polls = 0

    def log(self, event, **fields):
        self.events.append((event, fields))

    def call(self, *args, **kwargs):
        self.calls.append(tuple(map(str, args)))
        i = 0
        while i < len(args):
            if args[i] == "-w":
                self.memory[int(args[i + 2], 0)] = Path(args[i + 1]).read_bytes()
                i += 3
            else:
                i += 1
        if "-run" in args:
            self._run()
        return "Download verified successfully\nCore run\n"

    def _run(self):
        cmd = struct.unpack("<" + "I" * (len(self.memory[nor.COMMAND]) // 4),
                            self.memory[nor.COMMAND])
        self.commands.append(cmd)
        self.last_command = cmd
        self.polls = 0
        if cmd[2] == 1:
            values = dict.fromkeys(nor.READ_FIELDS, 0)
            values.update(magic=nor.DONE, sequence=cmd[1], command=1,
                          requested_bytes=cmd[3], read_count=cmd[3],
                          flash_offset=cmd[4], last_sr=2)
            self.memory[nor.OUTPUT] = self.flash[cmd[4]]
            fields = nor.READ_FIELDS
        else:
            offset = 0 if self.memory[nor.WRITE_LOAD][0] == 2 else 65536
            values = dict.fromkeys(nor.WRITE_FIELDS, 0)
            values.update(magic=nor.DONE, sequence=cmd[1], command=cmd[2], flags=39,
                          expected_current_crc=cmd[6], expected_input_crc=cmd[7],
                          jedec_id=0xC2803A)
            if cmd[2] == 3:
                image = self.memory[nor.INPUT]
                values.update(current_crc=zlib.crc32(self.flash[offset]),
                              input_crc=zlib.crc32(image))
                if values["current_crc"] != cmd[6]:
                    values["result"] = 18
                else:
                    self.flash[offset] = image
                    self.writes += 1
                    values.update(final_crc=zlib.crc32(image), changed_mask=65535,
                                  erased_mask=65535, completed_mask=65535, flags=47)
                self.memory[nor.OUTPUT] = self.flash[offset]
            fields = nor.WRITE_FIELDS
        self.values = values
        self.fields = fields

    def upload(self, address, length, label):
        if self.upload_error:
            raise self.upload_error
        if address == nor.STATUS:
            self.polls += 1
            values = dict(self.values)
            if self.status_filter:
                self.status_filter(values, self.last_command, self.polls)
            return struct.pack("<" + "I" * len(self.fields),
                               *(values[k] for k in self.fields))
        data = self.memory[address][:length]
        return self.readback_filter(data) if self.readback_filter else data


class NorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.helpers = self.root / "helpers"
        hashes = {}
        for index, name in enumerate(("reader", "writer0", "writer1"), 1):
            folder = self.helpers / name
            folder.mkdir(parents=True)
            data = bytes([index]) * nor.HELPER_SIZES[name]
            filename = "read.bin" if name == "reader" else "programmer.bin"
            (folder / filename).write_bytes(data)
            hashes[name] = hashlib.sha256(data).hexdigest()
            load = nor.READ_LOAD if name == "reader" else nor.WRITE_LOAD
            manifest = dict(binary_sha256=hashes[name], binary_bytes=len(data),
                            load=f"0x{load:X}", thumb_entry=f"0x{load | 1:X}",
                            command_address=f"0x{nor.COMMAND:X}",
                            status=f"0x{nor.STATUS:X}", revision=2,
                            status_fields_in_word_order=nor.READ_FIELDS if name == "reader"
                            else nor.WRITE_FIELDS)
            if name == "writer1":
                manifest.update(fixed_flash_base=65536, physical_write_window=[65536, 131072])
            (folder / "manifest.json").write_text(json.dumps(manifest))
        self.pin_patch = patch.dict(nor.HELPER_HASHES, hashes)
        self.pin_patch.start()
        self.addCleanup(self.pin_patch.stop)
        self.transport = FakeTransport()
        self.client = nor.Nor(self.transport, self.helpers, work_dir=self.root / "logs",
                              timeout=0, poll_interval=0)

    def assert_locked_without_more_calls(self):
        count = len(self.transport.calls)
        with self.assertRaises(nor.NorError):
            self.client.read(0)
        with self.assertRaises(nor.NorError):
            self.client.write(0, bytes(65536), bytes(65536))
        self.assertEqual(count, len(self.transport.calls))

    def assert_no_halt_after_last_run(self):
        last = max(i for i, call in enumerate(self.transport.calls) if "-run" in call)
        self.assertEqual(last, len(self.transport.calls) - 1)

    def test_reads_all_three_exact_regions(self):
        for offset in (0, 65536, 131072):
            self.assertEqual(self.client.read(offset), self.transport.flash[offset])
        self.assertEqual([cmd[3] for cmd in self.transport.commands], [65536, 65536, 4096])
        self.assertEqual(len({cmd[1] for cmd in self.transport.commands}), 3)
        self.assertEqual(self.transport.writes, 0)

    def test_secondary_then_primary_info_write_and_independent_reads(self):
        before_guard = self.client.read(131072)
        for offset in (65536, 0):
            current = self.client.read(offset)
            desired = bytes([offset // 65536 + 10]) * 65536
            status = self.client.write(offset, current, desired)
            self.assertEqual(status["final_crc"], zlib.crc32(desired))
            self.assertEqual(self.client.read(offset), desired)
        self.assertEqual(self.client.read(131072), before_guard)
        self.assertEqual([cmd[2] for cmd in self.transport.commands], [1, 1, 2, 3, 1, 1, 2, 3, 1, 1])
        self.assertEqual(self.transport.writes, 2)
        self.assertFalse(any("-rst" in call or "-hardRst" in call for call in self.transport.calls))

    def test_rejects_unpinned_binary_before_hardware_access(self):
        (self.helpers / "reader/read.bin").write_bytes(bytes(728))
        with self.assertRaisesRegex(ValueError, "pinned"):
            self.client.read(0)
        self.assertEqual(self.transport.calls, [])

    def test_public_validator_checks_all_helpers_without_transport_or_new_files(self):
        before = {p.relative_to(self.root) for p in self.root.rglob("*")}
        report = nor.validate_helpers(self.helpers)
        self.assertEqual(set(report), {"reader", "writer0", "writer1"})
        self.assertEqual(report["writer1"]["bytes"], 3332)
        self.assertEqual({p.relative_to(self.root) for p in self.root.rglob("*")}, before)
        self.assertEqual(self.transport.calls, [])

    def test_public_validator_rejects_later_helper_bad_abi_offline(self):
        path = self.helpers / "writer1/manifest.json"
        manifest = json.loads(path.read_text())
        manifest["status"] = "0x341B4200"
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "ABI"):
            nor.validate_helpers(self.helpers)
        self.assertEqual(self.transport.calls, [])

    def test_rejects_wrong_writer_window_before_hardware_access(self):
        path = self.helpers / "writer1/manifest.json"
        data = json.loads(path.read_text())
        data["physical_write_window"] = [0, 65536]
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "window"):
            self.client.write(65536, bytes(65536), bytes(65536))
        self.assertEqual(self.transport.calls, [])

    def test_bad_arguments_do_not_access_hardware(self):
        for offset in (-1, 1, 196608, True):
            with self.assertRaises(ValueError):
                self.client.read(offset)
        with self.assertRaises(ValueError):
            self.client.write(131072, bytes(65536), bytes(65536))
        with self.assertRaises(ValueError):
            self.client.write(0, bytes(1), bytes(65536))
        self.assertEqual(self.transport.calls, [])

    def test_read_stale_done_wrong_sequence_never_halts(self):
        self.transport.status_filter = lambda s, cmd, n: s.update(sequence=cmd[1] ^ 1)
        with self.assertRaisesRegex(nor.NorError, "fresh"):
            self.client.read(0)
        self.assert_no_halt_after_last_run()
        self.assert_locked_without_more_calls()

    def test_read_stale_done_wrong_offset_never_halts(self):
        self.transport.status_filter = lambda s, cmd, n: s.update(flash_offset=65536)
        with self.assertRaises(nor.NorError):
            self.client.read(0)
        self.assert_no_halt_after_last_run()

    def test_read_failed_or_busy_completion_never_halts(self):
        self.transport.status_filter = lambda s, cmd, n: s.update(last_sr=0x22)
        with self.assertRaisesRegex(nor.NorError, "not idle"):
            self.client.read(0)
        self.assert_no_halt_after_last_run()

    def test_transport_timeout_never_halts_or_retries(self):
        self.transport.upload_error = TimeoutError("simulated CLI timeout")
        with self.assertRaises(TimeoutError):
            self.client.read(0)
        self.assert_no_halt_after_last_run()
        self.assert_locked_without_more_calls()

    def test_info_failure_prevents_write_command(self):
        self.transport.status_filter = lambda s, cmd, n: s.update(flags=0)
        with self.assertRaisesRegex(nor.NorError, "safely"):
            self.client.write(0, self.transport.flash[0], bytes(65536))
        self.assertEqual([cmd[2] for cmd in self.transport.commands], [2])
        self.assert_no_halt_after_last_run()
        self.assert_locked_without_more_calls()

    def test_write_unsafe_done_never_halts(self):
        def change(s, cmd, n):
            if cmd[2] == 3:
                s["flags"] |= 16
        self.transport.status_filter = change
        with self.assertRaisesRegex(nor.NorError, "safely"):
            self.client.write(0, self.transport.flash[0], bytes(65536))
        self.assert_no_halt_after_last_run()
        self.assert_locked_without_more_calls()

    def test_write_wrong_current_crc_refuses_before_erase(self):
        with self.assertRaisesRegex(nor.NorError, "safely"):
            self.client.write(0, bytes(65536), bytes(65536))
        self.assertEqual(self.transport.writes, 0)
        self.assert_no_halt_after_last_run()

    def test_write_wrong_done_expected_crc_is_not_this_request(self):
        def change(s, cmd, n):
            if cmd[2] == 3:
                s["expected_input_crc"] ^= 1
        self.transport.status_filter = change
        with self.assertRaisesRegex(nor.NorError, "fresh"):
            self.client.write(0, self.transport.flash[0], bytes(65536))
        self.assert_no_halt_after_last_run()

    def test_write_wrong_final_crc_rejected_before_halt(self):
        def change(s, cmd, n):
            if cmd[2] == 3:
                s["final_crc"] ^= 1
        self.transport.status_filter = change
        with self.assertRaisesRegex(nor.NorError, "CRCs"):
            self.client.write(0, self.transport.flash[0], bytes(65536))
        self.assert_no_halt_after_last_run()

    def test_write_incomplete_mask_rejected_before_halt(self):
        def change(s, cmd, n):
            if cmd[2] == 3:
                s["completed_mask"] ^= 1
        self.transport.status_filter = change
        with self.assertRaisesRegex(nor.NorError, "masks"):
            self.client.write(0, self.transport.flash[0], bytes(65536))
        self.assert_no_halt_after_last_run()

    def test_full_readback_mismatch_locks_session(self):
        self.transport.readback_filter = lambda data: bytes([data[0] ^ 1]) + data[1:]
        with self.assertRaisesRegex(nor.NorError, "readback differs"):
            self.client.write(0, self.transport.flash[0], bytes(65536))
        self.assert_locked_without_more_calls()

    def test_stale_status_can_be_followed_by_fresh_completion(self):
        self.client.timeout = 1
        def change(s, cmd, n):
            if n == 1:
                s["sequence"] ^= 1
        self.transport.status_filter = change
        self.assertEqual(self.client.read(0), self.transport.flash[0])
        self.assertEqual(self.transport.polls, 2)
        progress = [fields for event, fields in self.transport.events if event == "nor_progress"]
        self.assertEqual(len(progress), 1)  # Stale records cannot drive progress.


class BundledHelperTests(unittest.TestCase):
    def test_actual_frozen_helpers_match_pinned_layout_and_hashes(self):
        helpers = Path(__file__).resolve().parent / "assets/helpers"
        with tempfile.TemporaryDirectory() as directory:
            transport = FakeTransport()
            client = nor.Nor(transport, helpers, work_dir=Path(directory) / "logs")
            for name in ("reader", "writer0", "writer1"):
                self.assertEqual(nor.sha(client._helper(name)), nor.HELPER_HASHES[name])
            self.assertEqual(transport.calls, [])

    def test_public_validator_accepts_all_real_frozen_helpers(self):
        helpers = Path(__file__).resolve().parent / "assets/helpers"
        report = nor.validate_helpers(helpers)
        self.assertEqual({name: value["sha256"] for name, value in report.items()}, nor.HELPER_HASHES)


if __name__ == "__main__":
    unittest.main()
