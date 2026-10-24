"""Offline same-frame timing plus conservative host-contained energy bounds."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT / "firmware/capture-sd"))
import compare_runs
import energy_sliding


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, obj):
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def stats(values):
    return dict(minimum=min(values), median=statistics.median(values), maximum=max(values))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, choices=(2, 3), required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists():
        raise ValueError("New analysis directory required")
    entries = []
    for n in range(1, a.count + 1):
        folder = BASE / f"same-frame-{n:02d}"
        m = json.loads((folder / "raw/manifest.json").read_bytes())
        if (m.get("finalized") is not True or m["status"]["dropped_chunks"] or
                not m["status"]["coverage"]["passed"] or
                sha(folder / "raw/chunks.jsonl") != m["chunks_sha256"]):
            raise ValueError("Raw metadata is not finalized/consistent")
        entries.append(dict(result=str(folder / "save/result.json"),
            stream_log=str(folder / "raw/chunks.jsonl"), boundary_uncertainty_s=.05))
    spec = dict(schema=1, frame_file=str(BASE / "v60-frame/frame.bin"),
        measurement_setup="Retained v60c RAW frame, same card/wiring, 25 MHz native one-bit SDMMC2, fast-none cached -Os; each SAVE has its own finalized JS raw recording. Explicit 50 ms UTC uncertainty is a conservative analyst assumption, not measured cross-instrument synchronization.",
        runs=entries)
    compared = compare_runs.compare(spec, BASE)
    if len(compared["groups"]) != 1 or len({row["png_bytes"] for row in compared["runs"]}) != 1:
        raise ValueError("Unexpected configuration or encoded-size variation; do not pool")
    a.out.mkdir(parents=True)
    write(a.out / "input-spec.json", spec)
    write(a.out / "comparison.json", compared)
    rows = []
    for index, row in enumerate(compared["runs"], 1):
        folder = BASE / f"same-frame-{index:02d}"
        result = json.loads((folder / "save/result.json").read_bytes())
        report, card = result["report"], result["card"]
        partial = dict(schema=1, frame_sha256=compared["frame_sha256"], runs=[row])
        sliding = energy_sliding.analyze_comparison(partial, (folder / "raw/chunks.jsonl").read_bytes())
        write(a.out / f"same-frame-{index:02d}-sliding.json", sliding)
        bounds = sliding["runs"][0]["fixed_duration_analysis"]
        hz, sd = row["cpu_hz"], row["sd_hz"]
        physical_writes = card["written_sectors"] * 512
        physical_reads = card["read_sectors"] * 512
        write_wire = physical_writes * 8 / sd
        read_wire = physical_reads * 8 / sd
        write_savings = .75 * write_wire
        all_payload_savings = .75 * (write_wire + read_wire)
        rows.append(dict(name=folder.name, file=report["name"], nonce=report["nonce"],
            png_bytes=row["png_bytes"], result_sha256=row["result_sha256"],
            complete_s=row["complete_s"], legacy_total_s=row["total_s"],
            encode_excluding_callback_s=row["encode_excluding_callback_s"],
            callback_s=row["callback_s"], sd_write_s=row["sd_write_s"],
            sd_read_s=card["read_cycles"]/hz, ready_poll_s=card["ready_cycles"]/hz,
            init_s=report["init"]/hz, mount_s=report["mount"]/hz,
            finish_s=report["finish"]/hz, initial_validate_s=report["validate"]/hz,
            postclean_validate_s=row["postclean_validate_s"], cleanup_s=row["cleanup_s"],
            physical_write_bytes=physical_writes, physical_read_bytes=physical_reads,
            physical_write_bytes_per_driver_write_second=physical_writes/row["sd_write_s"],
            png_bytes_per_complete_second=row["png_bytes"]/row["complete_s"],
            host_bracket_duration_s=row["host_bracket_duration_s"],
            host_bracket_energy_bounds_j=row["host_bracket_energy"]["energy_bounds_j"],
            fixed_complete_duration_energy_bounds_j=bounds["energy_bounds_j"],
            fixed_complete_duration_assumed_cpu_hz=hz,
            recording_finalized=sliding["recording_finalized"],
            optimistic_payload_only_four_bit_model=dict(
                clock_hz_unchanged=sd, one_bit_write_payload_s=write_wire,
                one_bit_read_payload_s=read_wire,
                write_payload_savings_s=write_savings,
                all_payload_savings_s=all_payload_savings,
                complete_s_if_only_write_payload_quarters=row["complete_s"]-write_savings,
                complete_s_if_all_payload_quarters=row["complete_s"]-all_payload_savings,
                all_payload_savings_fraction_of_complete=all_payload_savings/row["complete_s"])))
    summary = dict(schema=1, measured_runs=len(rows), frame_sha256=compared["frame_sha256"],
        frame_fnv=compared["frame_fnv"], configuration=compared["groups"][0]["configuration"],
        mode="fast-none", all_recordings_finalized=True, target_save_success=True,
        per_file_host_readback_verified=False, uses_cross_instrument_phase_alignment=False,
        boundary_uncertainty_s=.05, baseline_energy_subtracted=False, rows=rows,
        statistics={key:stats([r[key] for r in rows]) for key in
            ("complete_s", "legacy_total_s", "encode_excluding_callback_s", "callback_s",
             "sd_write_s", "init_s", "postclean_validate_s",
             "physical_write_bytes_per_driver_write_second")},
        energy_median_bounds_j=[statistics.median(r["fixed_complete_duration_energy_bounds_j"][n] for r in rows) for n in (0,1)],
        limitations=[
            "Firmware durations are target DWT counts at reported 400 MHz; host setup/poll/transport delays are separate.",
            "Energy bounds cover every placement of the fixed COMPLETE duration inside the expanded recorded host bracket. No current shape or phase marker selects alignment.",
            "The explicit 50 ms UTC mapping uncertainty is an analyst assumption; observed mapping residuals are checked, not an externally calibrated synchronization guarantee.",
            "No idle baseline is subtracted. These are JS-fed branch energy bounds, not isolated MCU, battery or storage-device energy.",
            "The three repeated SAVE target proofs do not substitute for bytewise host readback of each new file; any later verification is a separate addendum.",
            "Ready polling overlaps write/read/command scopes; it is not additive and is not pure card program time.",
            "Four-bit values are an optimistic payload-only model at unchanged clock and fixed physical sector counts. They are not measured four-bit performance or a strict speed bound; card busy, commands, DMA/CPU service and software changes can alter the result.",
            "Compression, initial/final frame checks, card initialization and other work do not automatically become four times faster.",
            "Only three repeats are planned; ranges are descriptive, not worst-case guarantees."])
    write(a.out / "summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
