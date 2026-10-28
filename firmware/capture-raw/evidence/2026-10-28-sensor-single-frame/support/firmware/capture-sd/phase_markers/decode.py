"""Decode PD12 phase pulses from Saleae's documented v0 binary exports.

Widths identify software observations, not proof of physical Standby, file
integrity, or an electrical power-good specification. No hardware access.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

EVENTS = {
    1: "receiver_entry",
    2: "first_strobe_irq_observed",
    3: "first_frame_complete_irq_observed",
    4: "save_entry",
    5: "sd_init_complete",
    6: "mount_complete",
    7: "png_encode_complete",
    8: "file_commit_close_complete",
    9: "cache_cleanup_uncached_validation_snapshots_complete",
    10: "pre_standby_wfi_or_awake_diagnostic_completion",
}
STEP_S = 0.5e-6
TOLERANCE_S = 0.15e-6
MAX_TRANSITIONS = 2_000_000


def read_digital(path):
    path = Path(path)
    size = path.stat().st_size
    if size > 44 + 8 * MAX_TRANSITIONS:
        raise ValueError("Transition export exceeds this phase decoder's bounded input size")
    payload = path.read_bytes()
    if len(payload) < 44:
        raise ValueError("Truncated Saleae header")
    magic, version, kind, initial, begin, end, count = struct.unpack_from("<8siiIddQ", payload)
    if magic != b"<SALEAE>" or version != 0 or kind != 0:
        raise ValueError("Expected documented Saleae digital binary version 0")
    if initial not in (0, 1) or not math.isfinite(begin) or not math.isfinite(end) or end < begin:
        raise ValueError("Invalid digital channel header")
    if len(payload) != 44 + 8 * count:
        raise ValueError("Transition-count/file-length mismatch")
    times = [x[0] for x in struct.iter_unpack("<d", payload[44:])]
    previous = None
    for value in times:
        if not math.isfinite(value) or not begin <= value <= end:
            raise ValueError("Invalid transition time")
        if previous is not None and value <= previous:
            raise ValueError("Transition times must increase strictly")
        previous = value
    return dict(path=str(path), bytes=size, sha256=hashlib.sha256(payload).hexdigest(),
                format_version=version, initial_state=initial, begin_s=begin, end_s=end,
                transitions=times)


def rising_edges(channel):
    # Each exported timestamp toggles the previous state.
    return channel["transitions"][0 if channel["initial_state"] == 0 else 1::2]


def pulses(channel):
    state = channel["initial_state"]
    start = channel["begin_s"] if state else None
    complete_start = not bool(state)
    result = []
    for at in channel["transitions"]:
        if state == 0:
            start, complete_start = at, True
        else:
            result.append(dict(start_s=start, end_s=at, width_s=at-start,
                               complete=complete_start))
            start = None
        state ^= 1
    if state:
        result.append(dict(start_s=start, end_s=channel["end_s"],
                           width_s=channel["end_s"]-start, complete=False))
    return result


def decode(channel, reset=None, power=None, *, sequence="cold"):
    if sequence not in ("cold", "storage"):
        raise ValueError("Sequence must be cold or storage")
    expected = list(range(1, 11)) if sequence == "cold" else list(range(4, 10))
    decoded, errors, cycles = [], [], []
    for index, pulse in enumerate(pulses(channel)):
        p = dict(pulse, index=index, event_id=None, event=None)
        if not p["complete"]:
            p["error"] = "partial_high_pulse_at_capture_boundary"
        else:
            event_id = int(math.floor(p["width_s"] / STEP_S + 0.5))
            delta = p["width_s"] - event_id * STEP_S
            # Tiny rounding slack only; this is not an extra sample of tolerance.
            if event_id not in EVENTS or abs(delta) > TOLERANCE_S + 1e-15:
                p["error"] = "unknown_pulse_width"
            else:
                p.update(event_id=event_id, event=EVENTS[event_id], width_error_s=delta)
        decoded.append(p)
        if "error" in p:
            errors.append(dict(pulse_index=index, error=p["error"]))

    current = None
    for pulse in decoded:
        event_id = pulse["event_id"]
        if event_id == expected[0]:
            if current is not None:
                cycles.append(current)
            current = dict(events=[], unexpected=[], first_edge_s=pulse["start_s"])
        if current is None:
            if event_id is not None:
                errors.append(dict(pulse_index=pulse["index"], error="event_before_sequence_start"))
            continue
        if event_id is None:
            current["unexpected"].append(pulse["index"])
        else:
            current["events"].append(pulse)
    if current is not None:
        cycles.append(current)

    reset_rises = rising_edges(reset) if reset else []
    power_rises = rising_edges(power) if power else []
    for cycle in cycles:
        events = cycle["events"]
        ids = [p["event_id"] for p in events]
        cycle["event_ids"] = ids
        cycle["marker_protocol_complete"] = ids == expected and not cycle["unexpected"]
        cycle["missing_event_ids"] = [i for i in expected if i not in ids]
        cycle["sequence_valid"] = ids == sorted(set(ids)) and all(i in expected for i in ids)
        cycle["intervals"] = [dict(from_event=a["event_id"], to_event=b["event_id"],
                                   first_edge_delta_s=b["start_s"]-a["start_s"])
                              for a, b in zip(events, events[1:])]
        cycle["elapsed_from_sequence_start_s"] = {
            str(p["event_id"]): p["start_s"]-cycle["first_edge_s"] for p in events}
        # These are observed crossings; initial-HIGH means no observed edge.
        before_reset = [x for x in reset_rises if x <= cycle["first_edge_s"]]
        before_power = [x for x in power_rises if x <= cycle["first_edge_s"]]
        cycle["preceding_observed_reset_release_s"] = before_reset[-1] if before_reset else None
        cycle["preceding_observed_5v_threshold_crossing_s"] = before_power[-1] if before_power else None
        cycle["reset_release_to_sequence_start_s"] = (
            cycle["first_edge_s"] - before_reset[-1] if before_reset else None)
        cycle["power_threshold_to_sequence_start_s"] = (
            cycle["first_edge_s"] - before_power[-1] if before_power else None)
        if sequence == "cold":
            cycle["elapsed_from_receiver_entry_s"] = dict(cycle["elapsed_from_sequence_start_s"])
            cycle["reset_release_to_receiver_entry_s"] = cycle["reset_release_to_sequence_start_s"]
            cycle["power_threshold_to_receiver_entry_s"] = cycle["power_threshold_to_sequence_start_s"]
    return dict(schema=1, marker_channel=1, marker_pin="PD12 / CN15.21 / Arduino D8",
                sequence=sequence, expected_event_ids=expected,
                nominal_step_s=STEP_S, tolerance_s=TOLERANCE_S, pulses=decoded,
                cycles=cycles, errors=errors,
                decode_passed=bool(cycles) and not errors and all(c["marker_protocol_complete"] for c in cycles),
                actual_standby_verified=False, image_integrity_verified=False,
                limitations=[
                    "Event timestamps are observed GPIO rising edges after their software checkpoints.",
                    "First STROBE/frame IRQ observations include interrupt latency.",
                    "Event 9 precedes final COMPLETE/terminal report publication and return to the receiver.",
                    "Event 10 is pre-WFI intent or awake diagnostic completion, not proof of Standby.",
                    "Power channel is a digital threshold crossing, not an analog power-good guarantee.",
                    "Missing edges are not invented for channels initially HIGH.",
                    "Host UTC/monotonic times do not synchronize independent instruments.",
                    "Pulse calls and code-layout changes can perturb the measured firmware."])


def summarize_folder(folder, *, sequence="cold"):
    folder = Path(folder)
    binary = folder / "binary" if (folder / "binary").is_dir() else folder
    channels = {n: read_digital(binary / f"digital_{n}.bin") for n in (0, 1, 4, 6)
                if (binary / f"digital_{n}.bin").exists()}
    if 1 not in channels:
        raise ValueError("Missing marker digital_1.bin")
    # All channels must be from the same capture/export interval. One 100 MS/s
    # sample allows representation/endpoint quantization, not arbitrary cropping.
    for n, c in channels.items():
        if any(abs(c[key] - channels[1][key]) > 1e-8 + 1e-15 for key in ("begin_s", "end_s")):
            raise ValueError(f"Channel {n} capture time bounds differ from the marker channel")
    result = decode(channels[1], channels.get(0), channels.get(4), sequence=sequence)
    result["input_files"] = {str(n): {k:v for k,v in c.items() if k != "transitions"}
                             for n,c in channels.items()}
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--sequence", choices=("cold", "storage"), default="cold",
                    help="cold requires events1..10; storage requires RAM SAVE events4..9.")
    args = ap.parse_args()
    result = summarize_folder(args.folder, sequence=args.sequence)
    text = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    raise SystemExit(0 if result["decode_passed"] else 2)
