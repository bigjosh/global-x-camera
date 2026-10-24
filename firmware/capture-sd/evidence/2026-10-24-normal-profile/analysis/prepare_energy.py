"""Offline strict native-sample energy export for completed final Standby trials.

Run only after the owner confirms all recorders have stopped: hashing raw files
is intentionally substantial disk I/O. This script never controls instruments.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import sys
import phase_timing
from fine_timing import require

ROOT=Path(__file__).resolve().parent
V66C_SECTOR='8129f9cc79e92c678207b4aee838810cc805d0b860c40b2f77b434ae746c8b61'
V66C_PREFIX='247f27c231e0053b7024af29914c6a0cb1b7decb1632ac0d6142a68b89e2da58'


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def distribution(values):
    return {'median':statistics.median(values),'minimum':min(values),'maximum':max(values),'n':len(values)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--tools',type=Path,required=True)
    parser.add_argument('--prior-energy',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--trials',nargs='+',default=['standby02','standby03','standby04'])
    parser.add_argument('--plot-deps',type=Path)
    args=parser.parse_args()
    require(not args.out.exists(),'Output must be new')
    require(len(set(args.trials))==len(args.trials),'Duplicate trial')
    # Require finalized records and independently qualified phase/SBF evidence
    # before reading any large sample files.
    preflight={}
    for name in args.trials:
        source=args.source_root/(name+'-cycle')
        manifest=json.loads((source/'raw/manifest.json').read_text())
        result=json.loads((source/'result.json').read_text())
        require(result['recording_complete'] and manifest['finalized'] and
                manifest['status']['coverage']['passed'] and
                manifest['status']['dropped_chunks']==0,'Invalid raw recording')
        with (source/'raw/chunks.jsonl').open() as index:
            first_chunk=next(json.loads(line) for line in index
                             if json.loads(line).get('event')=='stream_chunk')
        require(first_chunk['sample_rate_hz']==2000000 and first_chunk['decimate_factor']==1,
                'This fixed five-second window recipe requires native 2 MHz samples')
        spec=ROOT/'records'/name/'phase-spec.json';phase=phase_timing.analyze(spec)
        require(phase['completion_kind']=='standby' and phase['standby_flag_observed'] and
                phase['firmware']['sector_sha256']==result['sector_sha256']==V66C_SECTOR and
                phase['firmware']['prefix_sha256']==V66C_PREFIX, 'Final Standby identity differs')
        require(phase==json.loads((spec.parent/'phase-analysis.json').read_text()),
                'Recomputed phase analysis differs from persisted result')
        preflight[name]=(source,manifest,phase,spec)
    args.out.mkdir(parents=True)
    support=args.out/'support';support.mkdir()
    for name in ('cycle_energy.py','cycle_plot.py'):
        shutil.copyfile(args.tools/name,support/name)
    sys.path.insert(0,str(support.resolve()))
    if args.plot_deps:sys.path.insert(0,str(args.plot_deps.resolve()))
    import cycle_energy
    import cycle_plot
    old=json.loads(args.prior_energy.read_text())
    shutil.copyfile(args.prior_energy,args.out/'prior-summary.json')
    criteria=dict(json.loads((args.prior_energy.parent/'records/repeat-01/spec.json').read_text())['criteria'])
    records=[];compacts=[]
    for name,(source,manifest,phase,phase_spec) in preflight.items():
        dest=args.out/'records'/name;dest.mkdir(parents=True)
        context={'schema':1,'trial':name,'terminal_state_qualified':True,
            'qualification':'Fresh exact early-recovery park plus SBF, attributed by owner power/reset history',
            'owner_attestation':json.loads(phase_spec.read_text())['owner_attestation'],
            'sector_sha256':phase['firmware']['sector_sha256'],
            'phase_spec_sha256':sha(phase_spec),'phase_analysis_sha256':sha(phase_spec.parent/'phase-analysis.json'),
            'fresh_sbf_result_sha256':phase['input_sha256']['execution_proof'],
            'image_integrity_verified':False,
            'limits':['The native current-level boundary includes analog settling and is not an exact WFI timestamp.',
                      'SBF/completion and image integrity are separate; file verification is recorded separately.',
                      'JS voltage is measured at IN+; this is measured board-supply branch energy, not isolated MCU or battery energy.',
                      'Saleae and Joulescope clocks are not synchronized; no phase-specific energy is inferred.']}
        dump(dest/'measurement-context.json',context)
        coverage=manifest['status']['coverage']['signals']
        start=max(v['first_sample_id'] for v in coverage.values())+10000000
        end=min(v['last_sample_id_end_exclusive'] for v in coverage.values())
        spec={'criteria':criteria,'cycles':[{'name':name+' (v66c Standby)',
            'start_sample_id':start,'end_sample_id':end,'terminal_state_qualified':True,
            'terminal_evidence':'measurement-context.json'}]}
        dump(dest/'spec.json',spec)
        local=json.loads(json.dumps(spec));local['cycles'][0]['terminal_evidence']=str((dest/'measurement-context.json').resolve())
        result=cycle_energy.analyze(source/'raw',local)
        dump(dest/'analysis.json',result)
        shutil.copyfile(source/'raw/manifest.json',dest/'raw-manifest.json')
        (dest/'raw-chunks.jsonl.gz').write_bytes(gzip.compress((source/'raw/chunks.jsonl').read_bytes(),mtime=0))
        compact=cycle_plot.export(source/'raw',dest/'analysis.json',0)
        cycle_plot.write_compact(dest/'power-compact.json.gz',compact)
        c=result['cycles'][0]
        records.append({'name':name,'compact_file':(dest/'power-compact.json.gz').relative_to(args.out).as_posix(),
            'onset_to_plateau_s':c['onset_to_plateau_s'],'onset_to_plateau_energy_j':c['onset_to_plateau_energy_j'],
            'pretrigger_energy_j':c['pretrigger_energy_j'],'plateau_confirmation_energy_j':c['plateau_confirmation_energy_j'],
            'plateau_mean_current_a':c['plateau']['mean_current_a'],'plateau_mean_power_w':c['plateau']['mean_power_w'],
            'peak_current_a':c['peak_current_a'],'reset_to_pre_wfi_marker_ms':phase['events'][-1]['since_reset_release_ms'],
            'terminal_state_qualified':True,'image_integrity_verified':False})
        compacts.append(compact)
        print(json.dumps({'trial':name,'energy_j':c['onset_to_plateau_energy_j'],'duration_s':c['onset_to_plateau_s']}),flush=True)
    summary={'schema':1,'firmware':'v66c normal Standby','cycles':records,
        'energy_j':distribution([r['onset_to_plateau_energy_j'] for r in records]),
        'current_onset_to_plateau_s':distribution([r['onset_to_plateau_s'] for r in records]),
        'reset_to_pre_wfi_marker_ms':distribution([r['reset_to_pre_wfi_marker_ms'] for r in records]),
        'prior_summary_sha256':sha(args.prior_energy),'same_boundary_criteria':criteria,
        'limits':[f'{len(records)} final trials are included; median/range are descriptive, not population bounds.',
                  'Native-current energy boundaries are distinct from the independently clocked Saleae GPIO markers.',
                  'Observed quiet-tail onset can include analog settling; it is not an exact WFI entry time.',
                  'Measured JS branch energy includes board overhead and omits unmeasured bypass paths; no isolated-MCU or battery conversion is inferred.',
                  'The previous v59 baseline used the same threshold criteria but has signature-only qualification and different frames/firmware.',
                  'Normal-profile timing/check removal and card/image variability are not isolated by this comparison.',
                  'Separate PNG verification records establish image integrity; SBF alone does not inspect pixels.']}
    previous=[c['onset_to_plateau_energy_j'] for c in old['cycles']]
    summary['prior_energy_j']=distribution(previous)
    summary['observed_median_energy_reduction_fraction']=1-summary['energy_j']['median']/statistics.median(previous)
    prior_times=[c['onset_to_plateau_s'] for c in old['cycles']]
    summary['prior_current_onset_to_plateau_s']=distribution(prior_times)
    summary['observed_median_time_reduction_fraction']=1-summary['current_onset_to_plateau_s']['median']/statistics.median(prior_times)
    summary['firmware_sector_sha256']=V66C_SECTOR
    summary['firmware_prefix_sha256']=V66C_PREFIX
    dump(args.out/'summary.json',summary)
    cycle_plot.plot(compacts,args.out/'normal-standby.png')
    cycle_plot.plot(compacts,args.out/'normal-standby.svg')


if __name__=='__main__':main()
