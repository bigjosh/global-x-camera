"""Offline A/B timing summary; no instrument, serial, debugger or network access.

Usage: python analyze_ab.py [RUN_DIR ...] [--base BASE] [--out NEW_JSON]
Default discovery is BASE/control[0-9]* and BASE/early[0-9]*. Each run needs
capture/verified.json and trace/cycle-trace.json. Missing/incomplete runs are
reported as skipped, never assigned zero timings. Existing output is refused.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

BASE = Path(__file__).resolve().parent
MASK = 0xFFFFFFFF
PHASES = {
    "csd_ready_to_width_begin": ("SD_IDENTIFY_REGS_DONE", "SD_WIDTH_BEGIN"),
    "csd_ready_to_init_done": ("SD_IDENTIFY_REGS_DONE", "SD_INIT_DONE"),
    "identify_registers": ("SD_IDENTIFY_REGS_BEGIN", "SD_IDENTIFY_REGS_DONE"),
    "select": ("SD_SELECT_BEGIN", "SD_SELECT_DONE"),
    "clock_switch": ("SD_CLOCK_SWITCH_BEGIN", "SD_CLOCK_SWITCH_DONE"),
    "width_negotiation": ("SD_WIDTH_BEGIN", "SD_WIDTH_DONE"),
    "sd_init": ("SD_INIT_BEGIN", "SD_INIT_DONE"),
    "acmd41": ("SD_ACMD41_BEGIN", "SD_ACMD41_DONE"),
    "slot_scan": ("SLOT_SCAN_BEGIN", "SLOT_SCAN_DONE"),
    "slot_write": ("SLOT_WRITE_BEGIN", "SLOT_WRITE_DONE"),
    "cmd25_data_envelope": ("SD_CMD25_DONE", "SD_DATAEND"),
    "write_final_ready": ("SD_WRITE_FINAL_READY_BEGIN", "SD_WRITE_FINAL_READY_DONE"),
    "runtime_to_terminal": ("RUNTIME_BEGIN", "TERMINAL_READY"),
}
ORDER_EVENTS = (
    "SD_IDENTIFY_REGS_DONE", "SD_SELECT_BEGIN", "SD_SELECT_DONE",
    "SD_CLOCK_SWITCH_BEGIN", "SD_CLOCK_SWITCH_DONE", "SD_WIDTH_BEGIN",
)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def bind(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def analyze_files(label, capture_path, trace_path):
    v, t = read(capture_path), read(trace_path)
    p, card = v["proof"], v["card"]
    require(v.get("passed") is True and p["operation"] == 1 and p["state"] == 3
            and p["result"] == 0 and p["media_idle"] == 1
            and not any(p[k] for k in ("initialized", "controller_owned", "cleanup_error", "sd_error")),
            "Capture is not a completed successful idle operation")
    require(t["status"] == "complete" and t["result"] == 0 and t["clock_hz"] == 400000000,
            "Trace is incomplete, failed or uses an unqualified clock")
    hz, origin = t["clock_hz"], t["init_ticks"]
    total = (t["completion_ticks"] - origin) & MASK
    require(0 < total < MASK, "Invalid trace extent")
    events = {e["name"]: e["ticks"] for e in t["events"]}
    require(len(events) == len(t["events"]), "Duplicate trace event name")
    offsets = {name: (ticks - origin) & MASK for name, ticks in events.items()}
    require(all(ticks <= total for ticks in offsets.values()), "Event outside finalized trace extent")
    require(all(((p[key] - origin) & MASK) <= total for key in ("begin", "end")),
            "Capture timestamps do not lie within this trace")
    counters = {c["name"]: c["value"] for c in t["counters"]}
    durations, absent = {}, []
    for phase, (first, last) in PHASES.items():
        if first not in offsets or last not in offsets:
            absent.append({"phase": phase, "missing_events": [n for n in (first, last) if n not in offsets]})
            continue
        require(offsets[last] >= offsets[first], "Reversed interval: " + phase)
        durations[phase] = (offsets[last] - offsets[first]) * 1000 / hz
    if all(name in durations for name in ("select", "clock_switch")):
        durations["select_plus_clock_switch"] = durations["select"] + durations["clock_switch"]
    nested_frame = {}
    for phase in ("csd_ready_to_width_begin", "csd_ready_to_init_done"):
        first, last = PHASES[phase]
        needed = (first, last, "FRAME_CHECK_BEGIN", "FRAME_VALIDATED")
        if not all(name in offsets for name in needed):
            nested_frame[phase] = {"classification": "unavailable", "subtracted_ms": None}
            continue
        start, end, frame_start, frame_end = (offsets[name] for name in needed)
        require(frame_start <= frame_end, "Reversed frame validation interval")
        contained = start <= frame_start <= frame_end <= end
        overlap = max(start, frame_start) < min(end, frame_end)
        deduction = (frame_end - frame_start) * 1000 / hz if contained else 0.0
        nested_frame[phase] = {
            "classification": "fully_inside" if contained else "partially_overlaps_not_subtracted" if overlap else "outside",
            "frame_validation_ms": (frame_end - frame_start) * 1000 / hz,
            "subtracted_ms": deduction,
        }
        durations[phase + "_minus_fully_nested_frame_validation"] = durations[phase] - deduction
    order = sorted((name for name in ORDER_EVENTS if name in offsets), key=offsets.get)
    observed_early = None
    if all(n in offsets for n in ("SD_CLOCK_SWITCH_DONE", "SD_SELECT_BEGIN", "SD_SELECT_DONE", "SD_CLOCK_SWITCH_BEGIN")):
        if offsets["SD_CLOCK_SWITCH_DONE"] <= offsets["SD_SELECT_BEGIN"]:
            observed_early = True
        elif offsets["SD_SELECT_DONE"] <= offsets["SD_CLOCK_SWITCH_BEGIN"]:
            observed_early = False
        else:
            raise ValueError("Clock switch and selection unexpectedly overlap")
    return {
        "run": label, "completed": True, "binary_sha256": v["binary_sha256"],
        "sources": {"capture": bind(capture_path), "trace": bind(trace_path)},
        "nominal_dwt_hz": hz, "transfer_clock_hz": card["clock_hz"],
        "clock_switched_before_select": observed_early,
        "observed_order": [{"event": n, "since_trace_init_ms": offsets[n] * 1000 / hz} for n in order],
        "durations_ms": durations, "missing_intervals": absent,
        "nested_frame_validation_adjustment": nested_frame,
        "slot": p["slot"], "scan_headers": p["scan_headers"],
        "written_sectors": p["written_sectors"], "card_command_count": card.get("command_count"),
        "counters": counters,
        "transport_observed": "IDMA" if counters.get("SD_IDMA_TRANSFERS") == 1 and counters.get("SD_PIO_TRANSFERS") == 0 else
                              "PIO" if counters.get("SD_PIO_TRANSFERS") == 1 and counters.get("SD_IDMA_TRANSFERS") == 0 else "mixed_or_unavailable",
    }


def summarize(runs):
    groups = {}
    phase_names = sorted({key for run in runs for key in run["durations_ms"]})
    for early, name in ((False, "control"), (True, "early")):
        selected = [r for r in runs if r["clock_switched_before_select"] is early]
        if not selected:
            continue
        phases = {}
        for phase in phase_names:
            vals = [r["durations_ms"][phase] for r in selected if phase in r["durations_ms"]]
            if vals:
                phases[phase] = {"n": len(vals), "median": statistics.median(vals), "min": min(vals), "max": max(vals)}
        groups[name] = {"n": len(selected), "runs": [r["run"] for r in selected], "durations_ms": phases}
    differences = {}
    if all(n in groups for n in ("control", "early")):
        for phase in phase_names:
            a, b = groups["control"]["durations_ms"], groups["early"]["durations_ms"]
            if phase in a and phase in b:
                differences[phase] = a[phase]["median"] - b[phase]["median"]
    return {"groups_by_observed_clock_order": groups, "control_minus_early_median_ms": differences}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="*", type=Path)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--out", type=Path)
    a = parser.parse_args()
    paths = a.runs or sorted({*a.base.glob("control[0-9]*"), *a.base.glob("early[0-9]*")})
    runs, skipped = [], []
    for path in paths:
        try:
            runs.append(analyze_files(path.name, path / "capture/verified.json", path / "trace/cycle-trace.json"))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            skipped.append({"run": str(path), "reason": str(exc)})
    result = {"schema": 1, "hardware_access": False, "complete_runs": len(runs), "runs": runs,
              "skipped": skipped, **summarize(runs), "limits": [
        "Only completed capture/trace pairs are summarized; source hashes bind the input files, not new live hardware.",
        "CSD-ready means the SD_IDENTIFY_REGS_DONE software hook, not a new physical bus timestamp.",
        "Durations use observed timestamps, not event-ID order; early clock selection reverses two phases.",
        "select_plus_clock_switch sums only the two nonoverlapping intervals; csd_ready_to_width_begin also includes their surrounding software gaps.",
        "Frame-adjusted intervals subtract FRAME_CHECK_BEGIN to FRAME_VALIDATED only when that complete interval lies inside the enclosing phase; partial overlaps are reported and left unchanged.",
        "Frame-adjusted residuals still include other callbacks, card timing and host polling. They are not pure clock savings or exclusive CPU/bus time.",
        "The early candidate removes the redundant post-switch CMD13 while retaining post-select readiness; the comparison measures that combined sequence change, not frequency alone.",
        "ACMD41/card-state variation, callback timing and growing slot-scan count can confound whole-cycle comparisons.",
        "Intervals overlap and must not be added indiscriminately; write envelope is not pure payload or card-busy time.",
        "Warm RAM timing is not a cold-power or energy measurement. Image equality requires separate readback validation.",
    ]}
    text = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if a.out:
        with a.out.open("x", encoding="utf-8") as f:
            f.write(text)
    print(text, end="")


if __name__ == "__main__":
    main()
