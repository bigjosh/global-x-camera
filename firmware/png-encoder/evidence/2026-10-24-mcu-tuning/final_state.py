"""Derive the bounded physical checkpoint from archived restoration records."""
import json
import statistics
from pathlib import Path
from add_trial import HERE,read,sha,dump


def derive(root=HERE):
    folder=root/'restoration/completed-known-compute/records'
    prior=root/'restoration/refused-initial-current/records'
    result=read(folder/'result.json');first=read(prior/'result.json')
    events=[json.loads(line) for line in (folder/'recording/cycle.jsonl').read_text(encoding='utf-8').splitlines()]
    old_events=[json.loads(line) for line in (prior/'recording/cycle.jsonl').read_text(encoding='utf-8').splitlines()]
    assert first['success'] is False and not any(x['event'] in ('command_off','command_auto') for x in old_events)
    assert result['success'] is True and result['raw_logging_complete'] is True
    assert [x['event'] for x in events if x['event'].startswith('command_')]==['command_off','command_auto','command_stop']
    initial=next(x for x in events if x['event']=='compute_completed_start')
    off=next(x for x in events if x['event']=='off_baseline')
    assert len(initial['statistics'])==6 and off['off_seconds']>=15
    assert all(abs(x['current']['avg'])<0.0001 for x in off['statistics'])
    phase=read(folder/'phase-summary.json')
    assert phase['decode_passed'] is False
    assert len(phase['pulses'])==10 and all(p['complete'] for p in phase['pulses'])
    stopped=result['helper_stopped_record']
    assert stopped['ok'] and stopped['range']==128 and stopped['restore_error'] is None
    for key in ('sbf_verified','image_integrity_verified','terminal_state_qualified','nor_identity_read_this_run'):
        assert result[key] is False
    final=result['observations']['final_statistics']
    return dict(schema=1,passed=True,
        sources={str(p.relative_to(root)).replace('\\','/'):sha(p.read_bytes()) for p in
                 (folder/'result.json',folder/'recording/cycle.jsonl',folder/'phase-summary.json',prior/'result.json',prior/'recording/cycle.jsonl')},
        explicit_off_on_cycles=1,off_observation_seconds=off['off_seconds'],off_current_A=[x['current']['avg'] for x in off['statistics']],
        final_observation_utc=final['received']['utc'],helper_stopped_utc=stopped['utc'],
        final_JS_input_voltage_V=final['voltage']['avg'],final_current_A=final['current']['avg'],
        JS_restored_range=128,target_left_powered=True,complete_marker_pulses=10,
        strict_width_decode_passed=False,phase_ids_inferred_by_this_script=False,
        installed_sector_owner_attested=result['installed_sector_owner_attested'],NOR_identity_read_this_run=False,
        image_integrity_verified=False,SBF_verified=False,physical_Standby_proven=False,energy_claim=False,
        initial_current_anomaly=dict(first_last_recorded_current_A=first['helper_stopped_record']['statistics']['current']['avg'],
            second_pre_off_mean_current_A=statistics.mean(x['current']['avg'] for x in initial['statistics']),
            second_pre_off_range_A=[min(x['current']['avg'] for x in initial['statistics']),max(x['current']['avg'] for x in initial['statistics'])],
            cause_established=False,disappearance_precedes_cold_cycle=True),
        owner_attestation=dict(source='Root hardware-owner message after the final closed run',
            COM8_closed=True,BREAK_released=True,Logic2_left_running=True,no_further_hardware_planned=True),
        limits=['The host restoration helper sent no SD/NOR commands; normal installed firmware may save a new photo after boot',
                'Ten complete pulses and quiet current do not replace SBF or saved-image verification',
                'Raw logging coverage passed; no native-stream energy analysis is claimed',
                'The earlier high current had subsided before power-off; do not attribute its disappearance to cold reset'])


if __name__=='__main__':
    result=derive();dump(HERE/'restoration/final-state.json',result)
    print(json.dumps({key:result[key] for key in ('passed','explicit_off_on_cycles','final_current_A','strict_width_decode_passed')}))
