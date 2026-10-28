"""Offline promotion analysis; imports signal decoders, never bench controllers.

Manifest items: run, group (normal/autostop), trace, optional evidence. All trace
paths are resolved against this campaign. Only completed recorder outputs are
accepted. Outputs stay in this analysis folder; the prior campaign is untouched.
"""
from pathlib import Path
import argparse,importlib.util,json
import numpy as np

HERE=Path(__file__).resolve().parent
CAMPAIGN=HERE.parent
PREVIOUS=CAMPAIGN.parent/'sensor-autostop-20261028/analysis/analyze_cold.py'
spec=importlib.util.spec_from_file_location('promotion_prior_offline_decoder',PREVIOUS)
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
# Redirect only this interpreter's output globals. No previous files change.
prior.HERE=HERE;prior.CAMPAIGN=CAMPAIGN
prior.normal.HERE=HERE;prior.normal.CAMPAIGN=CAMPAIGN
FS=prior.FS;load=prior.load;metrics=prior.metrics;sha=prior.sha

def analyze(item):
    item=dict(item);trace=Path(item['trace'])
    if not trace.is_absolute():trace=CAMPAIGN/trace
    done=json.loads((trace/'result.json').read_text())
    assert done['success'] and not done['errors'] and not done['cleanup_errors']
    item['trace']=str(trace.resolve());r=prior.analyze(item)
    r['promotion_analysis_source']={str(Path(__file__).resolve()):sha(Path(__file__).resolve()),str(PREVIOUS):sha(PREVIOUS)}
    m={e['id']:e for e in r['marker_events']}
    r['receiver_entry_to_first_strobe_ms']=m[2]['time_ms']-m[1]['time_ms']
    r['all_expected_markers_observed']=len(m)==(11 if item['group']=='autostop' else 10)
    if item['group']=='autostop':
        e=r['external_strobe']
        observed=[pulse for pulse in e['pulses'] if pulse['rise_sample_id']<m[8]['sample_id']]
        assert all(pulse['fall_sample_id']<m[8]['sample_id'] for pulse in observed)
        e['qualified_exposure_pulses']=observed
        e['qualified_observation_end_sample_id']=m[8]['sample_id']
        e['post_commit_envelopes_before_pre_Standby']=[pulse for pulse in e['pulses'] if pulse not in observed]
        e['continuity_end_sample_id']=e['window_end_sample_id']
        e['window_end_sample_id']=m[8]['sample_id']
        e['pulses']=observed;e['complete_pulses']=len(observed)
        e['scope']='PD0 exposure IRQ envelopes qualified from explicit post-entry LOW through commit8, following the stable sensor check. PD0 remains driven LOW through10, but IRQs are disabled after8/9 during shutdown, so that final LOW is continuity only, not continuing sensor monitoring.'
        r['single_external_exposure_envelope_observed']=(len(observed)==1)
        r['exposure_envelopes_end_before_frame_IRQ']=all(pulse['fall_sample_id']<m[3]['sample_id'] for pulse in observed)
        r['no_external_exposure_edges_between_standby_observed_and_commit']=all(pulse['fall_sample_id']<m[11]['sample_id'] for pulse in observed)
        r['external_exposure_proof_scope']='PD0 mirrors PA0 STROBE interrupts. Explicit post-entry LOW excludes startup chatter; exposure counts are qualified through commit8 and the stable sensor check. This independently records the IRQ signal, not a directly probed sensor pin. Counter/FSM/zero-STOP proof and full image readback are separate required records.'
    r['cold_scope']='Cold start from measured current onset through low-current plateau. All currents include the full powered board. Marker10 plus low current does not independently prove fresh SBF, a particular saved slot or image integrity.'
    (HERE/(item['run']+'-analysis.json')).write_text(json.dumps(r,indent=2)+'\n')
    return r

