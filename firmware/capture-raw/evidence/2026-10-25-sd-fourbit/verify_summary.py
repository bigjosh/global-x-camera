"""Check recorded arithmetic/identities only; no hardware or private-data access."""
from pathlib import Path
import json
import math
import statistics


def main():
    data = json.loads(Path(__file__).with_name('measurement-summary.json').read_text(encoding='utf-8'))
    assert data['schema'] == 1
    assert data['installed']['sector_sha256'] == 'bb31867394a4e0d0fb9ab3f9fa96d0d16ffc7256e2a274db74be4f11f9cfdc14'
    assert data['installed']['prefix_sha256'] == '09fb59cfed0f715927e76f32d5f74187e4c2f1702a70ce192e0d17dcee2f822a'
    assert data['candidate_profile'] == dict(bus_width=4, clock_hz=12500000, gpio_speed=3, fixed_compensation=False, voltage_v=3.3)
    assert data['baseline_profile'] == dict(bus_width=1, clock_hz=25000000, voltage_v=3.3)
    assert data['format']['slot_bytes'] == data['format']['slot_sectors'] * 512
    assert data['format']['image_offset'] + data['format']['image_bytes'] + 4 == data['format']['slot_bytes']
    for group in ('baseline', 'candidate'):
        rows = data[group]
        assert len(rows) == 3 and [r['slot'] for r in rows] == [0, 1, 2]
        for r in rows:
            assert r['recorded_sbf_pass'] and r['recorded_image_readback_pass']
            assert r['cycle_s'] > 0 and r['energy_j'] > 0
            assert math.isclose(r['payload_to_commit_ms'], r['payload_to_ready_ms'] + r['ready_to_commit_ms'], rel_tol=1e-12)
    for key, expected in data['comparison'].items():
        old = statistics.median(r[key] for r in data['baseline'])
        new = statistics.median(r[key] for r in data['candidate'])
        assert math.isclose(old, expected['old_median'], rel_tol=1e-12)
        assert math.isclose(new, expected['new_median'], rel_tol=1e-12)
        assert math.isclose(1-new/old, expected['reduction_fraction'], rel_tol=1e-12)
    for group in ('baseline', 'candidate'):
        seconds = statistics.median(r['payload_to_commit_ms'] for r in data[group])/1000
        mbps = data['format']['image_bytes']/1e6/seconds
        assert math.isclose(mbps, data['image_payload_MB_s'][group], rel_tol=1e-12)
    assert not data['qualification']['original_ram_comparison_for_three_standby_cycles']
    assert not data['qualification']['strict_final_pulse_decode']
    assert data['qualification']['independent_sbf_attribution']
    assert data['final_state']['awake_idle_ram_read_park'] and not data['final_state']['currently_standby']
    print(json.dumps(dict(passed=True, recorded_runs=6, comparison=data['comparison'],
        scope='Recorded arithmetic and pinned firmware/profile identities only; no native integration, image decoding, hardware or private-data access.'), indent=2))


if __name__ == '__main__':
    main()
