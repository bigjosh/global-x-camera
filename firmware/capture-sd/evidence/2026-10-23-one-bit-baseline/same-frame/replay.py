"""Offline replay of target proofs and conditional energy; no device imports."""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def same(a, b, label):
    if not math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError("Replay disagreement: " + label)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    manifest = json.loads((ROOT / "manifest.json").read_bytes())
    for name, expected in manifest["files"].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or sha(path.read_bytes()) != expected:
            raise ValueError("Archive hash mismatch: " + name)
    sys.path.insert(0, str(ROOT / "support"))
    import compare_runs
    import energy
    import energy_sliding
    summary = json.loads((ROOT / "summary.json").read_bytes())
    comparison = json.loads((ROOT / "comparison.json").read_bytes())
    if (summary["measured_runs"] != 3 or len(comparison["runs"]) != 3 or
            summary["per_file_host_readback_verified"] is not False or
            summary["uses_cross_instrument_phase_alignment"] is not False or
            summary["baseline_energy_subtracted"] is not False or
            comparison["frame_sha256"] != summary["frame_sha256"] or
            comparison["frame_fnv"] != summary["frame_fnv"]):
        raise ValueError("Scope or frame identity differs")
    verified, nonces = [], set()
    for index, (row, old) in enumerate(zip(summary["rows"], comparison["runs"]), 1):
        record = ROOT / "records" / row["name"]
        raw = (record / "save/result.json").read_bytes()
        result = json.loads(raw)
        report, policy = compare_runs.validate_save(result, summary["frame_fnv"])
        if (sha(raw) != row["result_sha256"] or sha(raw) != old["result_sha256"] or
                result["module_sha256"] != summary["configuration"]["module_sha256"] or
                report["nonce"] in nonces):
            raise ValueError("SAVE identity differs or duplicate nonce")
        nonces.add(report["nonce"])
        for key, value in summary["configuration"]["card_identity"].items():
            if result["card"][key] != value:
                raise ValueError("Card identity differs")
        if policy != old["cache_evidence"]:
            raise ValueError("Cache policy differs")
        for output, source in (("complete_s", "complete"), ("legacy_total_s", "total"),
                ("callback_s", "callback"), ("postclean_validate_s", "postclean_validate")):
            same(report[source] / report["cpu_hz"], row[output], output)
        window, duration = compare_runs.host_window(result, summary["boundary_uncertainty_s"])
        for key in window:
            if window[key] != old["host_window"][key]:
                raise ValueError("Recorded host interval differs")
        same(duration, row["host_bracket_duration_s"], "host duration")
        stream = gzip.decompress((record / "raw-chunks.jsonl.gz").read_bytes())
        raw_manifest = json.loads((record / "raw-manifest.json").read_bytes())
        if (sha(stream) != raw_manifest["chunks_sha256"] or
                raw_manifest["finalized"] is not True or
                raw_manifest["status"]["dropped_chunks"] or
                not raw_manifest["status"]["coverage"]["passed"]):
            raise ValueError("Raw metadata differs or incomplete")
        records = [json.loads(line) for line in stream.decode("utf-8").splitlines()]
        measured = energy.analyze(records, old["host_window"])
        if not measured["recording_finalized"]:
            raise ValueError("Unfinalized energy log")
        partial = dict(schema=1, frame_sha256=summary["frame_sha256"], runs=[old])
        replayed = energy_sliding.analyze_comparison(partial, stream)
        bounded = replayed["runs"][0]["fixed_duration_analysis"]
        saved = json.loads((ROOT / f"same-frame-{index:02d}-sliding.json").read_bytes())
        for a, b in zip(measured["energy_bounds_j"], row["host_bracket_energy_bounds_j"]):
            same(a, b, "host energy")
        for key in ("fixed_duration_s", "energy_bounds_j"):
            if bounded[key] != saved["runs"][0]["fixed_duration_analysis"][key]:
                raise ValueError("Fixed-duration replay differs")
        for a, b in zip(bounded["energy_bounds_j"], row["fixed_complete_duration_energy_bounds_j"]):
            same(a, b, "fixed-duration energy")
        card = result["card"]
        writes, reads = card["written_sectors"]*512, card["read_sectors"]*512
        write_s = card["write_cycles"] / report["cpu_hz"]
        same(write_s, row["sd_write_s"], "driver write time")
        same(writes/write_s, row["physical_write_bytes_per_driver_write_second"], "write throughput")
        model = row["optimistic_payload_only_four_bit_model"]
        saving = .75 * (writes+reads) * 8 / report["sd_hz"]
        same(saving, model["all_payload_savings_s"], "four-bit payload arithmetic")
        same(row["complete_s"]-saving, model["complete_s_if_all_payload_quarters"], "modeled duration")
        verified.append(dict(name=row["name"], complete_s=row["complete_s"],
            conditional_energy_bounds_j=bounded["energy_bounds_j"],
            payload_only_modeled_savings_s=saving))
    for n in (0, 1):
        same(statistics.median(row["conditional_energy_bounds_j"][n] for row in verified),
             summary["energy_median_bounds_j"][n], "median energy bound")
    addendum = json.loads((ROOT / "verification-addendum.json").read_bytes())
    if (addendum["original_summary_sha256"] != sha((ROOT / "summary.json").read_bytes()) or
            addendum["all_three_host_readbacks_verified"] is not True or
            len(addendum["rows"]) != 3):
        raise ValueError("Readback addendum does not bind the original summary")
    png_hashes = set()
    for row, link in zip(summary["rows"], addendum["rows"]):
        evidence = (ROOT / link["verification_file"]).read_bytes()
        v = json.loads(evidence)
        if (sha(evidence) != link["verification_source_sha256"] or
                link["save_result_sha256"] != row["result_sha256"] or
                link["file"] != row["file"] or
                v["bytes"] != row["png_bytes"] or
                v["sha256"] != link["png_sha256"] or
                v["frame_sha256"] != summary["frame_sha256"] or
                v["all_png_chunk_crcs_valid"] is not True or
                v["exact_pixels_sample_shift_left_6"] is not True or
                v["pixels"] != 1120*1364 or v["sBIT"] != 10):
            raise ValueError("File verification evidence differs")
        png_hashes.add(v["sha256"])
    if len(png_hashes) != 1:
        raise ValueError("Repeated files are not byte-identical")
    args.out.mkdir(parents=True, exist_ok=False)
    result = dict(schema=1, passed=True, runs=3, hashes_verified=len(manifest["files"]),
        private_frame_hash_recomputed=False, image_payloads_present=False,
        later_readback_records_verified=3,
        energy_alignment="all feasible placements; not synchronized", results=verified)
    (args.out / "replay-result.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
