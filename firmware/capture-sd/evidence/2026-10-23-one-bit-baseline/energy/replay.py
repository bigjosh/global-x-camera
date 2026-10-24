"""Replay archived native-bin integrals; no hardware or original raw files.

python replay.py --out NEW_DIRECTORY [--figures] [--plot-deps PATH]
NumPy is required; figures also require Matplotlib. The compact bins retain
signed sample sums/extrema, not within-bin ordering: this does not rerun the
raw onset/plateau search. These three records remain signature-only, with no
per-cycle SBF or file-integrity claim.
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--figures",action="store_true")
    parser.add_argument("--plot-deps",type=Path)
    args=parser.parse_args()
    manifest=json.loads((ROOT/"manifest.json").read_text())
    for name,expected in manifest["files"].items():
        path=(ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or digest(path)!=expected:
            raise ValueError("Archive file identity mismatch: "+name)
    sys.path.insert(0,str(ROOT/"support"))
    if args.plot_deps:
        sys.path.insert(0,str(args.plot_deps.resolve()))
    import cycle_plot
    summary=json.loads((ROOT/"summary.json").read_text())
    compacts=[]
    verified=[]
    for row in summary["cycles"]:
        record=ROOT/"records"/row["name"]
        a=json.loads((record/"analysis.json").read_text())
        m=json.loads((record/"raw-manifest.json").read_text())
        c=cycle_plot.read_compact(ROOT/row["compact_file"])
        if (digest(record/"analysis.json")!=c["analysis_sha256"] or
                digest(record/"raw-manifest.json")!=c["raw_manifest_sha256"] or
                hashlib.sha256(gzip.decompress((record/"raw-chunks.jsonl.gz").read_bytes())).hexdigest()!=m["chunks_sha256"] or
                m["files"]!=c["raw_files"] or not m["finalized"] or
                not m["status"]["coverage"]["passed"] or m["status"]["dropped_chunks"]):
            raise ValueError("Compact/source/coverage identity differs")
        original,=a["cycles"]
        if (c["cycle_analysis"]!=original or
                digest(record/"measurement-context.json")!=original["terminal_evidence_sha256"] or
                any(original[key] is not False for key in
                    ("terminal_state_qualified","completion_boundary_qualified",
                     "onset_to_plateau_energy_is_complete_cycle"))):
            raise ValueError("Unexpected evidence or upgraded qualification")
        b=c["boundaries"]
        segments=(
            ("pretrigger_energy_j",b["integration_start_sample_id"],b["current_onset_sample_id"]),
            ("onset_to_plateau_energy_j",b["current_onset_sample_id"],b["terminal_plateau_start_sample_id"]),
            ("plateau_confirmation_energy_j",b["terminal_plateau_start_sample_id"],b["integration_end_sample_id"]),
            ("pretrigger_through_confirmed_plateau_energy_j",b["integration_start_sample_id"],b["integration_end_sample_id"]))
        terms={}
        for name,start,end in segments:
            value=cycle_plot.integrated(c["rows"],start,end,c["sample_rate_hz"],c["decimate_factor"])
            if not math.isclose(value,original[name],rel_tol=1e-12,abs_tol=1e-12):
                raise ValueError("Integral mismatch: "+name)
            terms[name]=value
        for key in ("onset_to_plateau_s","onset_to_plateau_energy_j","pretrigger_energy_j","plateau_confirmation_energy_j"):
            if row[key]!=original[key]:
                raise ValueError("Summary disagrees with original analysis")
        verified.append(dict(name=row["name"],terms=terms,terminal_state_qualified=False))
        compacts.append(c)
    args.out.mkdir(parents=True,exist_ok=False)
    if args.figures:
        cycle_plot.plot(compacts,args.out/"cold-baseline.png")
        cycle_plot.plot(compacts,args.out/"cold-baseline.svg")
    result=dict(schema=1,passed=True,records=len(verified),integral_terms=4*len(verified),
        scope="Compact aggregate replay only; raw detector not rerun; all qualification flags remain false",
        results=verified)
    (args.out/"replay-result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(dict(passed=True,records=len(verified),integral_terms=4*len(verified))))


if __name__=="__main__": main()
