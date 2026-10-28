"""Offline compact power evidence and figures on the JS110 native sample clock.

The compact bins preserve signed integrals and extrema, not within-bin order.
They can reproduce this figure and aggregate energy, but cannot rerun the raw
onset/plateau detector or establish physical rail edges or firmware phase times.
"""
import argparse
import gzip
import json
import math
from pathlib import Path

import numpy as np

from cycle_energy import Archive, sha_file

SIGNALS = ("current", "voltage", "power")
COLUMNS = ["start_sample_id", "end_sample_id", "count"] + [
    f"{signal}_{stat}" for signal in SIGNALS for stat in ("sum", "min", "max")]


def bins(archive, start, end, width, boundaries=()):
    """No decimation-by-picking: every finite sample contributes exactly once."""
    if type(width) is not int or width <= 0 or width % archive.decimation:
        raise ValueError("Bin width must be a positive aligned native-ID interval")
    data = {s: archive.get(s, start, end) for s in SIGNALS}
    if any(not np.isfinite(v).all() for v in data.values()):
        raise ValueError("Nonfinite samples cannot be hidden by compact binning")
    if any(type(b) is not int or (b-start) % archive.decimation
           or not start <= b <= end for b in boundaries):
        raise ValueError("Bin boundary is outside or misaligned")
    edges = sorted(set(range(start, end, width)) | {start, end} | set(boundaries))
    rows = []
    for a, b in zip(edges, edges[1:]):
        lo, hi = (a-start)//archive.decimation, (b-start)//archive.decimation
        row = [a, b, hi-lo]
        for name in SIGNALS:
            block = data[name][lo:hi]
            row.extend([float(block.sum(dtype=np.float64)),
                        float(block.min()), float(block.max())])
        rows.append(row)
    return rows


def integrated(rows, start, end, rate, decimation):
    selected = [r for r in rows if start <= r[0] and r[1] <= end]
    if (not selected or selected[0][0] != start or selected[-1][1] != end
            or any(a[1] != b[0] for a, b in zip(selected, selected[1:]))):
        raise ValueError("Integral boundaries must exactly coincide with covered bins")
    return math.fsum(r[9] for r in selected) * decimation / rate


def export(directory, analysis_path, cycle_index=0, *, bin_s=0.001,
           idle_tail_s=3.0, startup_s=0.002):
    analysis = json.loads(Path(analysis_path).read_text())
    if (analysis.get("schema") != 1 or analysis.get("uses_host_utc_alignment") is not False
            or sha_file(Path(directory)/"manifest.json") != analysis["manifest_sha256"]):
        raise ValueError("Analysis is not bound to this native-clock recording")
    if any(not math.isfinite(v) or v <= 0 for v in (bin_s,idle_tail_s,startup_s)):
        raise ValueError("Positive finite view intervals are required")
    cycle = analysis["cycles"][cycle_index]
    b = cycle["boundaries"]
    with Archive(directory) as archive:
        if (analysis["sample_rate_hz"] != archive.rate
                or analysis["decimate_factor"] != archive.decimation):
            raise ValueError("Analysis sample geometry disagrees with recording")
        origin = b["current_onset_sample_id"]
        start = b["integration_start_sample_id"]
        plateau = b["terminal_plateau_start_sample_id"]
        complete = b["integration_end_sample_id"]
        if not start < origin < plateau < complete <= cycle["window"]["end_sample_id"]:
            raise ValueError("Analysis boundary order differs")
        aligned = lambda seconds: max(1, math.ceil(seconds*archive.rate/archive.decimation))*archive.decimation
        end = min(cycle["window"]["end_sample_id"], max(complete,plateau+aligned(idle_tail_s)))
        rows = bins(archive,start,end,aligned(bin_s),(origin,plateau,complete))
        exact = {}
        segments = (
            ("pretrigger_energy_j",start,origin),
            ("onset_to_plateau_energy_j",origin,plateau),
            ("plateau_confirmation_energy_j",plateau,complete),
            ("pretrigger_through_confirmed_plateau_energy_j",start,complete))
        for name,a,z in segments:
            value=integrated(rows,a,z,archive.rate,archive.decimation)
            if not math.isclose(value,cycle[name],rel_tol=1e-12,abs_tol=1e-12):
                raise ValueError("Raw-bin integral disagrees with selected analysis: "+name)
            exact[name]=value
        startup_end=min(end,origin+aligned(startup_s))
        # At most ~2000 bins, retaining each bin's extrema and signed sum.
        startup_width=max(archive.decimation,
                          math.ceil((startup_end-origin)/2000/archive.decimation)*archive.decimation)
        startup=bins(archive,origin,startup_end,startup_width)
        return dict(
            schema=1,name=cycle.get("name"),sample_rate_hz=archive.rate,
            decimate_factor=archive.decimation,
            analysis_sha256=sha_file(Path(analysis_path)),
            raw_manifest_sha256=analysis["manifest_sha256"],
            raw_chunks_sha256=archive.manifest["chunks_sha256"],
            raw_files=archive.manifest["files"],
            recording_finalized=True,uses_host_utc_alignment=False,
            boundaries=b,cycle_analysis=cycle,columns=COLUMNS,
            nominal_bin_s=aligned(bin_s)/archive.rate,
            view_start_sample_id=start,view_end_sample_id=end,rows=rows,
            startup_rows=startup,exact_segment_integrals_j=exact,
            limits=[
                "Compact sums/min/max preserve aggregate energy and extrema, not within-bin sample order.",
                "Raw onset/plateau classification cannot be rerun from these bins.",
                "Zero time is observed current threshold, not a physical rail edge.",
                "No capture, exposure, encode, or SD-write phase alignment is asserted.",
                "Power is the JS110 measured branch; external debugger/CN8 bypass energy is not included.",
                "Native float samples may reflect instrument autorange suppression; no correction is inferred.",
            ])


