"""Replay compact native-sample energy arithmetic using only the standard library.

This verifies selected interval sums, boundaries and medians. It cannot rerun
the original raw onset/plateau detector or recover within-bin sample order.
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def need(value,message):
    if not value:raise ValueError(message)
def integral(rows,start,end,rate):
    selected=[r for r in rows if start<=r[0] and r[1]<=end]
    need(selected and selected[0][0]==start and selected[-1][1]==end and
        all(a[1]==b[0] for a,b in zip(selected,selected[1:])), 'Missing exact integral coverage')
    return math.fsum(r[9] for r in selected)/rate
def replay(folder):
    folder=Path(folder).resolve();manifest=read(folder/'manifest.json')
    for name,digest in manifest['files'].items():
        p=(folder/name).resolve()
        need(p.is_relative_to(folder) and sha(p)==digest,'Artifact hash mismatch: '+name)
    summary=read(folder/'energy-summary.json');result=[]
    segments=(('pretrigger_energy_j','integration_start_sample_id','current_onset_sample_id'),
        ('onset_to_plateau_energy_j','current_onset_sample_id','terminal_plateau_start_sample_id'),
        ('plateau_confirmation_energy_j','terminal_plateau_start_sample_id','integration_end_sample_id'),
        ('pretrigger_through_confirmed_plateau_energy_j','integration_start_sample_id','integration_end_sample_id'))
    for row in summary['cycles']:
        directory=folder/row['name'];analysis=read(directory/'analysis.json')
        with gzip.open(directory/'power-compact.json.gz','rt',encoding='utf-8') as f:c=json.load(f)
        raw=read(directory/'raw-manifest.json');e=analysis['cycles'][0]
        need(c['analysis_sha256']==sha(directory/'analysis.json') and
            c['raw_manifest_sha256']==sha(directory/'raw-manifest.json') and
            c['raw_files']==raw['files'] and c['raw_chunks_sha256']==raw['chunks_sha256'] and
            e['terminal_evidence_sha256']==sha(directory/'qualification-context.json') and
            c['cycle_analysis']==e and raw['status']['coverage']['passed'] and raw['finalized'], 'Binding differs')
        need(c['sample_rate_hz']==2000000 and c['decimate_factor']==1 and
            c['uses_host_utc_alignment'] is False,'Native timeline differs')
        rows=c['rows'];b=c['boundaries'];terms={}
        need(all(len(x)==12 and x[2]==x[1]-x[0] and x[2]>0 and all(math.isfinite(v) for v in x) for x in rows),
            'Nonfinite/invalid compact row')
        need(all(x[1]==y[0] for x,y in zip(rows,rows[1:])),'Compact gap or overlap')
        for key,start,end in segments:
            value=integral(rows,b[start],b[end],c['sample_rate_hz'])
            need(math.isclose(value,e[key],abs_tol=1e-12,rel_tol=1e-12) and
                math.isclose(value,c['exact_segment_integrals_j'][key],abs_tol=1e-12,rel_tol=1e-12) and
                math.isclose(value,row[key],abs_tol=1e-12,rel_tol=1e-12),'Energy integral differs: '+key)
            terms[key]=value
        seconds=(b['terminal_plateau_start_sample_id']-b['current_onset_sample_id'])/c['sample_rate_hz']
        need(math.isclose(seconds,row['current_onset_to_plateau_s'],abs_tol=1e-12,rel_tol=1e-12), 'Duration differs')
        need(e['criteria']==summary['same_boundary_criteria'],'Threshold criteria differ')
        result.append(dict(name=row['name'],seconds=seconds,integrals_j=terms))
    for name,field in (('cycle_s','current_onset_to_plateau_s'),('energy_j','onset_to_plateau_energy_j')):
        values=[r[field] for r in summary['cycles']]
        need(summary['summary'][name]==dict(n=len(values),minimum=min(values),median=statistics.median(values),maximum=max(values)),
            'Aggregate differs')
    return dict(passed=True,cycles=len(result),replayed_intervals=len(result)*4,results=result,
        limits='Selected arithmetic only; raw boundary detection, calibration, pixel equality and SBF history are not replayed')
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--folder',type=Path,default=Path(__file__).parent)
    a=p.parse_args();print(json.dumps(replay(a.folder),indent=2))
if __name__=='__main__':main()
