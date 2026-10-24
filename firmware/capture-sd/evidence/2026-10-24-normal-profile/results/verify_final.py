"""Replay only the compact final-state claims; no hardware access."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent / 'final-checkpoint'
def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def verify():
    index = read(HERE / 'index.json')
    for item in index['files']:
        raw = (HERE / item['archived_path']).read_bytes()
        assert len(raw) == item['bytes']
        assert hashlib.sha256(raw).hexdigest() == item['sha256']
    state = read(HERE / 'final-state.json')
    nor = (HERE / 'final-nor/nor.bin').read_bytes()
    assert nor == (HERE.parent.parent / 'build/v66c-normal-standby/staged/capture_sector_0.bin').read_bytes()
    assert hashlib.sha256(nor).hexdigest() == state['sector_sha256']
    assert read(HERE / 'final-park/result.json')['passed']
    cycle = read(HERE / 'final-cycle/result.json')
    phase = read(HERE / 'final-cycle/phase-summary.json')
    response = read(HERE / 'final-cycle/response.json')
    assert cycle['recording_complete'] and not cycle['phase_decode_passed']
    assert not cycle['terminal_state_qualified'] and not cycle['image_integrity_verified']
    assert len(phase['pulses']) == 10 and all(x['complete'] for x in phase['pulses'])
    assert response['ok'] and response['event'] == 'stopped' and response['restore_error'] is None
    assert response['range'] == response['starting_range'] == state['js_current_range_restored'] == 128
    assert state['stopped_utc'] == response['utc']
    assert state['final_measured_voltage_V'] == response['statistics']['voltage']['avg']
    assert state['final_measured_current_A'] == response['statistics']['current']['avg']
    assert not state['last_cycle_standby_independently_verified'] and not state['last_cycle_image_verified']
    assert not state['nor_readback_after_final_boot']
    assert state['expected_unverified_filename'] == 'IMG00072.PNG'
    return dict(passed=True, indexed_files=len(index['files']), exact_prefinal_nor_verified=True,
                final_standby_or_image_claim=False, owner_attestations_not_independently_replayed=True)

if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