def read_compact(path):
    path=Path(path)
    opener=gzip.open if path.suffix==".gz" else open
    with opener(path,"rt",encoding="utf-8") as source:
        return json.load(source)


def write_compact(path, value):
    path=Path(path)
    opener=gzip.open if path.suffix==".gz" else open
    with opener(path,"xt",encoding="utf-8") as target:
        json.dump(value,target,separators=(",",":"),allow_nan=False)
        target.write("\n")


def plot(compacts, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    if not compacts:
        raise ValueError("At least one compact cycle is required")
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,
                         "axes.spines.top":False,"axes.spines.right":False})
    fig,axes=plt.subplots(2,1,figsize=(10,7),gridspec_kw={"height_ratios":[2,1]},
                          constrained_layout=True)
    colors=plt.get_cmap("tab10").colors
    for n,c in enumerate(compacts):
        if c.get("schema")!=1 or c.get("uses_host_utc_alignment") is not False:
            raise ValueError("Unsupported compact figure input")
        color=colors[n%len(colors)]
        rate=c["sample_rate_hz"]
        origin=c["boundaries"]["current_onset_sample_id"]
        r=np.asarray(c["rows"],dtype=np.float64)
        x=((r[:,0]+r[:,1])/2-origin)/rate
        power=r[:,9]/r[:,2]
        label=c["name"] or f"Cycle {n+1}"
        axes[0].plot(x,power,lw=1.2,color=color,label=label)
        plateau=(c["boundaries"]["terminal_plateau_start_sample_id"]-origin)/rate
        axes[0].axvline(plateau,color=color,ls=":",alpha=.7)
        s=np.asarray(c["startup_rows"],dtype=np.float64)
        sx=((s[:,0]+s[:,1])/2-origin)/rate*1e6
        mean=s[:,3]/s[:,2]
        axes[1].plot(sx,mean,lw=1,color=color,label=label)
        axes[1].fill_between(sx,s[:,4],s[:,5],color=color,alpha=.2,linewidth=0)
    ambiguous=any(c["cycle_analysis"].get("completion_boundary_qualified") is False
                  for c in compacts)
    axes[0].set(xlabel="Time from observed current onset (s)",
                ylabel="Mean measured branch power (W)",
                title="Cold-cycle power and observed current levels")
    note=("Dotted lines: selected current-level boundary\n"
          "Current-level onset alone is not completion" if ambiguous else
          "Dotted lines: measured terminal plateau boundary\nNo firmware phase alignment")
    axes[0].text(.99,.98,note,
                 ha="right",va="top",transform=axes[0].transAxes,fontsize=9)
    axes[0].legend(loc="upper left",frameon=False,fontsize=9)
    axes[1].set(xlabel="Time from observed current onset (µs)",
                ylabel="Measured branch current (A)",
                title="Startup inrush: bin means with min/max envelope")
    for ax in axes:
        ax.grid(True,alpha=.18)
    fig.savefig(output,dpi=180)
    plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    e=sub.add_parser("export")
    e.add_argument("--raw",type=Path,required=True)
    e.add_argument("--analysis",type=Path,required=True)
    e.add_argument("--cycle",type=int,default=0)
    e.add_argument("--out",type=Path,required=True)
    p=sub.add_parser("plot")
    p.add_argument("--input",type=Path,nargs="+",required=True)
    p.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    if args.out.exists():
        raise ValueError("Output already exists")
    if args.command=="export":
        write_compact(args.out,export(args.raw,args.analysis,args.cycle))
    else:
        plot([read_compact(path) for path in args.input],args.out)


if __name__=="__main__":
    main()
