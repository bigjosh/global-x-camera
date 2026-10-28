"""Bound energy for every fixed-duration placement inside a host bracket.

This is an offline secondary analysis, not electrical synchronization. COMPLETE
cycles divided by the reported 400 MHz CPU clock supply the assumed duration.
The start may be anywhere in the host bracket enlarged by its explicit UTC
uncertainty. No waveform feature or favorable start is selected.

Within one logged power chunk, the sum and extrema bound any partial overlap.
Those bounds are piecewise linear in overlap length. A sliding fixed-length
window changes slope only at chunk boundaries and the two overlap thresholds
where those bounds change branch. Evaluating their union therefore covers all
continuous placements; this is not a sampled search.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import energy


def require(condition, message):
    if not condition:
        raise energy.EvidenceError(message)


def fixed_duration_bounds(chunks, host_window, duration_s):
    duration_s = energy.finite(duration_s, "fixed target duration")
    require(duration_s > 0, "Fixed duration must be positive")
    # Reuse coverage and UTC mapping-residual checks, including wrong-unit
    # uncertainty rejection. The returned host energy itself is not reused.
    host = energy.measure(chunks, host_window)
    rate = chunks[0].rate
    uncertainty = host["boundary_uncertainty_samples"]
    outer_start = host["start_sample_id"] - uncertainty
    outer_end = host["end_sample_id"] + uncertainty
    length = duration_s * rate
    start_low, start_high = outer_start, outer_end - length
    require(start_low <= start_high, "Fixed duration exceeds containing host bracket")
    relevant = [c for c in chunks if c.end > outer_start and c.start < outer_end]
    require(bool(relevant), "No samples cover the feasible placements")
    candidates = {start_low, start_high}

    def add(value):
        if start_low <= value <= start_high:
            candidates.add(value)

    for chunk in relevant:
        # All corners of the overlap-length trapezoid.
        for value in (chunk.start-length, chunk.end-length, chunk.start, chunk.end):
            add(value)
        span = chunk.end - chunk.start
        delta = chunk.maximum - chunk.minimum
        if delta > 0:
            # Thresholds are in native-sample units, not decimated sample count.
            lower_switch = (chunk.maximum * span - chunk.total_j * rate) / delta
            upper_switch = (chunk.total_j * rate - chunk.minimum * span) / delta
            for overlap in (lower_switch, upper_switch):
                # A real partial overlap cannot exceed the shorter interval.
                if 0 <= overlap <= min(span, length):
                    add(chunk.start + overlap - length)  # growing overlap
                    add(chunk.end - overlap)             # shrinking overlap
    low, high = math.inf, -math.inf
    for start in sorted(candidates):
        a, b, _ = energy.integrate(relevant, start, start+length)
        low, high = min(low, a), max(high, b)
    # Cover floating-point arithmetic around large native sample IDs. This is
    # numerical slack only; it is not a sensor calibration or clock bound.
    absolute_scale = sum(
        max(abs(c.minimum), abs(c.maximum)) * (c.end-c.start) / rate
        for c in relevant
    )
    position_ulp = max(math.ulp(outer_start), math.ulp(outer_end), math.ulp(length))
    maximum_power = max(max(abs(c.minimum), abs(c.maximum)) for c in relevant)
    numerical_slack = max(
        1e-9, absolute_scale * 1e-12,
        16 * len(relevant) * position_ulp * maximum_power / rate,
    )
    low -= numerical_slack
    high += numerical_slack
    return {
        "schema": 1,
        "status": "all feasible fixed-duration placements bounded",
        "fixed_duration_s": duration_s,
        "feasible_start_sample_ids": [start_low, start_high],
        "containing_sample_ids": [outer_start, outer_end],
        "energy_bounds_j": [low, high],
        "mean_power_bounds_w": [low/duration_s, high/duration_s],
        "critical_positions_evaluated": len(candidates),
        "power_chunks_considered": len(relevant),
        "numeric_slack_j": numerical_slack,
        "driver_utc_mapping_max_residual_s": host["driver_utc_mapping_max_residual_s"],
        "physical_alignment_verified": False,
        "scope_notes": [
            "All continuous starts within the enlarged host bracket are included.",
            "Fixed duration assumes the reported CPU clock is accurate and continuous.",
            "COMPLETE excludes entry setup and final return; its firmware-defined scope remains unchanged.",
            "No sample ordering inside a chunk was retained; extrema and sums bound partial overlaps.",
            "No baseline subtraction, waveform alignment or preferred placement is used.",
            "Bounds exclude calibration, clipping and power paths bypassing the Joulescope.",
        ],
    }


def analyze_comparison(comparison, stream_raw):
    require(comparison.get("schema") == 1 and bool(comparison.get("runs")),
            "Expected a completed compare_runs schema1 result")
    stream_sha = hashlib.sha256(stream_raw).hexdigest()
    records = [json.loads(line) for line in stream_raw.decode("utf-8-sig").splitlines()
               if line.strip()]
    chunks, finalized = energy.load_chunks(records)
    rows = []
    for run in comparison["runs"]:
        require(run.get("cpu_hz") == 400000000 and "complete_s" in run,
                "Expected COMPLETE evidence at reported 400 MHz")
        measurement = run.get("host_bracket_energy", {})
        require(measurement.get("stream_log_sha256") == stream_sha,
                "Power snapshot differs from the validated comparison")
        require("host_window" in run, "No recorded host bracket")
        bounds = fixed_duration_bounds(chunks, run["host_window"], run["complete_s"])
        rows.append({
            "result": run["result"],
            "result_sha256": run["result_sha256"],
            "module_sha256": run["module_sha256"],
            "mode": run["mode"],
            "png_bytes": run["png_bytes"],
            "cpu_hz": run["cpu_hz"],
            "sd_hz": run["sd_hz"],
            "cache_evidence": run["cache_evidence"],
            "card_identity": run["card_identity"],
            "fixed_duration_analysis": bounds,
        })
    return {
        "schema": 1,
        "frame_sha256": comparison["frame_sha256"],
        "stream_log_sha256": stream_sha,
        "recording_finalized": finalized,
        "runs": rows,
        "scope": "Secondary containment analysis; no electrical synchronization established",
        "configuration_policy": "Rows retain module/card/cache/clock identity; distinct builds are not pooled",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", required=True, type=Path)
    parser.add_argument("--stream-log", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    require(args.out.resolve() not in {args.comparison.resolve(), args.stream_log.resolve()},
            "Output must not overwrite source evidence")
    comparison_raw = args.comparison.read_bytes()
    result = analyze_comparison(json.loads(comparison_raw.decode("utf-8-sig")),
                                args.stream_log.read_bytes())
    result["comparison_sha256"] = hashlib.sha256(comparison_raw).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"runs": len(result["runs"]), "output": str(args.out)}))


if __name__ == "__main__":
    main()
