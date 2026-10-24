"""Offline-only compact/figure export after all three JS recordings are closed."""
import hashlib
import json
from pathlib import Path
import statistics
import sys

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
sys.path.insert(0,str(ROOT/"firmware/capture-sd"))
sys.path.insert(0,str(ROOT/"tmp/bringup/plot-deps"))
import cycle_plot


def main():
    runs=[]
    for number in range(1,4):
        folder=BASE/f"repeat-{number:02d}"
        manifest=json.loads((folder/"raw/manifest.json").read_text())
        analysis=json.loads((folder/"analysis.json").read_text())
        if (not manifest["finalized"] or manifest["status"]["dropped_chunks"] or
                not manifest["status"]["coverage"]["passed"]):
            raise ValueError("Incomplete recording: "+str(folder))
        c,=analysis["cycles"]
        if (analysis["sample_rate_hz"]!=2000000 or analysis["decimate_factor"]!=1 or
                analysis["uses_host_utc_alignment"] or c["terminal_state_qualified"] or
                c["completion_boundary_qualified"] or c["onset_to_plateau_energy_is_complete_cycle"]):
            raise ValueError("Unexpected measurement geometry or qualification flags")
        runs.append((folder,analysis,c))
    if any(a["starting_measurement_settings"]!=runs[0][1]["starting_measurement_settings"] for _,a,_ in runs):
        raise ValueError("Starting instrument settings differ; do not pool automatically")
    out=BASE/"cold-baseline-analysis"
    out.mkdir(exist_ok=False)
    records=[]
    compacts=[]
    for folder,analysis,c in runs:
        compact=cycle_plot.export(folder/"raw",folder/"analysis.json",0)
        target=out/(folder.name+"-compact.json.gz")
        cycle_plot.write_compact(target,compact)
        compacts.append(compact)
        records.append(dict(name=folder.name,
            onset_to_plateau_s=c["onset_to_plateau_s"],
            onset_to_plateau_energy_j=c["onset_to_plateau_energy_j"],
            pretrigger_energy_j=c["pretrigger_energy_j"],
            plateau_confirmation_energy_j=c["plateau_confirmation_energy_j"],
            plateau_mean_current_ma=1000*c["plateau"]["mean_current_a"],
            plateau_mean_power_mw=1000*c["plateau"]["mean_power_w"],
            peak_current_a=c["peak_current_a"],minimum_source_voltage_v=c["minimum_source_voltage_v"],
            terminal_state_qualified=False,completion_boundary_qualified=False,
            raw_manifest_sha256=analysis["manifest_sha256"],
            analysis_sha256=hashlib.sha256((folder/"analysis.json").read_bytes()).hexdigest(),
            compact_file=target.name,
            compact_sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    summary=dict(schema=1,recordings=3,
        scope="Observed current-onset to low-current plateau, unchanged-v59 one-bit SD cold-cycle signatures; no individual SBF or saved-file verification is inferred.",
        terminal_state_qualified=False,completion_boundary_qualified=False,
        input_boundary="JS110-fed Nucleo branch; remaining CN8/debugger paths are outside this measurement",
        latest_verified_sector_sha256="7fda9d00cc7ffb3fbb9e6aac6695cf18545754b5dbfce1520cf30b2da39c4e63",
        configuration="One-bit SDMMC2 at 25 MHz / 3.3 V; selected v8b fast-none cached -Os; unchanged v59 flash",
        sample_rate_hz=2000000,uses_host_utc_alignment=False,
        instrument_settings=runs[0][1]["starting_measurement_settings"],cycles=records,
        statistics={key:dict(median=statistics.median(r[key] for r in records),
            minimum=min(r[key] for r in records),maximum=max(r[key] for r in records))
            for key in ("onset_to_plateau_s","onset_to_plateau_energy_j","plateau_mean_current_ma","plateau_mean_power_mw")},
        limitations=[
            "No per-cycle SBF, physical WFI timestamp or file-integrity claim is inferred from current alone.",
            "The plateau boundary may include analog settling and uses 1 ms bins; onset uses a measured-current threshold, not power-good.",
            "Energy excludes the separately reported 1 s plateau confirmation tail; pretrigger and whole-window values remain in each original analysis.",
            "Autorange suppression configuration is preserved; finite delivered samples do not guarantee unsuppressed or perfectly calibrated analog peaks.",
            "Scene differs from October 20; do not interpret the difference as a storage, wiring or power optimization.",
            "Only three fresh recordings; median/min/max are descriptive, not population tail guarantees.",
            "The earlier five-cycle raw recording failed coverage and is excluded, without filling its gap.",
            "Compact bins preserve sample sums/extrema and checked integral terms, but not raw within-bin sample order."])
    (out/"summary.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n")
    cycle_plot.plot(compacts,out/"cold-baseline.png")
    cycle_plot.plot(compacts,out/"cold-baseline.svg")
    print(json.dumps(dict(output=str(out),statistics=summary["statistics"]),indent=2))


if __name__=="__main__": main()
