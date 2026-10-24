"""Offline source-order inference for the exact v60c awake diagnostic.

Cold runs require independent NOR readback and the automatic SAVE proof.
Retained-frame SAVE runs require a matching request/terminal proof and exact
loaded RAM module. This is not a pulse-width decoder or a hardware runner.
"""
import argparse
import json
from pathlib import Path
import re
import struct
import zlib
from ordered_edges import ARCHIVE, LABELS, infer, load_module, require, sha

SECTOR = '20444827100b1a33826c5b7e3362a396a0ce31f27f0c3db7fea12fb755320f7e'
MODULE = '51c067de2859588fc87cf1249fdff4186b17a4e0ab85585c72fc9b5dc94379f5'
FRAME_SHA = '0e5f5620a9596609ebce747f6756020dd3cff9159436d166da55e425af7a0f6c'
FRAME_FNV = 2079365944


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def infer_storage(channels):
    marker = channels[1]
    edges = marker['transitions']
    require(marker['initial_state'] == 0, 'SAVE marker must start LOW')
    require(len(edges) == 12, 'Exactly six complete SAVE pulses are required')
    require(all(a < b for a, b in zip(edges, edges[1:])), 'Edges must strictly increase')
    require(marker['begin_s'] < edges[0] and edges[-1] < marker['end_s'],
            'SAVE boundary pulses must be complete')
    for number, channel in channels.items():
        require(all(abs(channel[k] - marker[k]) <= 1e-8 + 1e-15
                    for k in ('begin_s', 'end_s')), 'Mixed capture bounds')
    for number in (0, 4):
        require(channels[number]['initial_state'] == 1 and
                not channels[number]['transitions'], 'SAVE requires stable HIGH NRST and power')
    events = []
    for ordinal, event_id in enumerate(range(4, 10), 1):
        rise, fall = edges[(ordinal - 1) * 2:ordinal * 2]
        events.append(dict(ordinal=ordinal, inferred_event_id=event_id,
            inferred_checkpoint=LABELS[event_id - 1],
            assignment_basis='inferred from source call order',
            rising_edge_s=rise, falling_edge_s=fall, width_us=(fall-rise)*1e6,
            nominal_width_us=event_id*.5, width_error_us=(fall-rise)*1e6-event_id*.5,
            from_save_entry_ms=(rise-edges[0])*1e3,
            from_previous_marker_ms=None if ordinal == 1 else (rise-edges[(ordinal-2)*2])*1e3))
    return dict(ordered_structure_valid=True, width_qualification=False,
        event_assignment='inferred from source call order; not decoded from pulse widths',
        marker_initial_state=0, marker_final_state=0, transition_count=12,
        complete_pulse_count=6, observed_reset_release_s=None,
        observed_power_threshold_s=None, all_marker_edges_s=list(edges), events=events,
        intervals=[dict(from_inferred_event=a['inferred_event_id'],
                        to_inferred_event=b['inferred_event_id'],
                        interval_ms=(b['rising_edge_s']-a['rising_edge_s'])*1e3,
                        assignment_basis='inferred from source call order')
                   for a, b in zip(events, events[1:])])


