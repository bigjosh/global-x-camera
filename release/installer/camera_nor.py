"""Pinned RAM NOR maintenance for an already verified early UART recovery park.

The caller must establish the exact, privileged Thread-mode park with interrupts
masked, both caches disabled, and the ROM's idle XSPI configuration. No bridge,
external loader, reset, cache change, or SD command is used here. The three
frozen helpers have their own stack and use only the already available low SRAM.

Use one Nor instance for the complete install. Any failed/uncertain operation
locks that instance: no automatic halt, reset, replacement helper or retry is
attempted. Transport.upload MUST read without halting. Transport.call executes
the supplied CubeProgrammer arguments and raises on timeout/error. Transport.log
persists structured events. All written command/input files remain in work_dir.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import secrets
import struct
import time
import zlib


COMMAND = 0x341B4000
STATUS = 0x341B4100
INPUT = 0x341C0000
OUTPUT = 0x341D0000
DONE = 0x444F4E45
READ_LOAD = 0x341B0000
WRITE_LOAD = 0x341E0000
BLOCK_BYTES = 65536
HELPER_HASHES = {
    "reader": "d6b63e6e993a9cb872cfe482c0fd4f8954f8edc398a7dfb1db25982b9e255b5d",
    "writer0": "e69f0d0c3c49c2bad1ad5e7e8ff5907fcf3b251cb5b968629c18a9c57247f307",
    "writer1": "5dcf3be40ef56443d0f9ecf011cb1f7acf4745ec449042cf0d9fe262be74949e",
}
HELPER_SIZES = {"reader": 728, "writer0": 3320, "writer1": 3332}
READ_FIELDS = """magic result requested_bytes read_count polls last_sr control ipsr
cpu_ccr original_msp original_msplim ahb5enr ahb5rstr mux_cr cr dcr1 dcr2
initial_sr ccr tcr ir initial_dlr initial_ar sequence command flash_offset""".split()
WRITE_FIELDS = """magic result sequence command stage address transfer_count polls last_sr
nor_status nor_security jedec_id changed_mask erased_mask completed_mask pages_programmed
current_crc input_crc final_crc expected_current_crc expected_input_crc flags failure_stage
failure_address failure_opcode last_opcode control ipsr cpu_ccr old_msp old_msplim ahb5enr
ahb5rstr mux_cr original_cr original_dcr1 original_dcr2 original_sr original_ccr original_tcr
original_ir original_dlr original_ar cfgr1 cfgr2 pll1cfgr1 pll1cfgr2 pll1cfgr3 dwt_initial
dwt_final dwt_advance cleanup_result first_mismatch wren_count transaction_count max_wip_cycles""".split()


class NorError(RuntimeError):
    """Operation stopped; do not retry or reset automatically."""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_helper(helpers_dir, name):
    """Read and validate one immutable helper without creating files or devices."""
    folder = Path(helpers_dir) / name
    filename = "read.bin" if name == "reader" else "programmer.bin"
    binary = (folder / filename).read_bytes()
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8-sig"))
    expected = HELPER_HASHES[name]
    if (sha(binary) != expected or len(binary) != HELPER_SIZES[name]
            or manifest.get("binary_sha256") != expected
            or manifest.get("binary_bytes") != len(binary)):
        raise ValueError(f"{name} is not the exact pinned RAM helper")
    load = READ_LOAD if name == "reader" else WRITE_LOAD
    fields = READ_FIELDS if name == "reader" else WRITE_FIELDS

    def address(key):
        value = manifest.get(key)
        return int(value, 0) if isinstance(value, str) else value

    if (address("load") != load
            or address("thumb_entry") != (load | 1)
            or address("command_address") != COMMAND
            or address("status") != STATUS
            or manifest.get("status_fields_in_word_order") != fields):
        raise ValueError(f"{name} manifest does not match the fixed host ABI")
    if name != "reader":
        offset = 0 if name == "writer0" else BLOCK_BYTES
        if (manifest.get("revision") != 2
                or manifest.get("fixed_flash_base", 0) != offset
                or manifest.get("physical_write_window", [0, BLOCK_BYTES])
                != [offset, offset + BLOCK_BYTES]):
            raise ValueError(f"{name} does not describe its fixed write window")
    return binary


def validate_helpers(helpers_dir):
    """Validate all three pinned binaries and ABIs using local reads only.

    Call before opening serial/debug devices. No transport, work directory,
    compiler, instrument, or serial dependency is required. Each operation
    revalidates its own helper again before uploading it.
    """
    result = {}
    for name in ("reader", "writer0", "writer1"):
        binary = _read_helper(helpers_dir, name)
        result[name] = {"sha256": sha(binary), "bytes": len(binary)}
    return result


class Nor:
    def __init__(self, transport, helpers_dir, *, work_dir,
                 timeout=90.0, poll_interval=0.2):
        if timeout < 0 or poll_interval < 0:
            raise ValueError("Timeout and poll interval must be nonnegative")
        self.transport = transport
        self.helpers_dir = Path(helpers_dir).resolve()
        self.work_dir = Path(work_dir).resolve()
        self.work_dir.mkdir(parents=True, exist_ok=False)
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._available = True
        self._sequences = set()
        self.last_status = None

    def _require_available(self):
        if not self._available:
            raise NorError("Previous NOR operation did not complete successfully; "
                           "no further hardware action is permitted by this session")

    def _helper(self, name):
        return _read_helper(self.helpers_dir, name)

    def _files(self, action, binary, command, status_bytes, desired=None):
        sequence = command[1]
        folder = self.work_dir / f"{action}-{sequence:08x}"
        folder.mkdir()
        files = {"helper": folder / "helper.bin", "command": folder / "command.bin",
                 "clear": folder / "clear-status.bin"}
        files["helper"].write_bytes(binary)
        files["command"].write_bytes(struct.pack("<" + "I" * len(command), *command))
        files["clear"].write_bytes(bytes(status_bytes))
        if desired is not None:
            files["input"] = folder / "desired.bin"
            files["input"].write_bytes(desired)
        return files

    def _sequence(self):
        while True:
            sequence = secrets.randbits(32)
            if sequence and sequence not in self._sequences:
                self._sequences.add(sequence)
                return sequence

    def _record(self, event, **fields):
        self.transport.log(event, **fields)

    def _upload(self, address, length, label):
        data = self.transport.upload(address, length, label)
        if len(data) != length:
            raise NorError(f"Short RAM upload for {label}: expected {length} bytes")
        return data

    def _poll(self, fields, matches, label):
        deadline = time.monotonic() + self.timeout
        poll = 0
        while True:
            data = self._upload(STATUS, len(fields) * 4, f"{label}-status-{poll:04d}.bin")
            status = dict(zip(fields, struct.unpack("<" + "I" * len(fields), data)))
            self.last_status = status
            matched = matches(status)
            if matched:
                self._record("nor_progress", operation=label, sequence=status["sequence"],
                             command=status["command"], stage=status.get("stage"),
                             pages_programmed=status.get("pages_programmed"),
                             completed_mask=status.get("completed_mask"),
                             read_count=status.get("read_count"))
            if status["magic"] == DONE and matched:
                self._record("nor_done", operation=label, status=status)
                return status
            if time.monotonic() >= deadline:
                self._record("nor_completion_unknown", operation=label, status=status)
                raise NorError("No fresh operation-matched DONE; target left running unchanged")
            poll += 1
            time.sleep(self.poll_interval)

    def read(self, offset):
        """Read one complete install sector or its following 4 KiB guard region."""
        self._require_available()
        if type(offset) is not int or offset not in (0, BLOCK_BYTES, 2 * BLOCK_BYTES):
            raise ValueError("Read offset must be 0, 65536, or 131072")
        count = 4096 if offset == 2 * BLOCK_BYTES else BLOCK_BYTES
        binary = self._helper("reader")
        sequence = self._sequence()
        label = f"read-{offset}-{sequence:08x}"
        command = [0x4E4F5244, sequence, 1, count, offset]
        files = self._files(label, binary, command, len(READ_FIELDS) * 4)
        self._record("nor_read_start", offset=offset, bytes=count, sequence=sequence,
                     helper_sha256=sha(binary))
        # From the first possible target mutation onward, exceptions leave this
        # instance locked. In particular, no finally block issues a halt/reset.
        self._available = False
        self.transport.call("-halt", "-w", files["helper"], hex(READ_LOAD), "-v",
                            "-w", files["clear"], hex(STATUS), "-v",
                            "-w", files["command"], hex(COMMAND), "-v",
                            "-coreReg", f"PC={hex(READ_LOAD | 1)}", "XPSR=0x01000000",
                            "-run", success="Core run")
        status = self._poll(READ_FIELDS, lambda s: s["sequence"] == sequence
                            and s["command"] == 1 and s["flash_offset"] == offset
                            and s["requested_bytes"] == count, label)
        if (status["result"] != 0 or status["read_count"] != count
                or status["last_sr"] & 0x7F21):
            raise NorError("NOR read helper failed or controller is not idle; target left unchanged")
        self.transport.call("-halt")
        data = self._upload(OUTPUT, count, f"{label}-readback.bin")
        self._record("nor_read_verified", offset=offset, bytes=count, sha256=sha(data),
                     sequence=sequence)
        self._available = True
        return data

    def _writer_operation(self, offset, binary, *, current=None, desired=None):
        writing = desired is not None
        opcode = 3 if writing else 2
        current_crc = zlib.crc32(current) if writing else 0
        desired_crc = zlib.crc32(desired) if writing else 0
        sequence = self._sequence()
        label = f"{'write' if writing else 'info'}-{offset}-{sequence:08x}"
        command = [0x4E4F5244, sequence, opcode, BLOCK_BYTES if writing else 0,
                   0, 0x57524954 if writing else 0, current_crc, desired_crc]
        files = self._files(label, binary, command, len(WRITE_FIELDS) * 4, desired)
        self._record("nor_write_start" if writing else "nor_info_start", offset=offset,
                     sequence=sequence, helper_sha256=sha(binary),
                     current_crc=current_crc, input_crc=desired_crc,
                     current_sha256=sha(current) if writing else None,
                     input_sha256=sha(desired) if writing else None)
        self._available = False
        self.transport.call("-halt", "-w", files["helper"], hex(WRITE_LOAD), "-v",
                            success="Download verified successfully")
        if writing:
            self.transport.call("-halt", "-w", files["input"], hex(INPUT), "-v",
                                success="Download verified successfully")
        self.transport.call("-halt", "-w", files["clear"], hex(STATUS), "-v",
                            "-w", files["command"], hex(COMMAND), "-v",
                            "-coreReg", f"PC={hex(WRITE_LOAD | 1)}", "XPSR=0x01000000",
                            "-run", success="Core run")
        status = self._poll(WRITE_FIELDS, lambda s: s["sequence"] == sequence
                            and s["command"] == opcode
                            and s["expected_current_crc"] == current_crc
                            and s["expected_input_crc"] == desired_crc, label)
        if (status["result"] != 0 or status["cleanup_result"] != 0
                or status["flags"] & 7 != 7 or status["flags"] & 16
                or status["nor_status"] & 3 or status["jedec_id"] != 0xC2803A):
            raise NorError("NOR helper did not finish safely; no halt, replacement, or retry")
        if writing:
            if (status["current_crc"] != current_crc or status["input_crc"] != desired_crc
                    or status["final_crc"] != desired_crc
                    or status["changed_mask"] != status["erased_mask"]
                    or status["changed_mask"] != status["completed_mask"]
                    or status["changed_mask"] & ~0xFFFF):
                raise NorError("NOR completion CRCs or erase/program masks disagree")
        elif (status["flags"] & 8 or status["changed_mask"] or status["erased_mask"]
              or status["completed_mask"] or status["pages_programmed"]):
            raise NorError("Read-only INFO unexpectedly reports a write")
        self.transport.call("-halt")
        if writing:
            data = self._upload(OUTPUT, BLOCK_BYTES, f"{label}-readback.bin")
            if data != desired:
                raise NorError("Full 64 KiB programmer readback differs from desired bytes")
            self._record("nor_write_verified", offset=offset, bytes=len(data),
                         sha256=sha(data), sequence=sequence, status=status)
        self._available = True
        return status

    def write(self, offset, current, desired):
        """INFO, then guarded fixed-window write and full programmer readback.

        current must be the fresh complete flash backup. The pinned helper
        independently rereads and CRC-checks it before the first erase. Caller
        independently rereads both installed sectors and the 4 KiB guard after
        both writes, then decides when a normal reset is appropriate.
        """
        self._require_available()
        if type(offset) is not int or offset not in (0, BLOCK_BYTES):
            raise ValueError("Write offset must be 0 or 65536")
        if not isinstance(current, bytes) or not isinstance(desired, bytes):
            raise ValueError("Current and desired images must be immutable bytes")
        if len(current) != BLOCK_BYTES or len(desired) != BLOCK_BYTES:
            raise ValueError("Current and desired images must each contain exactly 65536 bytes")
        binary = self._helper("writer0" if offset == 0 else "writer1")
        self._writer_operation(offset, binary)
        return self._writer_operation(offset, binary, current=current, desired=desired)
