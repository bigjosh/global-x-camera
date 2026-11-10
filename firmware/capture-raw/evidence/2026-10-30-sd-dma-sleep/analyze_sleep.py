"""Offline comparison of completed single-frame cold cycles: polling vs WFI.

Never imports instrument controllers or issues hardware commands. Both groups
must retain all eleven single-frame markers. Timing comes from JS sample IDs,
not DWT CYCCNT, whose progress in shallow sleep is deliberately not assumed.

Manifest: [{"run":"baseline01","variant":"poll","trace":"..."}, ...].
An item may supply "analysis" instead of "trace" to summarize an existing
qualified single-frame analysis (useful for offline replay only).
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[4]
PRIOR = ROOT / "tmp/bringup/sensor-autostop-promote-20261028/analysis/analyze_promotion.py"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked_row(item, result, analysis_path):
    if item["variant"] not in ("poll", "sleep"):
        raise ValueError("variant must be poll or sleep")
    required = (
        "unique_marker_train", "marker_precedence_pass", "all_expected_markers_observed",
        "single_external_exposure_envelope_observed", "exposure_envelopes_end_before_frame_IRQ",
        "no_external_exposure_edges_between_standby_observed_and_commit",
    )
    if not all(result.get(key) is True for key in required):
        raise ValueError("Single-frame marker/exposure qualification failed")
    markers = {entry["id"]: entry for entry in result["marker_events"]}
    if set(markers) != set(range(1, 12)) or len(result["marker_events"]) != 11:
        raise ValueError("Both variants require eleven single-frame markers")
    phase = result["autostop_phase_windows_overlapping_not_additive"]
    transport = phase["slot_transport"]
    energy = result["post5ms_to_plateau"]
    if not transport["finite"] or not energy["finite"]:
        raise ValueError("Non-finite scoped power data")
    for check in result["checks"].values():
        if not check["hash_passed"] or not check["contiguous"]:
            raise ValueError("Signal integrity/hash qualification failed")
    return dict(
        run=item["run"], variant=item["variant"],
        analysis=str(analysis_path), analysis_sha256=sha(analysis_path),
        first_exposure_ms=markers[2]["time_ms"],
        frame_complete_ms=markers[3]["time_ms"],
        sensor_standby_observed_ms=markers[11]["time_ms"],
        SD_init_ms=phase["SD_initialization"]["duration_ms"],
        scan_preparation_ms=phase["SCR_scan_write_preparation"]["duration_ms"],
        slot_transport_wall_ms=transport["duration_ms"],
        slot_transport_mean_mA=transport["current_mean_mA"],
        slot_transport_mean_mW=transport["power_mean"] * 1000,
        slot_transport_energy_mJ=transport["energy_mJ"],
        post5ms_energy_mJ=energy["energy_mJ"],
        onset_to_low_plateau_ms=result["whole_cycle_raw_unqualified"]["duration_ms"],
        peak1ms_mean_mA=result["peaks_1ms"][0]["current_mean_mA"],
        low_plateau_mA=result["low_plateau_100ms"]["current_mean_mA"],
        mean_input_V=energy["voltage_mean"],
        evidence=item.get("evidence", {}),
    )


def summarize(rows):
    metrics = [key for key, value in rows[0].items() if isinstance(value, (int, float))]
    groups = {}
    for variant in ("poll", "sleep"):
        selected = [row for row in rows if row["variant"] == variant]
        if not selected:
            continue
        groups[variant] = dict(count=len(selected), statistics={
            key: dict(mean=statistics.mean(row[key] for row in selected),
                      median=statistics.median(row[key] for row in selected),
                      minimum=min(row[key] for row in selected),
                      maximum=max(row[key] for row in selected))
            for key in metrics})
    comparison = None
    if len(groups) == 2:
        a, b = groups["poll"]["statistics"], groups["sleep"]["statistics"]
        comparison = {key: dict(poll_median=a[key]["median"], sleep_median=b[key]["median"],
                               sleep_minus_poll=b[key]["median"] - a[key]["median"],
                               reduction_percent=(100 * (1-b[key]["median"]/a[key]["median"]))
                               if a[key]["median"] else None) for key in metrics}
    return dict(rows=rows, groups=groups, comparison=comparison,
                timing_source="Joulescope native sample IDs and GPIO phase markers; no DWT-to-wall conversion",
                scope="Whole-board, post-first5ms cold-cycle comparison. No image-integrity, exact sleep residency, or physical Standby claim follows from these signals alone.",
                qualifications=[
                    "Both variants retain single-frame capture, Ethernet power-down and the same SD clock/card/wiring.",
                    "Report SD transport average power beside elapsed time and energy: variable card latency and growing header scan can confound whole-cycle totals.",
                    "First5ms/inrush and instantaneous extrema remain unqualified; no LTC/battery losses are included.",
                    "Counter evidence, original-frame/full-SD equality, error-timeout behavior and UART recovery are independent required checks.",
                    "DWT cycle counts may exclude CPU sleep and must not silently be called elapsed milliseconds.",
                ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    items = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    if not items or len({item["run"] for item in items}) != len(items):
        raise ValueError("Empty manifest or repeated run name")
    module = None
    rows = []
    for item in items:
        if "analysis" in item:
            path = Path(item["analysis"]).resolve()
            result = json.loads(path.read_text())
        else:
            if module is None:
                spec = importlib.util.spec_from_file_location("sleep_prior_analysis", PRIOR)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                for obj in (module, module.prior, module.prior.normal):
                    obj.HERE = args.out.resolve()
                    obj.CAMPAIGN = args.out.parent.resolve()
            analysis_item = dict(item, group="autostop", trace=str(Path(item["trace"]).resolve()))
            result = module.analyze(analysis_item)
            path = args.out / (item["run"] + "-analysis.json")
        rows.append(checked_row(item, result, path))
    output = summarize(rows)
    output["source_sha256"] = sha(__file__)
    output["prior_analysis_sha256"] = sha(PRIOR)
    output["manifest_sha256"] = sha(args.manifest)
    (args.out / "comparison.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
