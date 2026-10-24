"""Replay compact native energy integrals; never reads raw GB streams or devices."""
import gzip
import hashlib
import json
import math
import statistics
from pathlib import Path
import sys
import phase_timing
from fine_timing import require


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replay(folder):
    folder=Path(folder).resolve()
    manifest=json.loads((folder/'manifest.json').read_text())
    for name,sha in manifest['files'].items():
        path=(folder/name).resolve()
        require(path.is_relative_to(folder) and digest(path)==sha,'Energy archive identity: '+name)
    sys.path.insert(0,str(folder/'support'))
    import cycle_plot
    summary=json.loads((folder/'summary.json').read_text())
    prior=json.loads((folder/'prior-summary.json').read_text())
    require(digest(folder/'prior-summary.json')==summary['prior_summary_sha256'], 'Prior summary differs')
    results=[]
    for row in summary['cycles']:
        record=folder/'records'/row['name']
        source=json.loads((record/'analysis.json').read_text())
        raw=json.loads((record/'raw-manifest.json').read_text())
        context=json.loads((record/'measurement-context.json').read_text())
        compact=cycle_plot.read_compact(folder/row['compact_file'])
        original,=source['cycles']
        require(digest(record/'analysis.json')==compact['analysis_sha256'] and
            digest(record/'raw-manifest.json')==compact['raw_manifest_sha256'] and
            hashlib.sha256(gzip.decompress((record/'raw-chunks.jsonl.gz').read_bytes())).hexdigest()==raw['chunks_sha256'] and
            raw['files']==compact['raw_files'] and raw['finalized'] and
            raw['status']['coverage']['passed'] and raw['status']['dropped_chunks']==0,
            'Raw identities or coverage disagree')
        require(original==compact['cycle_analysis'] and original['terminal_state_qualified'] is True and
            context['terminal_state_qualified'] is True and
            digest(record/'measurement-context.json')==original['terminal_evidence_sha256'],
            'Terminal attestation differs')
        phase_spec=folder.parent/'records'/row['name']/'phase-spec.json'
        phase=phase_timing.analyze(phase_spec)
        require(digest(phase_spec)==context['phase_spec_sha256'] and
            digest(phase_spec.parent/'phase-analysis.json')==context['phase_analysis_sha256'] and
            phase['input_sha256']['execution_proof']==context['fresh_sbf_result_sha256'] and
            phase['firmware']['sector_sha256']==context['sector_sha256'] and phase['standby_flag_observed'],
            'Qualified phase/SBF identity differs')
        boundaries=compact['boundaries']
        segments=[('pretrigger_energy_j','integration_start_sample_id','current_onset_sample_id'),
            ('onset_to_plateau_energy_j','current_onset_sample_id','terminal_plateau_start_sample_id'),
            ('plateau_confirmation_energy_j','terminal_plateau_start_sample_id','integration_end_sample_id'),
            ('pretrigger_through_confirmed_plateau_energy_j','integration_start_sample_id','integration_end_sample_id')]
        terms={}
        for key,a,b in segments:
            value=cycle_plot.integrated(compact['rows'],boundaries[a],boundaries[b],
                compact['sample_rate_hz'],compact['decimate_factor'])
            require(math.isclose(value,original[key],rel_tol=1e-12,abs_tol=1e-12),'Compact integral differs: '+key)
            terms[key]=value
        for key in ('onset_to_plateau_energy_j','onset_to_plateau_s','pretrigger_energy_j','plateau_confirmation_energy_j'):
            require(row[key]==original[key],'Summary value differs: '+key)
        results.append({'name':row['name'],'terms':terms,'terminal_state_qualified':True,
                        'qualification_basis':'Historical SBF plus separately recorded owner reset/power history'})
    def distribution(values):
        return {'median':statistics.median(values),'minimum':min(values),'maximum':max(values),'n':len(values)}
    for field,key in [('energy_j','onset_to_plateau_energy_j'),
                      ('current_onset_to_plateau_s','onset_to_plateau_s'),
                      ('reset_to_pre_wfi_marker_ms','reset_to_pre_wfi_marker_ms')]:
        require(summary[field]==distribution([r[key] for r in summary['cycles']]), 'Aggregate differs: '+field)
    for field,key in [('prior_energy_j','onset_to_plateau_energy_j'),
                      ('prior_current_onset_to_plateau_s','onset_to_plateau_s')]:
        require(summary[field]==distribution([r[key] for r in prior['cycles']]), 'Prior aggregate differs')
    require(summary['observed_median_energy_reduction_fraction']==1-summary['energy_j']['median']/summary['prior_energy_j']['median'] and
            summary['observed_median_time_reduction_fraction']==1-summary['current_onset_to_plateau_s']['median']/summary['prior_current_onset_to_plateau_s']['median'],
            'Descriptive comparison ratio differs')
    return {'schema':1,'passed':True,'records':len(results),'integral_terms':4*len(results),'results':results,
        'limits':['Compact aggregate replay preserves integrals but cannot rerun raw onset/plateau detection or within-bin sample ordering.',
                  'Original SBF reader trial_entry_proven=false is preserved; trial attribution is the separate owner-history attestation.',
                  'No exact WFI timestamp, isolated MCU/battery energy, image pixel replay or cross-instrument synchronization is inferred.']}
