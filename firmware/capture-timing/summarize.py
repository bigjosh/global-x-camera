"""Offline experiment ledger from explicitly selected completed capture folders.

Each folder must contain timing.json and ram/capture-result.json. No instruments,
images, memory dumps, or NOR contents are accessed. Timing/RAM event association
is verified before summarizing. New output files are never overwritten.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path


ERROR_IDS = {70, 71, 73, 74}
PHASE_IDS = {
    'stage1_entry': 200, 'stage2_entry': 207, 'main_entry': 2,
    'sensor_ready_observed': 101, 'sensor_init_complete': 12,
    'exposure_configuration_complete': 15, 'receiver_configured': 21,
    'receiver_armed': 22, 'sensor_output_setup_complete': 111,
    'start_write_begin': 24, 'start_write_end': 25,
    'sensor_start_return': 26, 'first_vsync': 29, 'first_frame_complete': 30,
}


def micros(end, start):
    return None if end is None or start is None else round((end - start) * 1e6, 3)


def summarize_documents(timing, result):
    if not timing.get('matched'):
        raise ValueError('Timing alignment has not passed')
    events, ram = timing.get('events', []), result.get('events', [])
    if not events or len(events) != len(ram) or result.get('event_count') != len(ram):
        raise ValueError('Timing and RAM event counts differ')
    for observed, original in zip(events, ram):
        if any(observed.get(key) != original.get(key) for key in ('id', 'cycles', 'tick_ms', 'core_hz')):
            raise ValueError('Timing belongs to a different RAM event sequence')
    times = [event['time_s'] for event in events]
    if any(not math.isfinite(t) for t in times) or any(a >= b for a, b in zip(times, times[1:])):
        raise ValueError('Event timestamps must be finite and strictly increasing')

    def first(event_id):
        return next((event['time_s'] for event in events if event['id'] == event_id), None)

    nrst, pd0 = timing.get('nrst_release_s'), timing.get('pd0_rise_s')
    origin = nrst if nrst is not None else times[0]
    phase = {name: first(event_id) for name, event_id in PHASE_IDS.items()}
    # A no-reset experiment may omit both IDs; never invent a release event.
    phase['sensor_release_command'] = first(202) if first(202) is not None else first(11)
    phase['stage2_load_begin'], phase['stage2_load_end'] = first(203), first(204)
    warnings = []

    pulses, pending = [], None
    for event in events:
        if event['id'] == 50:
            if pending is not None:
                raise ValueError('Repeated strobe rise without a fall')
            pending = event
        elif event['id'] == 51:
            if pending is None:
                raise ValueError('Strobe fall has no preceding recorded rise')
            pulses.append(dict(ordinal=len(pulses) + 1,
                               rise_us=micros(pending['time_s'], origin),
                               fall_us=micros(event['time_s'], origin),
                               width_us=micros(event['time_s'], pending['time_s']),
                               rise_after_start_write_end_us=micros(pending['time_s'], phase['start_write_end']),
                               _rise=pending['time_s'], _fall=event['time_s']))
            pending = None
    if pending is not None:
        warnings.append('Final strobe rise lacks a fall; it is not a completed pulse.')
    rise, fall = (pulses[0]['_rise'], pulses[0]['_fall']) if pulses else (None, None)
    frame, vsync = phase['first_frame_complete'], phase['first_vsync']
    if pulses and not (phase['start_write_end'] is not None and phase['start_write_end'] <= rise < fall):
        warnings.append('First recorded pulse is not ordered after the START write.')
    if pulses and not (vsync is not None and frame is not None and fall <= vsync < frame):
        warnings.append('First pulse/VSYNC/frame ordering does not qualify the expected first snapshot.')

    error_events = [event for event in events if event['id'] in ERROR_IDS]
    details = result.get('error_events', [])
    if result.get('errors', 0) != len(error_events):
        warnings.append('Error callback count differs from recorded event count; error history is incomplete.')
    attach_details = len(details) == len(error_events)
    if details and not attach_details:
        warnings.append('Error detail count differs; raw details were not associated by guesswork.')
    classified, counts = [], dict(pre_frame=0, during_frame=0, post_frame=0, unclassified=0)
    for index, event in enumerate(error_events):
        stamp = event['time_s']
        phase_name = ('pre_frame' if vsync is not None and stamp < vsync else
                      'during_frame' if vsync is not None and frame is not None and vsync <= stamp <= frame else
                      'post_frame' if frame is not None and stamp > frame else 'unclassified')
        counts[phase_name] += 1
        optical_phase = ('before_first_exposure' if rise is not None and stamp < rise else
                         'during_first_exposure' if rise is not None and fall is not None and rise <= stamp <= fall else
                         'after_exposure_before_frame_complete' if fall is not None and frame is not None and fall < stamp <= frame else
                         'after_first_frame' if frame is not None and stamp > frame else 'unclassified')
        item = dict(id=event['id'], time_us=micros(stamp, origin),
                    frame_phase=phase_name, optical_phase=optical_phase)
        if attach_details:
            detail = details[index]
            delta = (event['cycles'] - detail['cycles']) & 0xffffffff
            if detail['id'] != event['id'] or delta >= max(1, event['core_hz'] // 1000):
                raise ValueError('Error details cannot be safely associated with event edges')
            item['detail_to_event_cycles'] = delta
            for name in ('error', 'csi_sr0', 'csi_sr1', 'cmsr2', 'ier0_entry', 'ier1_entry',
                         'ier0_callback', 'ier1_callback', 'previous_stage'):
                if name in detail:
                    item[name] = detail[name]
        classified.append(item)

    words = result.get('words', [])
    at = lambda index: words[index] if len(words) > index else None
    clocks = None
    if all(at(i) for i in range(52, 56)):
        packed = at(56)
        clocks = dict(external_hz=at(52), system_pll_hz=at(53), pixel_hz=at(54), sensor_mcu_hz=at(55),
                      system_predivider=packed & 7, system_multiplier=(packed >> 8) & 255,
                      system_output_divider=(packed >> 16) & 255, mipi_multiplier=(packed >> 24) & 255,
                      mipi_output_divider=at(57), configured_frame_lines=at(58))
    for pulse in pulses:
        pulse.pop('_rise'); pulse.pop('_fall')
    return dict(
        mode=timing.get('mode'), origin='nrst_release' if nrst is not None else 'first_recorded_event',
        build_sha256=result.get('build_sha256'), completed=result.get('completed', False),
        image_integrity_matches=result.get('image_integrity_matches', False),
        visual_qualification=result.get('visual_qualification', 'not recorded'),
        exposure_qualified=False, frame_geometry=[result.get('width'), result.get('height')],
        frame_bytes=result.get('frame_bytes'), frames=result.get('frames'), vsyncs=result.get('vsyncs'),
        rom_to_pd0_us=micros(pd0, nrst),
        phases_us={name: micros(stamp, origin) for name, stamp in phase.items()},
        intervals_us=dict(sensor_release_to_ready=micros(phase['sensor_ready_observed'], phase['sensor_release_command']),
                          sensor_ready_to_start_write=micros(phase['start_write_begin'], phase['sensor_ready_observed']),
                          start_write_duration=micros(phase['start_write_end'], phase['start_write_begin']),
                          start_write_end_to_first_strobe=micros(rise, phase['start_write_end']),
                          stage2_load=micros(phase['stage2_load_end'], phase['stage2_load_begin']),
                          first_strobe_end_to_vsync=micros(vsync, fall),
                          first_vsync_to_frame_complete=micros(frame, vsync)),
        first_strobe_us=micros(rise, origin), first_strobe_width_us=pulses[0]['width_us'] if pulses else None,
        strobe_pulses=pulses, camera_error=result.get('camera_error'),
        error_counts=counts, errors=classified,
        first_frame_status=dict(csi_sr0=at(44), csi_sr1=at(45), applied_coarse_lines=at(46), line_length=at(47)),
        clock_readbacks=clocks, warnings=warnings,
    )


def summarize_folder(folder):
    folder = folder.resolve()
    sources = [folder / 'timing.json', folder / 'ram' / 'capture-result.json']
    raw = [path.read_bytes() for path in sources]
    entry = summarize_documents(*(json.loads(data.decode('utf-8-sig')) for data in raw))
    entry['capture_dir'] = str(folder)
    entry['source_sha256'] = {str(path.relative_to(folder)): hashlib.sha256(data).hexdigest()
                              for path, data in zip(sources, raw)}
    return entry


def markdown(entries):
    def ms(value):
        return '—' if value is None else f'{value / 1000:.3f}'
    lines = ['Times are ms from NRST for cold starts; RAM runs use their first recorded event.',
             'Error columns mean before first VSYNC / VSYNC through first frame completion / after first frame.',
             'Visual qualification is not inferred; first-pulse timing alone does not establish a valid image.', '',
             '| Capture | ROM | Release | READY | Config | START end | First strobe | Frame | Width | Errors pre/during/post |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
    for entry in entries:
        p, errors = entry['phases_us'], entry['error_counts']
        name = Path(entry['capture_dir']).name
        if name == 'cold':
            name = Path(entry['capture_dir']).parent.name
        cells = [name, ms(entry['rom_to_pd0_us']), ms(p['sensor_release_command']), ms(p['sensor_ready_observed']),
                 ms(p['exposure_configuration_complete']), ms(p['start_write_end']), ms(entry['first_strobe_us']),
                 ms(p['first_frame_complete']), ms(entry['first_strobe_width_us']),
                 '/'.join(str(errors[key]) for key in ('pre_frame', 'during_frame', 'post_frame'))]
        lines.append('| ' + ' | '.join(cells) + ' |')
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture_dirs', nargs='+', type=Path)
    parser.add_argument('--json-out', type=Path)
    parser.add_argument('--markdown-out', type=Path)
    args = parser.parse_args()
    entries = [summarize_folder(folder) for folder in args.capture_dirs]
    report = markdown(entries)
    # Check both paths before creating either output. This is not an overwrite API.
    for path in (args.json_out, args.markdown_out):
        if path is not None and path.exists():
            parser.error(f'Refusing to overwrite {path}')
    if args.json_out:
        with args.json_out.open('x', encoding='utf-8') as output:
            json.dump(dict(schema=1, time_unit='us', experiments=entries), output, indent=2)
            output.write('\n')
    if args.markdown_out:
        with args.markdown_out.open('x', encoding='utf-8') as output:
            output.write(report)
    print(report, end='')


if __name__ == '__main__':
    main()