def verify_save(proof, automatic):
    require(proof['module_sha256'] == MODULE, 'Different SAVE module')
    report, card = proof['report'], proof['card']
    filesystem = proof['fs'] if automatic else proof['filesystem']
    exact = dict(magic=0x53564431, schema=1, words=128, state=2, operation=1,
                 mode=1, result=0, terminal=0x444f4e45, cpu_hz=400000000,
                 media_idle=1, card_error=0, fs_result=0, png_result=0,
                 width=1120, height=1364, frame_bytes=3055360, rows=1364,
                 sd_hz=25000000, cache_enabled=1, postclean_validated=1,
                 fnv_before=FRAME_FNV, fnv_after=FRAME_FNV, postclean_fnv=FRAME_FNV,
                 buffer_address=0x34326be0, buffer_bytes=32768,
                 stack_canary=0x5354414b, initial_msplim=0x343a0000)
    for key, expected in exact.items():
        require(report.get(key) == expected, 'Invalid successful SAVE field: '+key)
    require(report['nonce'] == 0 if automatic else 0 < report['nonce'] < 2**32,
            'Automatic/explicit SAVE nonce mismatch')
    require(not report['ccr'] & 0x30000 and not report['final_ccr'] & 0x30000 and
            not report['initial_mpu_ctrl'] & 1, 'Cache or MPU proof differs')
    require(report['complete'] >= report['total'] > 0 and report['stack_used'] <= 65536,
            'Invalid timing/stack proof')
    require(0 < report['png_bytes'] <= 3100000 and
            re.fullmatch(r'IMG\d{5}\.PNG', report['name']), 'Invalid saved object')
    require(not card['error'] and not card['cleanup_error'] and card['media_idle'] == 1 and
            not card['initialized'] and not card['controller_owned'], 'SD not quiescent')
    require(not filesystem['fat_result'] and filesystem['completed'] == 1 and
            filesystem['bytes_written'] == report['png_bytes'] and
            filesystem['final_name'] == report['name'], 'Filesystem completion mismatch')
    if not automatic:
        request = proof['request']
        require(all(request[key] == report[key] for key in ('operation', 'mode', 'nonce')),
                'Stale SAVE report/request')
        require(request['sd_clock_hz'] == 25000000 and not request['offset'] and
                not request['length'] and not request['name'], 'Not a bare SAVE request')
        require(all(proof[key] is False for key in
                    ('reset_sent', 'power_changed', 'nor_commands_sent')), 'Unexpected hardware action')
        context = proof['final_context']
        registers = context['registers']
        require(registers['PC'] == 0x3432006e and registers['CONTROL'] == 0 and
                registers['PRIMASK'] == 1 and registers['FAULTMASK'] == 0 and
                registers['XPSR'] & 0x01000000 and not registers['XPSR'] & 511 and
                not context['ccr'] & 0x30000 and not context['fpccr'] & 1,
                'Missing final exact RAM park/context')
    return report


def verify_calls(build):
    receiver = (build/'receiver/capture.c').read_text(encoding='utf-8')
    save = (build/'module/save_main.c').read_text(encoding='utf-8')
    led = (build/'receiver/sleep.c').read_text(encoding='utf-8')
    require(sorted(map(int, re.findall(r'phase_gpio_emit\((\d+)U\)', receiver))) == [1, 2, 3],
            'Different receiver marker calls')
    require(sorted(map(int, re.findall(r'phase_gpio_emit\((\d+)U\)', save))) == [4, 5, 6, 7, 8, 9],
            'Different module marker calls')
    require(re.findall(r'phase_gpio_emit\((\d+)U\)', led) == ['10'], 'Different awake final marker')
    require('if(fast_strobes==1U)' in receiver and 'if(frames==1U)' in receiver,
            'First-event guards absent')
    image = save[save.index('static int save_image('):save.index('int save_main(')]
    require(image.index('if(png_result) return png_result;') < image.index('phase_gpio_emit(7U)') <
            image.index('result=flush_buffer()'), 'Encode checkpoint moved')
    require(image.index('result=photo_fs_finish()') < image.index('phase_gpio_emit(8U)') <
            image.index('report[P_FNV_AFTER]'), 'File checkpoint moved')
    require(save.index('SCB_DisableDCache()') < save.index('uint32_t value=frame_fnv();') <
            save.index('phase_gpio_emit(9U)') < save.index('pair(P_COMPLETE_LO') <
            save.index('report[P_TERMINAL]'), 'Final validation/publication moved')
    require('if(op==SAVE_OP_SAVE && !result) (void)phase_gpio_emit(9U);' in save,
            'Final checkpoint is not SAVE-success-only')
    return dict(reviewed_calls=True, receiver_ids=[1, 2, 3], save_ids=[4, 5, 6, 7, 8, 9],
                awake_ids=[10], note='Source hash identity is frozen; labels remain inferred.')


