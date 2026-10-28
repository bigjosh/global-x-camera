"""Read-only shutdown diagnostics; never halts, resets or accesses peripherals.

Debugger traffic can wake Sleep/Stop. Read only after a power recording has
finished. AXI SRAM is lost in Standby; use reset/recovery and SBF evidence there.
Prepared/armed records prove software intent, not physical low-power entry.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "firmware/boot-timing"))
from nor_bench import Bench


def enum_fields(path, prefix):
    text = re.sub(r"/\*.*?\*/|//[^\n]*", "", path.read_text(), flags=re.S)
    bodies = [x for x in re.findall(r"enum[^{]*\{(.*?)\}", text, re.S)
              if re.search(r"\b" + re.escape(prefix) + r"MAGIC\b", x)]
    if len(bodies) != 1:
        raise ValueError("Missing or ambiguous proof enum: " + str(path))
    fields = {}
    value = 0
    offsets = set()
    for declaration in bodies[0].split(","):
        if not declaration.strip():
            continue
        item = re.fullmatch(r"\s*(" + re.escape(prefix) + r"[A-Z0-9_]+)"
                            r"\s*(?:=\s*(0[xX][0-9a-fA-F]+|[0-9]+)[uUlL]*)?\s*",
                            declaration)
        if item is None:
            raise ValueError("Unsupported proof enum declaration: " + declaration.strip())
        name, assigned = item.groups()
        if assigned:
            value = int(assigned, 16 if assigned.lower().startswith("0x") else 10)
        key = name[len(prefix):].lower()
        if key in fields or value in offsets or not 0 <= value < 64:
            raise ValueError("Duplicate/out-of-bounds proof enum field")
        fields[key] = value
        offsets.add(value)
        value += 1
    return fields


def layout(receiver):
    completion = enum_fields(receiver / "completion.h", "LPC_")
    peripheral = enum_fields(receiver / "peripherals.h", "LP_")
    # These fixed positions define the firmware's FNV interval and the two
    # adjacent 256-byte records. Unknown future schemas must fail closed.
    expected = dict(magic=0, schema=1, words=2, checksum=62, terminal=63)
    if any(completion.get(name) != value for name, value in expected.items()):
        raise ValueError("Unsupported completion proof layout")
    if (peripheral.get("magic") != 0 or peripheral.get("schema") != 1
            or peripheral.get("terminal") != 63 or len(peripheral) != 64):
        raise ValueError("Unsupported peripheral proof layout")
    return completion, peripheral


def decode(raw, receiver):
    if len(raw) != 512:
        raise ValueError("Incomplete shutdown proof")
    words = struct.unpack("<128I", raw)
    completion_fields, peripheral_fields = layout(receiver)
    completion = {k: words[v] for k, v in completion_fields.items()}
    peripherals = {k: words[64 + v] for k, v in peripheral_fields.items()}
    digest = 2166136261
    for byte in raw[4:248]:
        digest = ((digest ^ byte) * 16777619) & 0xffffffff
    valid = (completion["magic"] == 0x4c504d31 and completion["schema"] == 1
             and completion["words"] == 64 and completion["checksum"] == digest
             and completion["terminal"] == 0x4c50454e)
    return dict(stable_checksum_valid=valid, completion=completion,
                peripherals=peripherals, raw_words=list(words),
                checksum_scope="Completion words 1..61 only; peripheral snapshot has no checksum.",
                physical_entry_proven=False,
                limitation="ARMED is intent; debugger reads may wake Sleep/Stop. Standby loses this SRAM.")


def checked_clock_word(receiver, code):
    """Only the final four-byte .data.SystemCoreClock word may be mutable."""
    raw_symbols = (receiver / "symbols.txt").read_bytes()
    text = raw_symbols.decode("utf-8")

    def symbol(name):
        values = re.findall(r"^([0-9a-fA-F]+)\s+([dD])\s+" + re.escape(name) + r"\s*$",
                            text, re.M)
        if len(values) != 1:
            raise ValueError("Missing/ambiguous data symbol: " + name)
        return int(values[0][0], 16)

    address = symbol("SystemCoreClock")
    offset = address - 0x34300000
    if (offset < 0 or offset % 4 or offset != len(code) - 4
            or symbol("_sdata") != address or symbol("_edata") != address + 4
            or code[offset:] != struct.pack("<I", 64_000_000)):
        raise ValueError("SystemCoreClock final .data layout or 64 MHz initializer differs")
    return dict(offset=offset, address=hex(address), initial_hz=64_000_000,
                expected_runtime_hz=400_000_000,
                symbols_sha256=hashlib.sha256(raw_symbols).hexdigest())


def validate_live_receiver(receiver, code, live):
    clock = checked_clock_word(receiver, code)
    offset = clock["offset"]
    if len(live) != len(code) or live[:offset] != code[:offset]:
        raise ValueError("Live receiver immutable bytes differ from the selected build")
    runtime, = struct.unpack("<I", live[offset:])
    if runtime != clock["expected_runtime_hz"]:
        raise ValueError("Live SystemCoreClock differs from the exact 400 MHz profile")
    return dict(live_code_matches=(live == code), live_immutable_code_matches=True,
                immutable_bytes=offset,
                system_core_clock=dict(clock, runtime_hz=runtime))


def verify_sources(manifest, source_root):
    verified = set()
    for source, expected in manifest["sources"].items():
        path = (source_root / source).resolve()
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Changed frozen source: " + source)
        verified.add(path)
    return verified


def verify_headers(directory, verified):
    for name in ("completion.h", "peripherals.h"):
        if (directory / name).resolve() not in verified:
            raise ValueError("Decoder header missing from frozen source manifest: " + name)
    layout(directory)


def load_late_build(receiver, manifest, source_root=ROOT):
    """Bind the separately loaded, immutable completion blob to this receiver."""
    identity = manifest.get("low_power", {}).get("late_module")
    if identity is None:
        return None
    directory = receiver.parent / "late"
    path = (source_root / identity["manifest_path"]).resolve()
    if path != (directory / "manifest.json").resolve():
        raise ValueError("Late manifest must be the selected build's frozen late/manifest.json")
    raw_manifest = path.read_bytes()
    if hashlib.sha256(raw_manifest).hexdigest() != identity["manifest_sha256"]:
        raise ValueError("Changed late manifest")
    late = json.loads(raw_manifest)
    # Check every copied identity field, including optional park addresses.
    for key, value in identity.items():
        if key not in ("manifest_path", "manifest_sha256") and late.get(key) != value:
            raise ValueError("Late manifest identity disagrees: " + key)
    verified = verify_sources(late, source_root)
    verify_headers(directory, verified)
    if late.get("binary_file") != "late.bin":
        raise ValueError("Unexpected late binary filename")
    code = (directory / "late.bin").read_bytes()
    if (late.get("schema") != 1
            or type(late.get("binary_bytes")) is not int
            or not 0 < len(code) == late["binary_bytes"] <= 0x2000
            or len(code) % 4
            or late.get("flash_offset") != 0xE000
            or int(late["load_address"], 0) != 0x343C0000
            or int(late["entry_address"], 0) != 0x343C0001
            or int(late["loader_proof_address"], 0) != 0x343F9B00
            or late.get("no_initialized_data_or_bss") is not True
            or late.get("section_sizes") != dict(text=len(code), data=0, bss=0)
            or hashlib.sha256(code).hexdigest() != late["binary_sha256"]
            or zlib.crc32(code) != int(late["crc32"], 0)):
        raise ValueError("Late image differs from bounded, stateless manifest")
    for key in ("sleep_idle_address", "failure_park_address", "return_park_address"):
        if key in late:
            address = int(late[key], 0)
            if address % 2 or not 0x343C0000 <= address < 0x343C0000 + len(code):
                raise ValueError("Late park outside immutable blob: " + key)
    if manifest.get("sleep_idle_address") != late["sleep_idle_address"]:
        raise ValueError("Receiver sleep park does not point to selected late image")
    return dict(directory=directory, manifest=late, identity=identity, code=code)


def validate_late_loader(raw, late, peripherals):
    if len(raw) != 64:
        raise ValueError("Incomplete late-loader proof")
    w = struct.unpack("<16I", raw)
    manifest = late["manifest"]
    if (w[:4] != (0x4C504C31, 1, 2, 0)
            or w[8] != manifest["binary_bytes"]
            or w[9] != int(manifest["crc32"], 0)
            or w[10] != int(manifest["entry_address"], 0)
            or not w[11]
            or w[12] & 0x30000 or w[13] & ~0xC or w[14] & 1
            or w[15] != 0x4C504C44
            or w[6] & 0x7F20 or w[7] & 0x7F21 or not w[7] & 2):
        raise ValueError("Late-loader proof is incomplete, failed or disagrees with the selected image")
    if peripherals.get("loader_return") not in (0, w[11]):
        raise ValueError("Late-loader and peripheral SAVE-return records disagree")
    return dict(verified=True, raw_words=list(w),
                proof_sha256=hashlib.sha256(raw).hexdigest(),
                scope="Successful immutable load before entry; not proof of physical low-power entry.")


def load_build(build, source_root=ROOT):
    """Validate local frozen inputs before creating any debugger client."""
    receiver = build.resolve() / "receiver"
    manifest = json.loads((receiver / "manifest.json").read_text())
    verified = verify_sources(manifest, source_root)
    late = load_late_build(receiver, manifest, source_root)
    if late is None:
        verify_headers(receiver, verified)
    code = (receiver / "capture.bin").read_bytes()
    if (type(manifest.get("raw_bytes")) is not int
            or not 0 < len(code) == manifest["raw_bytes"] <= 0x20000
            or int(manifest["vector_address"], 0) != 0x34300000
            or hashlib.sha256(code).hexdigest() != manifest["raw_sha256"]):
        raise ValueError("Receiver differs from bounded AXI SRAM manifest")
    checked_clock_word(receiver, code)
    return receiver, manifest, code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    receiver, manifest, code = load_build(args.build)
    late = load_late_build(receiver, manifest)
    bench = Bench(args.out)
    raw = bench.upload(0x343F9C00, 512, "shutdown-proof.bin")
    result = decode(raw, late["directory"] if late else receiver)
    (bench.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    if not result["stable_checksum_valid"]:
        raise ValueError("No stable checksum-valid completion record; raw evidence retained")
    live = bench.upload(0x34300000, len(code), "receiver.bin")
    result["receiver_validation"] = validate_live_receiver(receiver, code, live)
    result["receiver_sha256"] = manifest["raw_sha256"]
    if late:
        loader_raw = bench.upload(0x343F9B00, 64, "late-loader-proof.bin")
        result["late_loader_validation"] = validate_late_loader(
            loader_raw, late, result["peripherals"])
        live_late = bench.upload(0x343C0000, len(late["code"]), "late.bin")
        if live_late != late["code"]:
            raise ValueError("Live late completion bytes differ from the selected build")
        result["late_validation"] = dict(
            live_code_matches=True, immutable_bytes=len(live_late),
            binary_sha256=late["manifest"]["binary_sha256"],
            manifest_sha256=late["identity"]["manifest_sha256"])
    result["no_halt_reset_or_peripheral_access"] = True
    (bench.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("completion", "peripherals")}))


if __name__ == "__main__":
    main()