def summarize(reports):
    rows=[]
    for r in reports:
        ph=r['autostop_phase_windows_overlapping_not_additive']
        m={e['id']:e for e in r['marker_events']}
        row=dict(run=r['run'],group=r['group'],analysis_sha256=sha(HERE/(r['run']+'-analysis.json')),
            marker_order=[e['id'] for e in r['marker_events']],all_expected_markers=r['all_expected_markers_observed'],
            first_strobe_ms=m[2]['time_ms'],receiver_to_first_strobe_ms=r['receiver_entry_to_first_strobe_ms'],
            frame_complete_ms=m[3]['time_ms'],post5ms_energy_mJ=r['post5ms_to_plateau']['energy_mJ'],
            onset_to_low_plateau_ms=r['whole_cycle_raw_unqualified']['duration_ms'],
            low_plateau_mA=r['low_plateau_100ms']['current_mean_mA'],low_plateau_input_V=r['low_plateau_100ms']['voltage_mean'],
            peak1ms_mean_mA=r['peaks_1ms'][0]['current_mean_mA'],peak10ms_mean_mA=r['peaks_10ms'][0]['current_mean_mA'],
            SD_init_ms=ph['SD_initialization']['duration_ms'],scan_preparation_ms=ph['SCR_scan_write_preparation']['duration_ms'],
            slot_transport_ms=ph['slot_transport']['duration_ms'],slot_transport_mean_mA=ph['slot_transport']['current_mean_mA'])
        if r['group']=='autostop':
            row.update(frame_to_standby_observation_ms=r['frame_IRQ_to_standby_observation_ms'],
                external_exposure_envelopes=len(r['external_strobe']['qualified_exposure_pulses']),
                external_exposure_widths_ms=[p['duration_ms'] for p in r['external_strobe']['qualified_exposure_pulses']],
                single_external_exposure_envelope_observed=r['single_external_exposure_envelope_observed'],
                exposure_envelopes_end_before_frame_IRQ=r['exposure_envelopes_end_before_frame_IRQ'],
                no_external_exposure_edges_between_standby_observed_and_commit=r['no_external_exposure_edges_between_standby_observed_and_commit'])
        rows.append(row)
    groups={}
    for group in ('normal','autostop'):
        selected=[r for r in rows if r['group']==group]
        if not selected:continue
        fields=['first_strobe_ms','post5ms_energy_mJ','onset_to_low_plateau_ms','peak1ms_mean_mA','peak10ms_mean_mA',
            'SD_init_ms','scan_preparation_ms','slot_transport_ms','low_plateau_mA']
        if group=='autostop':fields.append('frame_to_standby_observation_ms')
        groups[group]=dict(count=len(selected),statistics={field:dict(mean=float(np.mean([r[field] for r in selected])),
            median=float(np.median([r[field] for r in selected])),min=float(min(r[field] for r in selected)),max=float(max(r[field] for r in selected))) for field in fields})
    comparison=None
    if 'normal' in groups and 'autostop' in groups:
        a=groups['normal']['statistics'];b=groups['autostop']['statistics']
        comparison={k:dict(normal_mean=a[k]['mean'],autostop_mean=b[k]['mean'],
            autostop_minus_normal=b[k]['mean']-a[k]['mean'],reduction_percent=100*(1-b[k]['mean']/a[k]['mean'])) for k in a}
    out=dict(runs=rows,groups=groups,comparison=comparison,
        scope='Fresh normal cold baseline versus promoted auto-stop cold cycles. Per-run card timing, scan length and input voltage remain explicit; comparisons are descriptive, not a statistical or causal isolation of sensor-only energy.',
        qualifications=['Post5ms integration only; first5ms/inrush and instantaneous extrema remain unqualified.',
            'All11 markers plus one PD0 envelope establish observed control flow and exposure IRQ count; use independent AST/readback/code audit for stronger single-frame/save proof.',
            'Marker11 is first firmware observation of autonomous FSM2, not exact physical transition.',
            'Current onset is a repeatable trace threshold, not independently measured battery switch closure or reset release.',
            'Normal baseline has no STOP GPIO marker; its cold STOP tail is not inferred.',
            'Low plateau is an analog signature; no SBF/photo-slot/readback claim follows automatically.'])
    (HERE/'cold-promotion-comparison.json').write_text(json.dumps(out,indent=2)+'\n')
    return out

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('manifest',type=Path);ap.add_argument('--summary-only',action='store_true');args=ap.parse_args()
    items=json.loads(args.manifest.read_text())
    reports=[json.loads((HERE/(x['run']+'-analysis.json')).read_text()) for x in items] if args.summary_only else [analyze(x) for x in items]
    print(json.dumps(summarize(reports),indent=2))