def analyze(folder):
    folder = folder.resolve()
    for item in read_json(folder/'inputs.json'):
        path = (folder/item['archived_path']).resolve()
        require(path.is_relative_to(folder), 'Input escapes archive')
        raw = path.read_bytes()
        require(len(raw) == item['bytes'] and sha(raw) == item['sha256'], 'Input changed: '+str(path))
    load_module('v60_build_verify', ARCHIVE/'verify_build.py').verify(ARCHIVE)
    build = ARCHIVE/'build/v60c-awake'
    require(sha((build/'staged/capture_sector_0.bin').read_bytes()) == SECTOR,
            'Different frozen v60 sector')
    module = (build/'module/save.bin').read_bytes()
    require(sha(module) == MODULE, 'Different frozen module')
    context = read_json(folder/'context.json')
    sequence = context['sequence']
    require(sequence in ('cold', 'storage'), 'Unknown analysis sequence')
    require(context['sector_sha256'] == SECTOR and context['frame_sha256'] == FRAME_SHA,
            'Context is not this exact v60/frame')
    frame = read_json(folder/'frame-metadata.json')
    require(frame['completed'] and frame['image_integrity_matches'] and
            frame['zero_camera_errors'] and frame['stage'] == 40 and
            not frame['result'] and not frame['camera_error'] and not frame['errors'] and
            frame['width'] == 1120 and frame['height'] == 1364 and
            frame['frame_bytes'] == 3055360 and frame['fnv1a'] == FRAME_FNV and
            frame['host_image']['sha256'] == FRAME_SHA and
            frame['host_image']['fnv1a'] == FRAME_FNV,
            'Captured RAW metadata is not this retained successful input')
    original = read_json(folder/'strict-width-summary.json')
    require(original['sequence'] == sequence, 'Strict decode sequence differs')
    parser = load_module('v60_frozen_parser', ARCHIVE/'support/phase_markers/decode.py')
    channels = {n: parser.read_digital(folder/'binary'/f'digital_{n}.bin') for n in (0, 1, 4, 6)}
    if sequence == 'cold':
        require((folder/'nor-readback.bin').read_bytes() == (build/'staged/capture_sector_0.bin').read_bytes(),
                'Independent NOR readback differs')
        require(read_json(folder/'nor-read-result.json') ==
                dict(bytes=65536, offset=0, sha256=SECTOR, read_only=True), 'NOR read metadata differs')
        maintenance = read_json(folder/'maintenance-result.json')
        proof = maintenance['storage_proof']
        require(proof['recognized'] and proof['automatic_save'], 'No automatic SAVE proof')
        report = verify_save(proof, True)
        require((folder/'live-module.bin').read_bytes() == module, 'Live automatic module differs')
        loader = proof['loader_words']
        require(loader[0] == 0x534c4431 and loader[8] == len(module) and loader[7] == zlib.crc32(module)
                and loader[9] and not loader[10] and loader[11], 'Automatic loader not complete')
        result = infer(channels)
        result['events'][-1]['inferred_checkpoint'] = 'Awake diagnostic completion checkpoint'
    else:
        proof = read_json(folder/'bench-result.json')
        report = verify_save(proof, False)
        require((folder/'loaded-module.bin').read_bytes() == module, 'Loaded RAM code differs')
        request = struct.unpack('<6I16s6I', (folder/'request-readback.bin').read_bytes())
        require(request[:6] == (0x53525131, 1, 1, 25000000, 0, 0) and
                request[6] == bytes(16) and request[7] == report['nonce'] and
                request[8:] == (0, 0, 0, 0, 0), 'Request readback differs')
        capture = read_json(folder/'capture-config.json')
        times = proof['host_timing']
        require(capture['capture_mode'] == 'manual' and capture['module_sha256'] == MODULE and
                capture['reset_sent'] is False and capture['power_switch_sent'] is False and
                capture['bench_returncode'] == 0, 'Recording wrapper did not complete this SAVE')
        require(capture['started']['monotonic_ns'] <= times['run_before']['monotonic_ns'] and
                times['polls'][-1]['after']['monotonic_ns'] <= capture['stopped']['monotonic_ns'],
                'Host run/report brackets do not fit within this capture')
        result = infer_storage(channels)
    report_raw = (folder/'report.bin').read_bytes()
    require(report_raw == struct.pack('<128I', *report['raw_words']), 'Raw terminal report differs')
    fields = '''magic schema words state operation mode result stage begin end cpu_hz
        buffer_address buffer_bytes read_bytes sd_hz ccr total_lo total_hi encode_lo
        encode_hi callback_lo callback_hi finish_lo finish_hi init_lo init_hi mount_lo
        mount_hi validate_lo validate_hi stack_used stack_canary rows idat_chunks
        callbacks buffer_flushes png_bytes_lo png_bytes_hi fnv_before fnv_after width
        height frame_bytes media_idle card_error fs_result fs_stage png_result card_size
        fs_size nonce initial_msplim'''.split()
    cache_fields = '''cache_enabled initial_mpu_ctrl final_ccr cleanup_lo cleanup_hi
        postclean_validate_lo postclean_validate_hi complete_lo complete_hi postclean_fnv
        postclean_validated'''.split()
    raw_fields = dict(zip(fields, report['raw_words']))
    raw_fields.update(zip(cache_fields, report['raw_words'][68:79]))
    raw_fields.update(terminal=report['raw_words'][63],
                      name=report_raw[256:272].split(b'\0', 1)[0].decode('ascii'))
    require(all(report[key] == value for key, value in raw_fields.items()),
            'Decoded report fields differ from actual words')
    for field in ('total', 'encode', 'callback', 'finish', 'init', 'mount', 'validate',
                  'png_bytes', 'cleanup', 'postclean_validate', 'complete'):
        value = raw_fields[field+'_lo'] | raw_fields[field+'_hi'] << 32
        require(report[field] == value, 'Decoded 64-bit report differs')
        if field != 'png_bytes':
            require(report[field+'_ms'] == value*1000/400000000, 'Decoded timing differs')
    require(len(original['pulses']) == len(result['events']) and
            all(p['complete'] for p in original['pulses']), 'Strict parser pulse count/completeness differs')
    require([p['start_s'] for p in original['pulses']] ==
            [p['rising_edge_s'] for p in result['events']], 'Strict parser edges differ')
    require(all(original['input_files'][str(n)]['sha256'] == channel['sha256']
                for n, channel in channels.items()), 'Strict parser input hashes differ')
    result.update(schema=1, sequence=sequence, firmware_sector_sha256=SECTOR,
        module_sha256=MODULE, frame_sha256=FRAME_SHA, source_review=verify_calls(build),
        original_width_decode_passed=original['decode_passed'], image_integrity_verified=False,
        successful_save_report_verified=True, saved_name=report['name'], png_bytes=report['png_bytes'],
        target_complete_ms=report['complete_ms'], target_total_ms=report['total_ms'],
        limitations=[
            'Every phase label is inferred from source call order; pulse-width qualification remains false.',
            'No missing pulse is synthesized, and the original strict decoder result remains unchanged.',
            'Event 7 precedes any buffered-tail flush; event 9 precedes COMPLETE/terminal publication.',
            'Cold event 10 is an awake checkpoint, not Standby or WFI.',
            'Interrupt latency, marker execution and extra code loading perturb the path.',
            'A matching completed SAVE report does not itself verify stored PNG bytes; see separate readback evidence.',
            'Host monotonic brackets bind a storage operation to its recording window, not cross-instrument sample clocks.',
            'No Joulescope/Saleae synchronization or phase-specific energy is inferred.'],
        input_files={str(n): dict({k: v for k, v in channel.items() if k not in ('path', 'transitions')},
                                 path=f'binary/digital_{n}.bin') for n, channel in channels.items()})
    return result


