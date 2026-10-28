"""Decode one fixed RAM cycle log offline; never access the DUT or instruments.

Event definitions are the exact headers copied into the inspected build. A
caller can bind each header to its recorded SHA-256; the decoded report always
records the hashes actually read. Event slots retain the last occurrence, not
an implicit sequence of every loop iteration. All offsets are relative to the
init timestamp modulo 2**32 and require a run shorter than one CYCCNT wrap.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

ADDRESS = 0x343FB000
WORDS = 256
MAGIC = 0x314C5443
SCHEMA = 1
HZ = 400000000
DONE = 0x454E4F44
UNSET = 0xFFFFFFFF
EVENT_WORD = 32
EVENT_COUNT = 128
COUNTER_WORD = 160
COUNTER_COUNT = 32

_DEFINITION = re.compile(
    r"^\s*#\s*define\s+(CT[EC]_[A-Za-z0-9_]+)\s+"
    r"(0[xX][0-9a-fA-F]+|[0-9]+)[uUlL]*\s*"
    r"(?://\s*(.*?)\s*|/\*\s*(.*?)\s*\*/\s*)?$"
)
_PREFIX = re.compile(r"^\s*#\s*define\s+CT[EC]_")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def parse_definitions(text, source="<text>"):
    """Parse literal CTE_/CTC_ defines, rejecting ambiguous IDs or expressions.

    Format: ``#define CTE_SENSOR_READY 4 // Sensor boot ready observed``.
    Hex IDs and C unsigned suffixes are accepted. A missing comment uses the
    macro name with underscores replaced by spaces, not invented semantics.
    """
    result = {"events": {}, "counters": {}}
    names = set()
    for line_no, line in enumerate(text.splitlines(), 1):
        match = _DEFINITION.fullmatch(line)
        if not match:
            if _PREFIX.match(line):
                raise ValueError(f"{source}:{line_no}: unsupported trace definition")
            continue
        name, value, slash_comment, block_comment = match.groups()
        kind = "events" if name.startswith("CTE_") else "counters"
        limit = EVENT_COUNT if kind == "events" else COUNTER_COUNT
        index = int(value, 16 if value.lower().startswith("0x") else 10)
        if index >= limit:
            raise ValueError(f"{source}:{line_no}: {name} ID {index} outside {kind} range")
        if name in names or index in result[kind]:
            raise ValueError(f"{source}:{line_no}: duplicate {kind} ID/name {name}={index}")
        names.add(name)
        result[kind][index] = {
            "id": index,
            "name": name[4:],
            "description": slash_comment or block_comment or name[4:].replace("_", " "),
            "source": str(source),
            "line": line_no,
        }
    return result


def load_definitions(headers, expected_sha256=None):
    """Load build-local event headers, optionally verifying exact header hashes.

    ``expected_sha256`` maps path strings to SHA-256. If supplied it must bind
    every supplied header, with no extra paths. This validates identity of the
    vocabulary only; live code/boot identity must be checked by the bench gate.
    """
    headers = [Path(path) for path in headers]
    if not headers:
        raise ValueError("At least one build event header is required")
    keys = [str(path) for path in headers]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate header path")
    expected = None if expected_sha256 is None else {
        str(Path(path)): value.lower() for path, value in expected_sha256.items()
    }
    if expected is not None and set(expected) != set(keys):
        raise ValueError("Expected SHA-256 map must bind exactly the supplied event headers")
    result = {"events": {}, "counters": {}, "headers": [], "hashes_verified": expected is not None}
    all_names = set()
    for path in headers:
        data = path.read_bytes()
        digest = sha256(data)
        if expected is not None and digest != expected[str(path)]:
            raise ValueError(f"Trace header SHA-256 mismatch: {path}")
        parsed = parse_definitions(data.decode("utf-8"), str(path))
        for kind in ("events", "counters"):
            for index, definition in parsed[kind].items():
                name = (kind, definition["name"])
                if index in result[kind] or name in all_names:
                    raise ValueError(f"Duplicate {kind} ID/name across headers: {definition['name']}={index}")
                result[kind][index] = definition
                all_names.add(name)
        result["headers"].append({"path": str(path), "sha256": digest, "bytes": len(data)})
    if not result["events"]:
        raise ValueError("No event definitions found")
    return result


def decode(data, definitions, *, require_complete=False):
    """Decode an exact 1024-byte dump; partial logs cannot imply completion.

    No pair durations are manufactured, because overlapping tasks, repeated
    slots and missing events require source-level interpretation. A numerical
    rollover is supported, but a log covering more than one wrap cannot be
    reconstructed from these 32-bit counters and must not be used as wall time.
    """
    if len(data) != WORDS * 4:
        raise ValueError(f"Cycle trace must contain exactly {WORDS * 4} bytes")
    words = struct.unpack("<256I", data)
    fixed = {0: MAGIC, 1: SCHEMA, 2: WORDS, 3: HZ, 7: EVENT_COUNT, 8: COUNTER_COUNT}
    for index, value in fixed.items():
        if words[index] != value:
            raise ValueError(f"Cycle trace header word {index}: expected 0x{value:08x}, got 0x{words[index]:08x}")
    if words[5] == UNSET:
        raise ValueError("Cycle trace initialization timestamp is unset")
    if words[9] not in (UNSET, DONE):
        raise ValueError("Invalid cycle trace completion marker")
    complete = words[9] == DONE
    if complete and (words[4] == UNSET or words[6] == UNSET):
        raise ValueError("DONE record lacks result or completion timestamp")
    if require_complete and not complete:
        raise ValueError("Cycle trace is partial: DONE has not been published")
    # The ABI leaves these words untouched. Reject format drift/corruption.
    if any(value != UNSET for value in words[10:EVENT_WORD] + words[192:]):
        raise ValueError("Reserved cycle trace words changed")
    start = words[5]
    events = []
    missing = []
    for index in range(EVENT_COUNT):
        value = words[EVENT_WORD + index]
        definition = definitions["events"].get(index)
        if value == UNSET:
            if definition is not None:
                missing.append(definition.copy())
            continue
        if definition is None:
            raise ValueError(f"Observed event ID {index} has no build definition")
        elapsed = (value - start) & UNSET
        events.append({**definition, "ticks": value, "since_init_ticks": elapsed,
                       "since_init_ms": elapsed * 1000 / HZ})
    events.sort(key=lambda event: (event["since_init_ticks"], event["id"]))
    counters = []
    for index in range(COUNTER_COUNT):
        value = words[COUNTER_WORD + index]
        definition = definitions["counters"].get(index)
        if definition is None:
            if value:
                raise ValueError(f"Nonzero counter ID {index} has no build definition")
            continue
        counters.append({**definition, "value": value})
    finish = None if words[6] == UNSET else (words[6] - start) & UNSET
    if complete and events and events[-1]["since_init_ticks"] > finish:
        raise ValueError("Event occurs after completed log (or counter span exceeds one wrap)")
    return {
        "address": ADDRESS,
        "bytes": len(data),
        "sha256": sha256(data),
        "schema": SCHEMA,
        "status": "complete" if complete else "partial",
        "result": None if words[4] == UNSET else words[4],
        "init_ticks": start,
        "completion_ticks": None if words[6] == UNSET else words[6],
        "completion_since_init_ms": None if finish is None else finish * 1000 / HZ,
        "clock_hz": HZ,
        "events": events,
        "never_hit": missing,
        "counters": counters,
        "event_headers": definitions.get("headers", []),
        "event_header_hashes_verified": definitions.get("hashes_verified", False),
        "basis": "One RAM snapshot; nominal 400 MHz CYCCNT offsets from logger initialization, not power/reset wall time.",
        "limits": [
            "Each fixed event slot retains its last hit; counters summarize only their named coarse loops.",
            "Repeated READ/SCR/SYNC calls can leave an earlier DONE when a later BEGIN fails; do not pair such slots as a duration.",
            "Offsets assume less than one 32-bit wrap (10.73741824 s) and an unchanged running CYCCNT.",
            "0xFFFFFFFF is the unset sentinel, so an event exactly at that counter value cannot be distinguished from never hit.",
            "Overlapping intervals are not additive; sleep/stopped clocks are not included in CYCCNT time.",
            "DONE is logger finalization, not proof of storage idle, successful capture, safe maintenance, or Standby.",
            "This decoder verifies no live firmware, boot freshness, image content, external timing or energy.",
        ],
    }


_PREFIX_EVENTS = {
    2: "Receiver main entered; SystemCoreClockUpdate has not run yet",
    3: "Receiver SystemCoreClockUpdate and HAL initialization finished",
    200: "Expanded SRAM ready; prefix context checks begin",
    208: "Initial XSHUTDOWN host-pin snapshot (not a sensor reset edge)",
    209: "Host drives XSHUTDOWN high (sensor may already have started)",
    220: "Prefix I2C configuration finished",
    100: "Sensor READY polling begins",
    101: "Sensor READY polling finished",
    102: "Sensor identity/revision checks finished",
    103: "Sensor BOOT command sequence begins",
    104: "Sensor BOOT acknowledgement and standby state observed",
    105: "Post-BOOT revision step finished (trimmed profile skips the read)",
    106: "Sensor GPIO configuration begins",
    107: "Sensor GPIO configuration finished; clock configuration begins",
    12: "Sensor clock configuration finished",
    15: "Manual frame/exposure/gain configuration finished",
    108: "Sensor CSI format/ROI configuration begins",
    109: "Sensor configuration finished",
    24: "Before sensor START timestamp and command",
    25: "Sensor START write returned; acknowledgement not yet awaited",
    203: "Early NOR read begins",
    204: "Early NOR read finished; CRC comparison follows",
    205: "Early NOR CRC accepted",
    206: "Early NOR vector/cache checks finished; receiver handoff follows",
    207: "Receiver reset entry before SystemInit and BSS initialization",
}


def decode_prefix(trace_header, event_records, sensor_status, loader_status, *, require_success=True):
    """Decode existing prefix telemetry from the same gated RAM snapshot.

    Layout/labels are verified against the frozen ``stage1.c`` and
    ``stage1_sensor.c`` in promoted-flash25-awake: CTP1 at 0x343F0000,
    records at 0x343F0100, SEN1 at 0x343F4000, S1OK at 0x343F3000.
    The caller binds the source/build and snapshot to its live maintenance
    proof. This function cannot detect a caller mixing files from two boots.
    Prefix code resets CYCCNT before expanded SRAM setup; receiver logging
    starts later but uses that same unchanged nominal 400 MHz counter.
    """
    for name, data, length in (("CTP1", trace_header, 256), ("SEN1", sensor_status, 128),
                               ("S1OK", loader_status, 256)):
        if len(data) != length:
            raise ValueError(f"{name} record must contain exactly {length} bytes")
    header = struct.unpack('<64I', trace_header)
    sensor = struct.unpack('<32I', sensor_status)
    loader = struct.unpack('<64I', loader_status)
    if header[0] != 0x43545031:
        raise ValueError("Prefix trace is not CTP1")
    count = header[2]
    if count > 200 or len(event_records) != count * 16:
        raise ValueError("CTP1 event count/record length is invalid")
    if sensor[0] != 0x53454E31:
        raise ValueError("Sensor prefix record is not SEN1")
    if loader[0] not in (0x53314F4B, 0x5331524E, 0x53314552):
        raise ValueError("Prefix loader record has an unknown magic")
    sensor_ok = sensor[1] == 37 and sensor[2] == 0
    loader_ok = loader[0] == 0x53314F4B and loader[1] == 0
    if loader_ok and (loader[2] == 0 or loader[3] != loader[2] or loader[20] != loader[21]):
        raise ValueError("S1OK loader count/CRC fields are inconsistent")
    if require_success and (not sensor_ok or not loader_ok):
        raise ValueError("Prefix sensor or loader did not report successful completion")
    records = list(struct.iter_unpack('<4I', event_records))
    events = []
    software_clock_exceptions = []
    for index, (event_id, ticks, hal_tick, hz) in enumerate(records):
        # The reviewed receiver emits event(2) before SystemCoreClockUpdate.
        # system.c initializes that *software variable* to HSI_VALUE=64 MHz;
        # BENCH_ROM_CLOCKS=1 leaves the already qualified 400 MHz ROM profile
        # untouched. capture_early's preceding 207 hardcodes 400 MHz, and the
        # following event3 reports the corrected variable. Admit only this
        # exact startup bracket, never normalize arbitrary clock mismatches.
        startup_software_clock = (
            hz == 64000000 and event_id == 2 and hal_tick == 0 and
            sum(record[0] == 2 for record in records) == 1 and
            sensor_ok and loader_ok and header[16:18] == (0x33330000, 0x00100000) and
            0 < index < len(records) - 1 and
            records[index - 1][0] == 207 and records[index - 1][3] == HZ and
            records[index + 1][0] == 3 and records[index + 1][3] == HZ and
            loader[25] <= records[index - 1][1] <= ticks <= records[index + 1][1]
        )
        if hz != HZ and not startup_software_clock:
            raise ValueError(f"CTP1 event {index} has unexpected clock {hz}")
        if startup_software_clock:
            software_clock_exceptions.append({
                "record_index": index, "event_id": event_id,
                "reported_software_clock_hz": hz, "qualified_dwt_clock_hz": HZ,
                "reason": "Receiver event2 precedes SystemCoreClockUpdate; software HSI default is stale while qualified ROM clocks remain unchanged.",
            })
        known = event_id in _PREFIX_EVENTS
        events.append({"record_index": index, "id": event_id, "ticks": ticks,
                       "hal_tick": hal_tick, "clock_hz": HZ,
                       "reported_software_clock_hz": hz,
                       "startup_software_clock_default": startup_software_clock,
                       "known_prefix_event": known,
                       "description": _PREFIX_EVENTS.get(event_id, f"CTP1 event {event_id} (not named by prefix decoder)"),
                       "since_prefix_dwt_zero_ms": ticks * 1000 / HZ})
    fixed = []
    if sensor_ok:
        for word, name, description in (
            (6, 'SENSOR_READY', 'Sensor READY polling returned successfully'),
            (7, 'SENSOR_BOOT_DONE', 'BOOT command acknowledgement and sensor standby state observed'),
            (4, 'SENSOR_START_BEGIN', 'Immediately before sensor START register write'),
            (5, 'SENSOR_START_END', 'Sensor START register write returned, before acknowledgement polling'),
        ):
            fixed.append({"source": "SEN1", "word": word, "name": name, "description": description,
                          "ticks": sensor[word], "since_prefix_dwt_zero_ms": sensor[word] * 1000 / HZ})
    if loader_ok:
        for word, name, description in (
            (24, 'EARLY_NOR_BEGIN', 'Before issuing finite early NOR read'),
            (25, 'EARLY_NOR_END', 'Early NOR bytes received, idle observed and prescaler restored; before final CRC comparison'),
        ):
            fixed.append({"source": "S1OK", "word": word, "name": name, "description": description,
                          "ticks": loader[word], "since_prefix_dwt_zero_ms": loader[word] * 1000 / HZ})
    fixed.sort(key=lambda item: item['ticks'])
    return {
        "clock_hz": HZ,
        "prefix_success": sensor_ok and loader_ok,
        "sensor_phase": sensor[1], "sensor_result": sensor[2], "loader_result": loader[1],
        "ctp_error": header[3], "event_count": count,
        "software_clock_exceptions": software_clock_exceptions,
        "events": events, "fixed_timestamps": fixed,
        "snapshots": {name: {"bytes": len(data), "sha256": sha256(data)} for name, data in (
            ("trace_header", trace_header), ("event_records", event_records),
            ("sensor_status", sensor_status), ("loader_status", loader_status))},
        "basis": "Same-snapshot prefix CYCCNT; nominal 400 MHz from the prefix's explicit DWT zero, after recovery selection.",
        "limits": [
            "No timestamp covers power arrival, reset release, ROM boot or recovery selection before DWT zero.",
            "Sensor READY/BOOT/START timestamps are host observations, not physical exposure edges.",
            "CTP1 also contains later receiver events; only reviewed prefix IDs have semantic labels here.",
            "The exact event207 → event2 → event3 startup bracket may report the stale 64 MHz SystemCoreClock default at event2; qualified DWT remains nominal 400 MHz.",
            "The caller must prove these four records and CTL1 came from one boot and the exact inspected build.",
            "No cross-run joins, energy estimate, sleep duration or inferred interval is produced.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path, help="Exact 1024-byte SRAM dump")
    parser.add_argument("--header", action="append", type=Path, required=True,
                        help="Build-local cycle_trace_events.h or cycle_trace_sd.h; repeat")
    parser.add_argument("--header-sha256", action="append", default=[], metavar="PATH=SHA256",
                        help="Expected build hash; if provided, bind every --header")
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    expected = None
    if args.header_sha256:
        expected = {}
        for entry in args.header_sha256:
            path, separator, digest = entry.rpartition("=")
            if not separator or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
                parser.error("--header-sha256 expects PATH=64_HEX_DIGITS")
            if str(Path(path)) in expected:
                parser.error("Duplicate --header-sha256 path")
            expected[str(Path(path))] = digest
    definitions = load_definitions(args.header, expected)
    result = decode(args.binary.read_bytes(), definitions, require_complete=args.require_complete)
    text = json.dumps(result, indent=2) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
