"""Offline integrity and NOR byte-comparison replay; no hardware dependencies."""
import hashlib
import json
from pathlib import Path
import zlib


def main():
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / "manifest.json").read_text())
    for name, expected in manifest["files"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Archive identity mismatch: " + name)
    def blob(name):
        return (root / name).read_bytes()
    def status(name):
        return json.loads(blob("operations/" + name + "/status.json"))
    incident = json.loads(blob("incident.json"))
    old = blob("inputs/v59-before.bin")
    desired = blob("inputs/v61b-desired.bin")
    partial = blob("operations/partial-nor-read/nor.bin")
    final = blob("operations/v61-independent-read/nor.bin")
    if not len(old) == len(desired) == len(partial) == len(final) == 65536:
        raise ValueError("Unexpected NOR evidence length")
    if (partial[:0x4000] != desired[:0x4000] or
            partial[0x4200:0x4300] != desired[0x4200:0x4300] or
            partial[0x4300:0x4400] == desired[0x4300:0x4400] or
            partial[0x5000:] != old[0x5000:] or final != desired):
        raise ValueError("Partial/final comparison differs")
    if zlib.crc32(partial) != incident["repair"]["expected_current_crc32"]:
        raise ValueError("Repair current CRC differs")
    before = blob("operations/following-nor-read/nor.bin")
    after = blob("operations/v61-independent-following/nor.bin")
    if len(before) != 4096 or before != after:
        raise ValueError("Following NOR guard differs")
    failed, info, repaired = [status(n) for n in
        ("install-v61", "nor-after-wel-failure", "repair-v61")]
    if (failed["result"] != 16 or failed["failure_stage"] != 8 or
            failed["failure_address"] != 0x4200 or failed["failure_opcode"] != 0x2B or
            failed["cleanup_result"] != 0 or failed["flags"] != 47):
        raise ValueError("Original failure status differs")
    if info["result"] != 0 or info["flags"] != 39:
        raise ValueError("Fresh idle INFO differs")
    if repaired["result"] != 0 or repaired["cleanup_result"] != 0 or repaired["flags"] != 47:
        raise ValueError("Repair result differs")
    print(json.dumps(dict(passed=True, hashes_verified=len(manifest["files"]),
        final_bytes_verified=len(final), following_guard_bytes=len(before),
        original_failure_preserved=True, cause_established=False), indent=2))


if __name__ == "__main__":
    main()
