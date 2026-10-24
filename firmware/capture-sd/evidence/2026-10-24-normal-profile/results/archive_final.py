"""Archive the closed final checkpoint; no hardware access or large-stream reads."""
import json
from archive_installation import HERE, copy_groups, read, sha

SECTOR = '8129f9cc79e92c678207b4aee838810cc805d0b860c40b2f77b434ae746c8b61'

def main():
    out = copy_groups('final-checkpoint', ['final-vcp', 'final-park', 'final-nor', 'final-cycle'])
    nor = (out / 'final-nor/nor.bin').read_bytes()
    assert nor == (HERE.parent / 'build/v66c-normal-standby/staged/capture_sector_0.bin').read_bytes()
    assert sha(nor) == SECTOR and len(nor) == 65536
    assert read(out / 'final-park/result.json')['passed']
    result = read(out / 'final-cycle/result.json')
    response = read(out / 'final-cycle/response.json')
    phase = read(out / 'final-cycle/phase-summary.json')
    assert result['recording_complete'] and not result['phase_decode_passed']
    assert not result['terminal_state_qualified'] and not result['image_integrity_verified']
    assert len(phase['pulses']) == 10 and all(p['complete'] for p in phase['pulses'])
    assert response['event'] == 'stopped' and response['ok'] and response['restore_error'] is None
    assert response['range'] == response['starting_range'] == 128
    state = dict(
        installed_build='v66c-normal-standby', sector_sha256=SECTOR,
        whole_sector_verified_before_final_boot=True, nor_readback_after_final_boot=False,
        stopped_utc=response['utc'], target_left_powered=True,
        js_current_range_restored=128,
        final_measured_voltage_V=response['statistics']['voltage']['avg'],
        final_measured_current_A=response['statistics']['current']['avg'],
        voltage_location=response['statistics']['voltage_location'],
        complete_marker_pulses=10, strict_width_decode_passed=False,
        last_cycle_standby_independently_verified=False,
        last_cycle_image_verified=False, expected_unverified_filename='IMG00072.PNG',
        final_cycle_energy_analyzed=False,
        limitations=['Ten ordered pulses and the measured plateau do not independently establish Standby or image integrity',
                     'The last sample statistics describe the measured branch, not isolated MCU consumption',
                     'Raw logging coverage does not validate boundaries, clipping, or the 71 nonfinite current samples'],
        hardware_owner_attestation={
            'source':'Root hardware-owner completion message after 2026-10-24T02:39:05.697298Z',
            'no_uart_sbf_or_image_readback_after_final_cycle':True,
            'all_helper_owners_inactive':True,
            'com8_closed':True, 'break_released':True,
            'target_left_powered':True,
            'process_check_note':'CIM matched only the inspection shell'},
        source_records=['final-nor/nor.bin','final-park/result.json','final-cycle/result.json',
                        'final-cycle/response.json','final-cycle/phase-summary.json'],
        hardware_accessed_by_archiver=False)
    (out / 'final-state.json').write_text(json.dumps(state, indent=2)+'\n', encoding='utf-8')
    index = read(out / 'index.json')
    print(json.dumps(dict(indexed_files=len(index['files']), bytes=sum(x['bytes'] for x in index['files']),
                         final_state=str(out / 'final-state.json')), indent=2))

if __name__ == '__main__':
    main()
