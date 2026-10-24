"""Offline native-sample analysis; exact instrumented sector is an explicit input.

No hardware imports. Keeps current-level boundaries unqualified even when a
separate later SBF observation exists; no phase-to-JS time alignment is inferred.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT / "firmware/capture-sd"))
sys.path.insert(0, str(ROOT / "tmp/bringup/plot-deps"))
import numpy as np
import cycle_energy
import cycle_plot


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, obj):
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for key in ("record", "build", "out"):
        ap.add_argument("--" + key, type=Path, required=True)
    ap.add_argument("--sector-sha256", required=True)
    ap.add_argument("--sbf-context", type=Path)
    a = ap.parse_args()
    record, build, out = a.record.resolve(), a.build.resolve(), a.out.resolve()
    if out.exists():
        raise ValueError("Output already exists")
    sector = build / "staged/capture_sector_0.bin"
    manifest = json.loads((build / "staged/manifest.json").read_bytes())
    safe = json.loads((record / "safe-start-proof.json").read_bytes())
    expected = a.sector_sha256
    if (len(expected) != 64 or len(sector.read_bytes()) != 65536 or
            sha(sector) != expected or manifest.get("program_sha256") != expected or
            safe.get("sector_sha256") != expected):
        raise ValueError("Explicit expected sector, exact build and safe-start identity disagree")
    if manifest.get("phase_markers", {}).get("pin") != "PD12":
        raise ValueError("Instrumented PD12 build required")
    raw = record / "raw"
    with cycle_energy.Archive(raw) as archive:
        if archive.rate != 2000000 or archive.decimation != 1:
            raise ValueError("Unexpected native sample geometry")
        step = archive.rate // 10
        intervals, start = [], None
        for at in range(archive.start, archive.end - step + 1, step):
            values = archive.get("current", at, at + step)
            quiet = np.isfinite(values).all() and float(np.max(np.abs(values))) < .0001
            if quiet and start is None:
                start = at
            elif not quiet and start is not None:
                if at - start >= 10 * archive.rate:
                    intervals.append((start, at))
                start = None
        if start is not None and archive.end - start >= 10 * archive.rate:
            intervals.append((start, archive.end))
        if len(intervals) != 1:
            raise ValueError("Expected exactly one measured >=10-second off interval")
        begin, end = intervals[0][0] + 2 * archive.rate, archive.end - step
    out.mkdir(parents=True)
    context = dict(schema=1, terminal_state_qualified=False,
        completion_boundary_qualified=False, image_integrity_verified=False,
        scope="Instrumented current/power signature; not an exact completion, WFI or saved-file verification",
        firmware_sector_sha256=expected,
        build_manifest_sha256=sha(build / "staged/manifest.json"),
        safe_start_proof_sha256=sha(record / "safe-start-proof.json"),
        raw_manifest_sha256=sha(raw / "manifest.json"),
        cycle_log_sha256=sha(record / "cycle.jsonl"),
        original_phase_summary_sha256=sha(record / "phase-summary.json"),
        phase_width_qualified=False, uses_host_utc_alignment=False,
        bench_owner="root", note="No debugger/UART command occurs in the recording runner; later evidence is separate.")
    if a.sbf_context:
        sbf = json.loads(a.sbf_context.read_bytes())
        context["later_sbf_observation"] = dict(path=str(a.sbf_context.resolve()),
            sha256=sha(a.sbf_context), passed=sbf.get("passed"), sbf=sbf.get("sbf"),
            trial_entry_proven=sbf.get("trial_entry_proven"),
            scope="Separate later observation; does not qualify the selected JS current boundary or image integrity")
    write(out / "measurement-context.json", context)
    criteria = dict(bin_s=.001, off_baseline_s=.5, off_abs_max_a=.0001, onset_a=.12,
        pretrigger_s=.1, plateau_min_s=1.0, plateau_mean_min_a=.007,
        plateau_mean_max_a=.01, plateau_peak_abs_max_a=.0105,
        plateau_mean_span_a=.002, current_valid_abs_max_a=9.5)
    spec = dict(criteria=criteria, cycles=[dict(name=record.name + " (instrumented; unverified boundary)",
        start_sample_id=begin, end_sample_id=end, terminal_state_qualified=False,
        terminal_evidence=str(out / "measurement-context.json"))])
    write(out / "spec.json", spec)
    analysis = cycle_energy.analyze(raw, spec, allow_unqualified_plateau=True)
    write(out / "analysis.json", analysis)
    compact = cycle_plot.export(raw, out / "analysis.json", 0)
    cycle_plot.write_compact(out / "compact.json.gz", compact)
    c, = analysis["cycles"]
    assert not c["terminal_state_qualified"] and not c["completion_boundary_qualified"]
    assert not c["onset_to_plateau_energy_is_complete_cycle"]
    summary = dict(schema=1, recording=record.name, firmware_sector_sha256=expected,
        configuration="Instrumented PD12 build; native one-bit SDMMC2, not pooled with unchanged-v59 baseline",
        input_boundary="JS110-fed branch; remaining CN8/debugger bypass paths are outside this measurement",
        terminal_state_qualified=False, completion_boundary_qualified=False,
        image_integrity_verified=False, phase_width_qualified=False,
        sample_rate_hz=analysis["sample_rate_hz"], uses_host_utc_alignment=False,
        onset_to_plateau_s=c["onset_to_plateau_s"], onset_to_plateau_energy_j=c["onset_to_plateau_energy_j"],
        pretrigger_energy_j=c["pretrigger_energy_j"],
        plateau_confirmation_energy_j=c["plateau_confirmation_energy_j"],
        plateau_mean_current_ma=1000*c["plateau"]["mean_current_a"],
        plateau_mean_power_mw=1000*c["plateau"]["mean_power_w"],
        peak_current_a=c["peak_current_a"], minimum_source_voltage_v=c["minimum_source_voltage_v"],
        raw_manifest_sha256=sha(raw / "manifest.json"), analysis_sha256=sha(out / "analysis.json"),
        compact_sha256=sha(out / "compact.json.gz"),
        limitations=["Only one instrumented trial; do not attribute differences from unchanged v59 to marker overhead.",
            "Current onset is not physical power-good; the 1 ms selected plateau boundary includes possible analog settling.",
            "Energy excludes the separately reported 1 s confirmation tail; no current-level boundary is asserted to be exact WFI.",
            "Finite native delivered samples retain the instrument range/suppression behavior; peaks are not independently analog-qualified.",
            "Saleae and JS clocks are not synchronized; no phase-specific energy is inferred from host UTC or aligned curve shapes.",
            "The failed strict pulse-width decode remains preserved; ordered edges, if separately qualified, are a different timing analysis."])
    write(out / "summary.json", summary)
    cycle_plot.plot([compact], out / "power.png")
    cycle_plot.plot([compact], out / "power.svg")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
