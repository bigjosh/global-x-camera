"""UNUSED: planned full final-cold-boot closure, abandoned at the user's stop.

The root-authored final-state.json records the actual partial qualification.
This helper was not run and its required final cold trace does not exist.
It must not be used to imply a final boot or all-three-image readback occurred.

Original purpose: write final-state.json from completed files and a root owner-release record.

No debugger, serial, device, network, subprocess, or instrument APIs are used.
This records the final cold FLASH current/phase signature, not a fresh final
photo readback or a new final Standby-flag observation. Never overwrites output.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path

HOME=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('file_only_singleframe_archive',HOME/'archive_single_frame.py')
archive=importlib.util.module_from_spec(spec);spec.loader.exec_module(archive)
EXPECTED=archive.EXPECTED['flash-standby-v1']

def readj(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def when(value):
    value=datetime.fromisoformat(value.replace('Z','+00:00'))
    assert value.tzinfo is not None
    return value
def local(path):
    path=Path(path);path=path if path.is_absolute() else HOME/path
    path=path.resolve();path.relative_to(HOME.resolve())
    assert path.is_file(),str(path)
    return path
def relative(path):return local(path).relative_to(HOME).as_posix()


def finish(owner_path,free_path):
    evidence={}
    def bind(path):
        path=local(path);evidence[relative(path)]=sha(path);return readj(path)
    owner_path=local(owner_path);owner=bind(owner_path)
    assert owner['schema']==1 and owner['bench_owner']=='root'
    assert owner['active_helpers'] is False and owner['com8_closed'] is True and owner['break_released'] is True
    assert owner['hardware_changes_after_final_trace'] is False
    archive.tests(HOME)
    bind('offline-tests.json');bind('offline-tests.log') if False else None
    evidence['offline-tests.log']=sha(HOME/'offline-tests.log')
    bind('control-build-results.json')
    for name,build in (('install-awake','flash-awake-v3'),('install-standby','flash-standby-v1')):
        result=bind(name+'/complete.json')
        assert all(result.get(k) is True for k in ('passed','independent_full_readback','following4096_unchanged'))
        assert result['new_sector_sha256']==archive.EXPECTED[build]['sector']
        assert sha(HOME/name/'nor-after/readback.bin')==result['new_sector_sha256']
        assert sha(HOME/name/'nor-before/readback.bin')==result['old_sector_sha256']
        assert (HOME/name/'following-before/readback.bin').read_bytes()==(HOME/name/'following-after/readback.bin').read_bytes()
    for filename in ('awake-offline-audit.json','standby-offline-audit.json'):
        assert bind(filename)['passed'] is True
    awake=bind('awake-inspect/verified.json')
    assert awake['passed'] is True and awake['kind']=='raw-flash-inspection' and awake['proof']['nonce']==0
    ast=awake['sensor_autostop']
    assert ast['version']==2 and ast['completed'] and ast['production_single_frame'] and ast['exact_one_frame_observed']
    assert ast['sensor_count_from_reset']==ast['strobe_delta']==1 and ast['explicit_stop_writes']==0
    images=archive.image_validations(HOME)
    assert [v['slot'] for _,v in images]==[142,143,144,145]
    for path,value in images:
        bind(path)
        for item in value['artifacts']:
            assert sha(local(item['path']))==item['sha256']
        ref=value.get('source_reference_comparison')
        if ref:
            assert sha(local(ref['source']['path']))==ref['source']['sha256']==value['raw_sha256']
    bind('awake-readback/summary.json');bind('cold-images-readback/summary.json')
    comparison=bind('analysis/cold-promotion-comparison.json')
    rows={item['run']:item for item in comparison['runs']}
    assert set(rows)=={'control-before','candidate01','candidate02','candidate03'}
    recoveries=[]
    for name in ('candidate01','candidate02','candidate03'):
        phase=bind('analysis/'+name+'-analysis.json')
        assert sha(HOME/'analysis'/(name+'-analysis.json'))==rows[name]['analysis_sha256']
        assert phase['all_expected_markers_observed'] and phase['single_external_exposure_envelope_observed']
        park=bind(name+'/park/result.json')
        assert park['passed'] and park['prefix_sha256']==EXPECTED['prefix']
        assert park['context']['PC']==0x3418078C and park['context']['CONTROL']==0
        assert park['vcp_status']['good_pulses']>=3 and park['vcp_status']['bad_pulses']==0
        recoveries.append(dict(run=name,good_pulses=park['vcp_status']['good_pulses'],
            bad_pulses=park['vcp_status']['bad_pulses'],park=park['context']['PC']))
    standby=bind('candidate-standby-flags/result.json')
    assert standby['passed'] and standby['sbf'] and standby['pdds'] and not standby['stopf']
    assert standby['trial_entry_proven'] is False and standby['prefix_sha256']==EXPECTED['prefix']
    result=bind('final/trace/result.json');analysis=bind('analysis/final-analysis.json')
    assert result['success'] and not result['errors'] and not result['cleanup_errors']
    assert analysis['result_sha256']==sha(HOME/'final/trace/result.json')
    assert analysis['run']=='final' and analysis['group']=='autostop'
    for key in ('unique_marker_train','marker_precedence_pass','all_expected_markers_observed',
            'single_external_exposure_envelope_observed','exposure_envelopes_end_before_frame_IRQ',
            'no_external_exposure_edges_between_standby_observed_and_commit'):
        assert analysis[key] is True,key
    ids=[v['id'] for v in analysis['marker_events']]
    assert len(ids)==11 and set(ids)==set(range(1,12)) and ids.index(3)<ids.index(11)<ids.index(8)
    for signal,check in analysis['checks'].items():
        assert check['hash_passed'] and check['contiguous'] and check['sha256']==result['sha256'][signal]
    plateau=analysis['low_plateau_100ms']
    assert plateau['finite'] is True and plateau['duration_ms']==100
    assert 6<plateau['current_mean_mA']<12 and 4.8<plateau['voltage_mean']<5.1
    events_path=HOME/'final/trace/events.jsonl';evidence[relative(events_path)]=sha(events_path)
    events=[json.loads(line) for line in events_path.read_text().splitlines()]
    names=[event['event'] for event in events]
    required=('opened','ready','power_off','off_verified','power_on','observation_end','closed')
    assert names==list(required),names
    off=events[3];power_on=events[4];closed=events[-1]
    assert off['seconds']>=15 and abs(off['mean_a'])<0.005
    assert closed['success'] and not closed['errors'] and not closed['cleanup_errors']
    assert closed['sha256']==result['sha256'] and closed['initial_settings']==result['initial_settings']
    assert result['initial_settings']['s/i/range/select']==128
    assert result['initial_settings']['s/extio/voltage']==0
    assert when(owner['observed_utc'])>=when(closed['utc'])
    free_path=local(free_path);free=bind(free_path)
    assert free['passed'] and free['one_sector_per_slot']
    matches=[item for item in free['slots'] if item['slot']==146];assert len(matches)==1
    entry=matches[0];assert entry['header']['state']=='FREE' and entry['header']['occupied'] is False
    erase=free['layout']['erased_byte'];assert erase in (0,255)
    data_path=local(entry['data']['path']);proof_path=local(entry['proof']['path'])
    data=data_path.read_bytes();proof=bind(proof_path)
    assert len(data)==512 and data==bytes([erase])*512
    assert sha(data_path)==entry['data']['sha256'] and sha(proof_path)==entry['proof']['sha256']
    assert proof['passed'] and proof['binary_sha256']==archive.EXPECTED['design/read-helper']['receiver']
    p=proof['proof']
    assert p['nonce'] and p['operation']==3 and p['state']==3 and p['result']==p['cleanup_error']==0
    assert p['media_idle']==1 and p['read_lba']==146*3730 and p['read_count']==1 and p['read_bytes']==512
    assert p['card_write_lo']==p['card_write_hi']==0 and proof['read_sha256']==entry['data']['sha256']
    assert free_path.stat().st_mtime<=when(power_on['utc']).timestamp()
    assert proof_path.stat().st_mtime<=when(power_on['utc']).timestamp()
    return dict(schema=1,completed=True,recorded_utc=datetime.now(timezone.utc).isoformat(),
        scope='File-only finalization of root-owned completed bench observations; no new hardware access.',
        receiver_sha256=EXPECTED['receiver'],prefix_sha256=EXPECTED['prefix'],sector_sha256=EXPECTED['sector'],
        sensor_single_frame_installed=True,sensor_autostop_installed=True,cold_sensor_autostop_qualified=True,
        normal_unchanged=False,nor_programming=True,physical_full_nor_readback_verified=True,
        following4096_unchanged=True,card_erased=False,wiring_changed=False,
        active_helpers=False,com8_closed=True,break_released=True,owner_release=relative(owner_path),
        js_closed_utc=closed['utc'],js_settings_restored_and_requeried_by_logger=True,
        js_initial_settings=result['initial_settings'],js_output_enabled=True,
        target_powered=True,target_execution='normal single-frame FLASH after final cold cycle; not a RAM helper',
        final_state_proof='current/phase signature only; no fresh final SBF or final-photo readback',
        final_marker_order=ids,final_exposure_envelopes=1,final_plateau=plateau,
        final_cycle_post5ms_energy_mJ=analysis['post5ms_to_plateau']['energy_mJ'],
        final_expected_slot=146,final_expected_slot_was_free=True,final_photo_readback=False,final_sbf_read=False,
        final_free_header=dict(summary=relative(free_path),data=entry['data'],proof=entry['proof'],
            erased_byte=erase,all_512_bytes_erased=True,precedes_final_power_on_by_file_completion=True),
        verified_sensor_slots=[142,143,144,145],awake_original_sensor_ram_equality=True,
        cold_saved_images_readback=True,cold_source_ram_lost_in_standby=True,
        recovery_checks=recoveries,
        prior_guarded_standby=dict(sbf=True,pdds=True,stopf=False,trial_entry_proven=False,
            path='candidate-standby-flags/result.json'),
        wiring='Regulated bench5V through JS to CN5.5, return CN5.6; CN8/LTC disconnected, no CN9 shunts; '
            'CN10 separately powered, D2/R23 removed, U24 fitted, JP1/JP2 normal. '
            'CN15 PD12/PD0/ground21/33/20; SD twisted CLK/GND CN3.3/8, VCC CN3.5, no resistor or signal probes.',
        evidence=[dict(path=path,sha256=digest) for path,digest in sorted(evidence.items())])


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--owner-proof',type=Path,required=True)
    ap.add_argument('--free-summary',type=Path,default=HOME/'before-final-headers/summary.json')
    ap.add_argument('--check-only',action='store_true')
    args=ap.parse_args();output=finish(args.owner_proof,args.free_summary)
    if not args.check_only:
        path=HOME/'final-state.json'
        if path.exists():raise FileExistsError(path)
        path.write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(output,indent=2))
