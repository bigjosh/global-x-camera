"""Offline SAVE timing and optional host-bracket energy comparison.

Input JSON: {"schema": 1, "frame_file": ".../frame.bin",
 "measurement_setup": "unchanged wiring, supply and JS range",
 "runs": [{"result": ".../result.json",
           "stream_log": ".../power.jsonl", "boundary_uncertainty_s": 0.05,
           "baseline": {"start_sample_id": ..., "end_sample_id": ...}}]}

Paths are relative to that JSON. stream_log and baseline are optional. Energy
uses run_before through the first fresh terminal poll.after; it includes host
command, status polling and terminal-detection overhead. Firmware cycles stay
separate: no invented electrical alignment or automatic baseline interval.
Configuration groups never mix module hashes, clock rates or cache policies.
An explicit allow_live_stream_snapshot=true permits covered intervals from an
immutable snapshot of a running log; final logger counters remain unverified.
This script neither imports bench control nor opens instruments.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics

import energy


MODES = {0: "stored", 1: "fast-none", 2: "fast-sub"}
FRAME_BYTES = 1120 * 1364 * 2


def require(condition, message):
    if not condition:
        raise energy.EvidenceError(message)


def fnv1a(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xFFFFFFFF
    return value


def elapsed_stamp(stamp):
    return energy.utc_seconds(stamp["utc"]), energy.integer(stamp["monotonic_ns"], "monotonic stamp")


def host_window(result, uncertainty):
    """Broad recorded host interval, never presented as a target phase window."""
    timing = result["host_timing"]
    begin = timing["run_before"]
    start_utc, start_mono = elapsed_stamp(begin)
    _, run_after = elapsed_stamp(timing["run_after"])
    require(run_after >= start_mono, "Host run timestamps are reversed")
    previous = run_after
    terminal = None
    nonce = result["request"]["nonce"]
    for poll in timing["polls"]:
        _, before = elapsed_stamp(poll["before"])
        _, after = elapsed_stamp(poll["after"])
        require(previous <= before <= after, "Host poll timestamps are reversed")
        previous = after
        if poll.get("nonce") == nonce and poll.get("terminal") == 0x444F4E45:
            require(poll.get("state") == 2, "First fresh terminal poll is unsuccessful")
            terminal = poll["after"]
            break
    require(terminal is not None, "No fresh terminal poll brackets completion")
    end_utc, end_mono = elapsed_stamp(terminal)
    mono_seconds = (end_mono-start_mono) / 1e9
    utc_seconds = end_utc-start_utc
    require(mono_seconds > 0 and utc_seconds > 0, "Invalid host interval")
    uncertainty = energy.finite(uncertainty, "explicit UTC boundary uncertainty")
    require(uncertainty >= 0, "Negative UTC boundary uncertainty")
    require(abs(mono_seconds-utc_seconds) <= 2*uncertainty + 0.002,
            "Host UTC changed beyond supplied uncertainty")
    timing_field = "complete" if result.get("cache_report_extension") == 1 else "total"
    target_s = result["report"][timing_field] / result["report"]["cpu_hz"]
    require(target_s <= mono_seconds + 0.002,
            "Firmware duration exceeds the containing host interval")
    return dict(start_utc=begin["utc"], end_utc=terminal["utc"],
                boundary_uncertainty_s=uncertainty), mono_seconds


def validate_save(result, frame_fnv):
    r, card, fs, request = [result[key] for key in ("report", "card", "filesystem", "request")]
    required = dict(magic=0x53564431, schema=1, words=128, state=2, operation=1,
                    result=0, terminal=0x444F4E45, media_idle=1, card_error=0,
                    fs_result=0, png_result=0, width=1120, height=1364,
                    frame_bytes=FRAME_BYTES, rows=1364)
    require(all(r.get(k) == v for k, v in required.items()), "SAVE report is incomplete or unsuccessful")
    require(request.get("operation") == 1 and request.get("nonce", 0) != 0
            and r["nonce"] == request["nonce"] and r["mode"] == request["mode"],
            "SAVE request/nonce/mode does not match report")
    require(r["mode"] in MODES and r["cpu_hz"] == 400000000
            and r["sd_hz"] == request["sd_clock_hz"], "Unexpected mode or clocks")
    require(r["fnv_before"] == frame_fnv == r["fnv_after"],
            "Frame fingerprint differs from supplied frame or changed during SAVE")
    require(card.get("media_idle") == 1 and card.get("error") == 0
            and card.get("initialized") == 0 and card.get("controller_owned") == 0
            and fs.get("fat_result") == 0 and fs.get("completed") == 1
            and fs.get("bytes_written") == r["png_bytes"] > 0
            and fs.get("final_name") == r["name"], "Final storage snapshot is inconsistent")
    context = result["final_context"]
    require(context["ccr"] & 0x30000 == 0 and context["fpccr"] & 1 == 0
            and context["registers"].get("CONTROL") == 0
            and context["registers"].get("FAULTMASK") == 0,
            "Final cache/core context is not clean")
    require(re.fullmatch(r"[0-9a-f]{64}", result["module_sha256"]) is not None,
            "Missing module identity")
    for name in ("total", "encode", "callback", "finish", "init", "mount", "validate"):
        require(energy.integer(r[name], name) >= 0, "Negative cycle counter")
    require(r["total"] >= r["encode"] >= r["callback"], "Nested cycle scopes are inconsistent")
    # New modules expose cache policy explicitly. Old modules are kept in their
    # own hash group and labelled legacy rather than assuming a cache setting.
    extension = result.get("cache_report_extension", 0)
    require(extension in (0, 1), "Unsupported cache report extension")
    policy = {}
    if extension:
        require(isinstance(result.get("data_cache_enabled"), bool),
                "Cache policy must come from verified manifest metadata")
        require(r["cache_enabled"] == int(result["data_cache_enabled"])
                and r.get("final_ccr", 0x30000) & 0x30000 == 0,
                "New module did not prove final caches disabled")
        require(r.get("postclean_validated") == 1 and r.get("postclean_fnv") == frame_fnv,
                "New module lacks post-clean uncached frame validation")
        require(not r["cache_enabled"] or not r["initial_mpu_ctrl"] & 1,
                "Enabled D-cache inherited an unreviewed active MPU")
        policy = {k: r[k] for k in ("cache_enabled", "initial_mpu_ctrl", "final_ccr")}
    else:
        require(not any(r.get(k, 0) for k in ("cache_enabled", "complete", "postclean_validated")),
                "New cache evidence lacks verified manifest extension metadata")
    return r, policy


def summary(values):
    return dict(count=len(values), median=statistics.median(values),
                minimum=min(values), maximum=max(values))


def compare(spec, base):
    require(spec.get("schema") == 1, "Expected comparison schema 1")
    require(isinstance(spec.get("measurement_setup"), str) and bool(spec["measurement_setup"].strip()),
            "Describe the fixed measurement setup")
    live_allowed = spec.get("allow_live_stream_snapshot", False)
    require(isinstance(live_allowed, bool), "Live snapshot option must be explicit boolean")
    frame_path = (base / spec["frame_file"]).resolve()
    frame = frame_path.read_bytes()
    require(len(frame) == FRAME_BYTES, "Wrong RAW10 frame length")
    frame_fnv = fnv1a(frame)
    frame_sha = hashlib.sha256(frame).hexdigest()
    rows, groups, seen, identities = [], {}, set(), set()
    # Bind each immutable input path once, so every row sees the same snapshot
    # and a long finalized log need not be parsed again for every run.
    streams = {}
    require(isinstance(spec.get("runs"), list) and spec["runs"], "No runs selected")
    for entry in spec["runs"]:
        path = (base / entry["result"]).resolve()
        require(path not in seen, "Duplicate result would count one observation twice")
        seen.add(path)
        raw = path.read_bytes()
        result = json.loads(raw.decode("utf-8-sig"))
        r, cache = validate_save(result, frame_fnv)
        identity = (result["module_sha256"], r["nonce"])
        require(identity not in identities, "Duplicate operation nonce would count one observation twice")
        identities.add(identity)
        row = dict(result=str(path), result_sha256=hashlib.sha256(raw).hexdigest(),
                   module_sha256=result["module_sha256"], mode=MODES[r["mode"]],
                   nonce=r["nonce"], name=r["name"], cache_evidence=cache,
                   card_identity={k: result["card"][k] for k in
                                  ("cid0", "cid1", "cid2", "cid3", "sector_count")
                                  if k in result["card"]},
                   cpu_hz=r["cpu_hz"], sd_hz=r["sd_hz"], png_bytes=r["png_bytes"],
                   total_s=r["total"]/r["cpu_hz"],
                   encode_including_callback_s=r["encode"]/r["cpu_hz"],
                   encode_excluding_callback_s=(r["encode"]-r["callback"])/r["cpu_hz"],
                   callback_s=r["callback"]/r["cpu_hz"],
                   sd_write_s=card_time(result["card"], "write_cycles", r["cpu_hz"]))
        if result.get("cache_report_extension") == 1:
            require(energy.integer(r["complete"], "complete cycles") >= r["total"],
                    "Completion duration is shorter than legacy total")
            row["complete_s"] = r["complete"]/r["cpu_hz"]
            for name in ("cleanup", "postclean_validate"):
                if name in r:
                    require(0 <= energy.integer(r[name], name) <= r["complete"],
                            "Invalid cleanup/validation duration")
                    row[name+"_s"] = r[name]/r["cpu_hz"]
        if "stream_log" in entry:
            window, host_s = host_window(result, entry.get("boundary_uncertainty_s"))
            window.update(mode=row["mode"], frame_sha256=frame_sha, run_id=path.parent.name)
            if "baseline" in entry:
                window["baseline"] = entry["baseline"]
            stream_path = (base / entry["stream_log"]).resolve()
            if stream_path not in streams:
                stream_raw = stream_path.read_bytes()
                records = [json.loads(line) for line in stream_raw.decode("utf-8-sig").splitlines()
                           if line.strip()]
                streams[stream_path] = (records, hashlib.sha256(stream_raw).hexdigest())
            records, stream_sha = streams[stream_path]
            measurement = energy.analyze(records, window)
            require(measurement["recording_finalized"] or live_allowed,
                    "Finalize the power log or explicitly allow a live-stream snapshot")
            if not measurement["recording_finalized"]:
                measurement["live_snapshot_limitation"] = (
                    "Only received contiguous finite intervals are checked; final logger "
                    "drop/error counters and session cleanup are not yet available")
            measurement["stream_log_sha256"] = stream_sha
            row.update(host_bracket_duration_s=host_s, host_window=window,
                       host_bracket_energy=measurement)
        else:
            require("baseline" not in entry and "boundary_uncertainty_s" not in entry,
                    "Energy options supplied without a power stream")
        rows.append(row)
        key = json.dumps(dict(module_sha256=row["module_sha256"], cpu_hz=row["cpu_hz"],
                              sd_hz=row["sd_hz"], cache_evidence=cache,
                              card_identity=row["card_identity"]), sort_keys=True)
        groups.setdefault(key, []).append(row)
    summaries = []
    for key, grouped in groups.items():
        modes = {}
        for mode in MODES.values():
            selected = [r for r in grouped if r["mode"] == mode]
            if not selected:
                continue
            modes[mode] = {metric: summary([r[metric] for r in selected])
                          for metric in ("total_s", "encode_excluding_callback_s", "png_bytes")}
            if all("complete_s" in r for r in selected):
                modes[mode]["complete_s"] = summary([r["complete_s"] for r in selected])
            measured = [r for r in selected if "host_bracket_energy" in r]
            if measured:
                modes[mode]["energy_measured_runs"] = len(measured)
                modes[mode]["host_bracket_energy_median_bounds_j"] = [
                    statistics.median(r["host_bracket_energy"]["energy_bounds_j"][i] for r in measured)
                    for i in (0, 1)]
        summaries.append(dict(configuration=json.loads(key),
                              observed_order=[r["mode"] for r in grouped], modes=modes))
    return dict(schema=1, frame_sha256=frame_sha, frame_fnv=frame_fnv,
                measurement_setup=spec["measurement_setup"],
                allow_live_stream_snapshot=live_allowed, runs=rows, groups=summaries,
                scope_notes=[
                    "Firmware total scope is defined by the selected module; compare hashes separately.",
                    "Encode minus callback includes conversion, checksums and encoder overhead.",
                    "SD write and ready intervals overlap other scopes and must not be summed.",
                    "Host-bracket energy includes command setup, debug polling and detection tail.",
                    "Frame SHA binds the supplied dump; target FNV is an error check, not a cryptographic proof.",
                    "Reported medians/ranges describe these runs, not a confidence interval or card lifetime guarantee.",
                ])


def card_time(card, key, cpu_hz):
    return energy.integer(card[key], key) / cpu_hz


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    require(args.out.resolve() != args.spec.resolve(), "Output must not overwrite the input spec")
    spec = json.loads(args.spec.read_text(encoding="utf-8-sig"))
    result = compare(spec, args.spec.resolve().parent)
    inputs = {(args.spec.parent / spec["frame_file"]).resolve()}
    for entry in spec["runs"]:
        inputs.add((args.spec.parent / entry["result"]).resolve())
        if "stream_log" in entry:
            inputs.add((args.spec.parent / entry["stream_log"]).resolve())
    require(args.out.resolve() not in inputs, "Output must not overwrite evidence")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(dict(runs=len(result["runs"]), configurations=len(result["groups"]),
                          output=str(args.out))))


if __name__ == "__main__":
    main()