def table(result):
    cold = result['sequence'] == 'cold'
    origin = 'NRST release' if cold else 'inferred SAVE entry'
    lines = ['# v60c ordered-edge timing', '',
        '**All checkpoint labels are inferred from source call order. Width qualification remains false.**', '',
        f"Successful SAVE evidence: `{result['saved_name']}`, {result['png_bytes']:,} bytes. "
        'PNG byte/pixel readback is separate from this timing analysis.', '',
        f'| Inferred event | Inferred checkpoint | Width (µs) | After {origin} (ms) | Since previous marker (ms) |',
        '| --- | --- | ---: | ---: | ---: |']
    for event in result['events']:
        previous = '—' if event['from_previous_marker_ms'] is None else f"{event['from_previous_marker_ms']:.6f}"
        value = event['from_reset_release_ms'] if cold else event['from_save_entry_ms']
        lines.append(f"| {event['inferred_event_id']} | {event['inferred_checkpoint']} | {event['width_us']:.3f} | {value:.6f} | {previous} |")
    lines += ['', 'These endpoint intervals are not isolated compression or card-programming costs. '
              'Event 9 is before terminal publication. Every original edge, width, and input hash remains in the JSON. '
              'No event or energy alignment to the independent Joulescope clock is asserted.', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    result = analyze(args.folder)
    (args.folder/'ordered-analysis.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    (args.folder/'timing.md').write_text(table(result), encoding='utf-8')
    print(json.dumps(dict(sequence=result['sequence'], width_qualification=False,
                         saved_name=result['saved_name'], pulses=result['complete_pulse_count']), indent=2))
