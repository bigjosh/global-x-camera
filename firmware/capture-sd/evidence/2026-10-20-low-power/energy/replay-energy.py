"""Replay archived compact energy/figures; raw onset search is NOT replayed."""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--figures",action="store_true")
    a=p.parse_args()
    root=a.archive.resolve()
    sys.path.insert(0,str(root/"support/firmware/capture-sd"))
    from cycle_plot import read_compact,integrated,plot,COLUMNS
    cases=[("baseline","baseline","compact-qualified-scope.json.gz",0)]
    cases += [("standby","v59",f"compact-cycle-{i+1}.json.gz",i) for i in range(3)]
    compacts=[]
    verified=[]
    for folder,raw_folder,filename,index in cases:
        directory=root/"energy"/folder
        compact_path=directory/filename
        c=read_compact(compact_path)
        analysis_path=directory/"analysis.json"
        analysis=json.loads(analysis_path.read_text())
        manifest_path=root/"energy/raw-metadata"/raw_folder/"manifest.json"
        manifest=json.loads(manifest_path.read_text())
        chunk_path=manifest_path.parent/"chunks.jsonl.gz"
        h=hashlib.sha256()
        with gzip.open(chunk_path,"rb") as chunks:
            for block in iter(lambda:chunks.read(1024**2),b""):
                h.update(block)
        if (c["schema"]!=1 or c["columns"]!=COLUMNS
                or c["uses_host_utc_alignment"] is not False
                or c["analysis_sha256"]!=sha(analysis_path)
                or c["raw_manifest_sha256"]!=sha(manifest_path)
                or c["raw_chunks_sha256"]!=h.hexdigest()
                or c["raw_chunks_sha256"]!=manifest["chunks_sha256"]
                or c["raw_files"]!=manifest["files"]
                or c["cycle_analysis"]!=analysis["cycles"][index]
                or c["sample_rate_hz"]!=analysis["sample_rate_hz"]
                or c["decimate_factor"]!=analysis["decimate_factor"]):
            raise ValueError("Compact provenance or geometry differs: "+filename)
        rows=c["rows"]
        next_id=c["view_start_sample_id"]
        for row in rows:
            if (len(row)!=12 or row[0]!=next_id or type(row[2]) is not int
                    or row[2]<=0 or row[1]-row[0]!=row[2]*c["decimate_factor"]
                    or any(not math.isfinite(v) for v in row)):
                raise ValueError("Invalid compact coverage")
            for column in (3,6,9):
                mean=row[column]/row[2]
                if not row[column+1]-1e-12<=mean<=row[column+2]+1e-12:
                    raise ValueError("Invalid compact extrema")
            next_id=row[1]
        if next_id!=c["view_end_sample_id"]:
            raise ValueError("Compact coverage is incomplete")
        b=c["boundaries"]
        start,onset,plateau,end=(b[k] for k in (
            "integration_start_sample_id","current_onset_sample_id",
            "terminal_plateau_start_sample_id","integration_end_sample_id"))
        intervals=(("pretrigger_energy_j",start,onset),
                   ("onset_to_plateau_energy_j",onset,plateau),
                   ("plateau_confirmation_energy_j",plateau,end),
                   ("pretrigger_through_confirmed_plateau_energy_j",start,end))
        sums={}
        for name,lo,hi in intervals:
            value=integrated(rows,lo,hi,c["sample_rate_hz"],c["decimate_factor"])
            if (not math.isclose(value,c["exact_segment_integrals_j"][name],rel_tol=1e-12,abs_tol=1e-12)
                    or not math.isclose(value,c["cycle_analysis"][name],rel_tol=1e-12,abs_tol=1e-12)):
                raise ValueError("Compact integral differs: "+name)
            sums[name]=value
        verified.append(dict(name=c["name"],compact_sha256=sha(compact_path),
                             completion_boundary_qualified=c["cycle_analysis"].get(
                                 "completion_boundary_qualified",True),integrals_j=sums))
        compacts.append(c)
    a.out.mkdir(parents=True,exist_ok=False)
    result=dict(verified_cycles=verified,raw_detector_replayed=False,
                limits="Only compact aggregate sums/figures replayed. Original raw samples remain local; v50 current-level onset is not a complete-save boundary.")
    (a.out/"aggregate-replay.json").write_text(json.dumps(result,indent=2)+"\n")
    if a.figures:
        plot(compacts,a.out/"cold-cycle-comparison.png")
        plot(compacts,a.out/"cold-cycle-comparison.svg")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
