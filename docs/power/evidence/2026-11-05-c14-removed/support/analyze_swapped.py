"""Explicit offline interpretation of new traces with observed GPI roles reversed.

Raw gpi0 remains physical IN0 and raw gpi1 remains physical IN1. This module
does not rewrite either stream or the original analysis. It requires a complete
eleven-phase train on physical IN1 and a properly bounded exposure mirror on
physical IN0 before assigning logical roles.
"""
from pathlib import Path
import argparse
import importlib.util
import json

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'analyze_inrush.py'
spec = importlib.util.spec_from_file_location('inrush_mapping_base', SOURCE)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


def exposure_evidence(signals, markers, onset):
    events = {event['id']: event for event in markers['events']}
    base.require(set(events) == set(range(1, 12)), 'Require all11 logical phase markers')
    edges = base.edges(signals, 'gpi1')
    before = [edge for edge in edges if events[1]['end_sample_id'] <= edge['sample_id'] < events[2]['sample_id'] - 200]
    base.require(len(before) == 1 and before[0]['level'] == 0,
                 'Require exactly one explicit post-entry LOW before first exposure')
    start = before[0]['sample_id'] + 200
    end = events[8]['sample_id']
    selected = [edge for edge in edges if start <= edge['sample_id'] < end]
    base.require(len(selected) == 2 and [edge['level'] for edge in selected] == [1, 0],
                 'Require exactly one complete exposure envelope through commit')
    rise, fall = selected
    offset = (rise['sample_id'] - events[2]['sample_id']) / base.FS * 1e6
    base.require(abs(offset) < 100, 'Exposure rise does not match phase2')
    base.require(fall['sample_id'] < events[3]['sample_id'] < events[11]['sample_id'] < end,
                 'Exposure/frame/standby-observation/commit precedence failed')
    return dict(physical_stream='gpi0/IN0', logical_role='PD0 exposure IRQ mirror',
        explicit_low_sample_id=before[0]['sample_id'], observation_start=start,
        observation_end_exclusive=end, complete_envelopes=1,
        rise_sample_id=rise['sample_id'], fall_sample_id=fall['sample_id'],
        rise_ms=(rise['sample_id'] - onset) / base.FS * 1000,
        fall_ms=(fall['sample_id'] - onset) / base.FS * 1000,
        duration_ms=(fall['sample_id'] - rise['sample_id']) / base.FS * 1000,
        rise_minus_phase2_us=offset,
        scope='Observed MCU IRQ mirror, not direct sensor pin or independent sensor frame counter; qualified through commit8')


def analyze(trace):
    report, profile = base.analyze(trace, markers='11')
    original_marker_decode = report['marker_decode']
    raw, checks, _ = base.load_trace(trace)
    base.require('gpi0' in raw and 'gpi1' in raw, 'Both physical GPI streams required')
    logical = dict(raw)
    logical['gpi0'], logical['gpi1'] = raw['gpi1'], raw['gpi0']
    onset = report['current_onset']['sample_id']
    markers = base.decode_markers(logical, onset, '11')
    base.require(markers['unique_complete_train'], 'No unique11-marker phase train on physical GPI1')
    exposure = exposure_evidence(logical, markers, onset)
    report.update(original_marker_decode=original_marker_decode,
        marker_decode=markers, cycle=base.cycle_metrics(logical, markers, onset),
        external_exposure_mirror=exposure,
        gpio_interpretation=dict(explicit_remapping=True,
            phase_source='physical IN1 / raw gpi1', exposure_source='physical IN0 / raw gpi0',
            observation='Complete phase protocol onIN1 and bounded exposure envelope onIN0 support reversed roles relative to the historical hookup.',
            physical_rewiring_verified=False, raw_files_changed=False,
            instrument_settings_changed=False,
            scope='Offline logical aliases only; raw stream names, sample IDs and hashes retain physical acquisition identity'),
        remapping_source_sha256=base.sha(Path(__file__)))
    report['limitations'].append('GPI roles are explicitly inferred from independent protocol/envelope evidence; physical wiring was not inspected.')
    return report, profile, logical


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    dest = args.out.resolve()
    dest.relative_to(HERE)
    base.require(not dest.exists(), 'Do not overwrite original or existing analysis')
    report, _, _ = analyze(args.trace)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(output=str(dest), markers=report['marker_decode']['events'],
        exposure=report['external_exposure_mirror'],
        post5ms=report['cycle'].get('post5ms_to_plateau'),
        plateau=report['cycle'].get('low_plateau_100ms')), indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
