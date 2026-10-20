"""Replay archived energy without instruments or private image bytes.

Expected layout:
  energy-analysis/{comparison,summary,fixed-duration-bounds}.json
  energy-input/power.jsonl.gz
  support/firmware/capture-sd/{energy,energy_sliding,compare_runs}.py
  results/<run>/result.json
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys


def check(condition, description):
    if not condition:
        raise ValueError(description)


def close_bounds(actual, expected, description):
    check(len(actual) == len(expected) == 2 and all(
        math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-9)
        for a, b in zip(actual, expected)
    ), description)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    archive = args.archive_root.resolve()
    sys.path.insert(0, str(archive/"support/firmware/capture-sd"))
    import compare_runs
    import energy
    import energy_sliding

    folder = archive/"energy-analysis"
    comparison = json.loads((folder/"comparison.json").read_text())
    summary = json.loads((folder/"summary.json").read_text())
    sliding = json.loads((folder/"fixed-duration-bounds.json").read_text())
    power_raw = gzip.decompress((archive/"energy-input/power.jsonl.gz").read_bytes())
    power_sha = hashlib.sha256(power_raw).hexdigest()
    check(power_sha == summary["power_sha256"] == sliding["stream_log_sha256"],
          "Final power log SHA mismatch")
    records = [json.loads(line) for line in power_raw.decode("utf-8-sig").splitlines() if line.strip()]
    chunks, finalized = energy.load_chunks(records)
    check(finalized, "Expected cleanly finalized power log")
    fixed_by_run = {
        Path(r["result"].replace("\\", "/")).parent.name: r["fixed_duration_analysis"]
        for r in sliding["runs"]
    }
    seen = set()
    verified = []
    for row in comparison["runs"]:
        name = Path(row["result"].replace("\\", "/")).parent.name
        check(name not in seen, "Duplicate run")
        seen.add(name)
        raw = (archive/"results"/name/"result.json").read_bytes()
        check(hashlib.sha256(raw).hexdigest() == row["result_sha256"], "Result SHA mismatch")
        result = json.loads(raw.decode("utf-8-sig"))
        report, policy = compare_runs.validate_save(result, comparison["frame_fnv"])
        check(result["module_sha256"] == row["module_sha256"], "Module SHA mismatch")
        check(policy == row["cache_evidence"], "Cache policy mismatch")
        window, host_seconds = compare_runs.host_window(
            result, row["host_window"]["boundary_uncertainty_s"])
        for key, value in window.items():
            check(value == row["host_window"][key], "Host-window mismatch")
        check(math.isclose(host_seconds, row["host_bracket_duration_s"], abs_tol=1e-9),
              "Host duration mismatch")
        check(row["host_bracket_energy"]["stream_log_sha256"] == power_sha,
              "Run power snapshot mismatch")
        measured = energy.measure(chunks, window)
        close_bounds(measured["energy_bounds_j"],
                     row["host_bracket_energy"]["energy_bounds_j"], "Host energy differs")
        if "baseline" in row["host_window"]:
            baseline = energy.measure(chunks, row["host_window"]["baseline"])
            close_bounds(baseline["energy_bounds_j"],
                         row["host_bracket_energy"]["baseline"]["energy_bounds_j"],
                         "Baseline energy differs")
        if name in fixed_by_run:
            check(report["cpu_hz"] == 400000000, "Unexpected cycle clock")
            duration = report["complete"] / report["cpu_hz"]
            fixed = energy_sliding.fixed_duration_bounds(chunks, window, duration)
            close_bounds(fixed["energy_bounds_j"], fixed_by_run[name]["energy_bounds_j"],
                         "All-placement fixed-duration bounds differ")
        verified.append(name)
    check(len(verified) == len(comparison["runs"]) == 21, "Expected 21 strict runs")
    check(len(fixed_by_run) == 18, "Expected 18 COMPLETE windows")
    print(json.dumps({
        "verified_runs": len(verified),
        "verified_complete_windows": len(fixed_by_run),
        "power_sha256": power_sha,
        "recording_finalized": True,
        "private_frame_bytes_required": False,
        "frame_identity_limitation": (
            "Reports are checked against the recorded target FNV; private RAW SHA "
            "is retained as provenance but cannot be re-derived without the RAW file."
        ),
        "hardware_access": False,
    }, indent=2))


if __name__ == "__main__":
    main()
