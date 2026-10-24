"""Replay v60 timing arithmetic from archived records; no hardware access.

Every subtraction uses one v60 target DWT time base at the reported 400 MHz.
No Saleae, Joulescope, v61, or host timestamp is used in this arithmetic.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zlib

HERE = Path(__file__).resolve().parent
ARCHIVE = HERE.parent
HZ = 400000000
SECTOR = '20444827100b1a33826c5b7e3362a396a0ce31f27f0c3db7fea12fb755320f7e'
MODULE = '51c067de2859588fc87cf1249fdff4186b17a4e0ab85585c72fc9b5dc94379f5'


def sha(raw): return hashlib.sha256(raw).hexdigest()
def load(path): return json.loads(path.read_text(encoding='utf-8-sig'))
def require(value, message):
    if not value: raise ValueError(message)
def ms(cycles): return cycles*1000/HZ


def analyze():
    inputs = load(HERE/'inputs.json')
    for item in inputs:
        path = (ARCHIVE/item['path']).resolve()
        require(path.is_relative_to(ARCHIVE.resolve()), 'Input path escaped archive')
        raw = path.read_bytes()
        require(len(raw) == item['bytes'] and sha(raw) == item['sha256'], 'Input changed: '+item['path'])
    capture = load(ARCHIVE/'phase/v60-cycle-01/capture-result.json')
    maintenance = load(ARCHIVE/'phase/v60-cycle-01/maintenance-result.json')
    metrics = load(ARCHIVE/'automatic-save-v60/metrics.json')
    proof = maintenance['storage_proof']
    report = proof['report']; loader = proof['loader_words']
    module = (ARCHIVE/'build/v60c-awake/module/save.bin').read_bytes()
    require(sha((ARCHIVE/'build/v60c-awake/staged/capture_sector_0.bin').read_bytes()) == SECTOR,
            'Different v60 sector')
    require(sha(module) == proof['module_sha256'] == metrics['module_sha256'] == MODULE,
            'Different SAVE module')
    require(capture['completed'] and capture['image_integrity_matches'] and
            capture['zero_camera_errors'] and capture['stage'] == 40 and
            not capture['result'] and not capture['camera_error'] and not capture['errors'],
            'Capture was not successful')
    require(not capture['entry_ccr'] & 0x10000 and not report['ccr'] & 0x10000,
            'Receiver/SAVE entry had D-cache enabled')
    require(proof['recognized'] and proof['automatic_save'] and report['operation'] == 1 and
            report['nonce'] == 0 and report['state'] == 2 and report['result'] == 0 and
            report['terminal'] == 0x444f4e45 and report['cpu_hz'] == HZ and
            report['media_idle'] == 1 and not report['card_error'] and not report['fs_result'],
            'No successful automatic SAVE proof')
    require(loader[0] == 0x534c4431 and loader[8] == len(module) and
            loader[7] == zlib.crc32(module) and loader[9] and not loader[10] and loader[11],
            'Loader completion/code identity differs')
    require(report['frame_bytes'] == capture['frame_bytes'] == metrics['frame_bytes'] == 3055360 and
            report['fnv_before'] == report['fnv_after'] == report['postclean_fnv'] == capture['fnv1a'] and
            report['postclean_validated'] == 1 and report['cache_enabled'] == 1 and
            not report['final_ccr'] & 0x30000, 'Frame/cache proof differs')
    require(report['name'] == metrics['image_name'] == 'IMG00061.PNG' and
            report['png_bytes'] == metrics['png_bytes'], 'Different saved object')
    events = {}
    for event_id in (30, 31, 442, 443, 40):
        matched = [event for event in capture['events'] if event['id'] == event_id]
        require(len(matched) == 1 and matched[0]['core_hz'] == HZ,
                'Missing, repeated, or differently clocked event '+str(event_id))
        events[event_id] = matched[0]['cycles']
    points = [
        ('frame_irq_event30', events[30]),
        ('frame_wait_complete_event31', events[31]),
        ('before_data_disable_event442', events[442]),
        ('after_data_disable_event443', events[443]),
        ('capture_complete_event40', events[40]),
        ('loader_start_word1', loader[1]),
        ('loader_read_crc_complete_word9', loader[9]),
        ('save_report_begin', report['begin'])]
    require(all(a[1] < b[1] for a, b in zip(points, points[1:])), 'DWT chain not strictly increasing')
    descriptions = [
        'First complete-frame IRQ bookkeeping to main-loop acknowledgement.',
        'Post-frame register/RAW10 checks, thirteen sensor read transactions, pipe stop, and data-disable setup.',
        'Guarded CSI data disable and its diagnostic bookkeeping.',
        'Sensor STOP command/ack/SW_STBY wait, then the entire receiver bytewise min/max/sum/FNV scan; exact split unavailable.',
        'Capture-complete event bookkeeping and call into the loader.',
        'Finite NOR read of 27,576 bytes with interleaved software CRC and completion checks.',
        'Disable I-cache, enter SAVE, fill unused stack canary, zero 300,472-byte BSS, and initialize the report.']
    intervals = [dict(start=a[0], end=b[0], cycles=b[1]-a[1], milliseconds=ms(b[1]-a[1]),
                      scope=description)
                 for (a, b), description in zip(zip(points, points[1:]), descriptions)]
    first_total = report['begin']-events[30]
    require(sum(interval['cycles'] for interval in intervals) == first_total,
            'Frame-to-SAVE intervals do not sum exactly')
    # Each duration is reconstructed from the report's two raw 32-bit fields.
    for field in ('total', 'complete', 'encode', 'callback', 'finish', 'init', 'mount',
                  'validate', 'cleanup', 'postclean_validate'):
        cycles = report[field+'_lo'] | report[field+'_hi'] << 32
        require(report[field] == cycles and metrics['seconds'][field] == cycles/HZ,
                'Report/metrics duration mismatch: '+field)
    require(report['callback'] <= report['encode'], 'Callback exceeds encoder scope')
    legacy_residual = report['total']-sum(report[key] for key in ('init','mount','validate','encode','finish'))
    final_residual = report['complete']-report['total']-report['cleanup']-report['postclean_validate']
    require(legacy_residual >= 0 and final_residual >= 0, 'Negative disjoint timing residual')
    terms = [
        ('sd_init', report['init'], 'Measured card initialization scope.'),
        ('fat32_mount', report['mount'], 'Measured mount scope.'),
        ('initial_cached_frame_validation', report['validate'], 'Frame guards and initial FNV with D-cache enabled.'),
        ('encoder_excluding_callbacks', report['encode']-report['callback'],
         'Encoder wall time minus nested output callbacks; not an independently instrumented compressor-only interval.'),
        ('encoder_output_callbacks', report['callback'],
         'Nested output copies/buffering and synchronous filesystem writes; already included in the original encoder scope.'),
        ('final_buffer_and_file_finish', report['finish'],
         'Remaining buffered tail, file close/sync/rename/card-ready, and checkpoint bookkeeping.'),
        ('other_legacy_total', legacy_residual,
         'Untimed file open/name search/allocation, cached post-write FNV, SD deinit, snapshots, setup, and timing overhead. Cannot assign wholly to file creation.'),
        ('data_cache_cleanup', report['cleanup'], 'Measured owned D-cache clean/invalidate/disable scope.'),
        ('final_uncached_frame_validation', report['postclean_validate'], 'Fresh full-frame FNV after D-cache is disabled.'),
        ('other_after_legacy_total', final_residual,
         'Stack watermark scan, final snapshots/LED/cache state, event 9, and accounting/publication-preparation overhead.')]
    require(sum(value for _, value, _ in terms) == report['complete'], 'Disjoint SAVE terms do not equal COMPLETE')
    receiver = (ARCHIVE/'build/v60c-awake/receiver/capture.c').read_text(encoding='utf-8')
    require(receiver.index('fast_snapshot(436);') < receiver.index('for (unsigned i=0;i<BYTES;++i)') <
            receiver.index('fast_snapshot(440);'), 'Receiver scan placement differs')
    require(receiver.index('check(33, VD6G_Stop(&sensor));') < receiver.index('fast_snapshot(436);'),
            'Sensor STOP boundary changed')
    return dict(schema=1, scope='Single v60c automatic cold-capture/SAVE DWT audit',
        firmware_sector_sha256=SECTOR, module_sha256=MODULE, image_name=report['name'],
        png_bytes=report['png_bytes'], frame_bytes=report['frame_bytes'],
        time_base=dict(kind='target DWT', nominal_hz=HZ, assumption='Reported 400 MHz; no external calibration applied',
                       uses_cross_clock_arithmetic=False, uses_host_timestamps=False,
                       uses_saleae_timestamps=False, uses_joulescope_timestamps=False, uses_v61_data=False),
        frame_to_save=dict(points=[dict(name=name, cycle=cycle) for name, cycle in points],
                           intervals=intervals, sum_cycles=first_total, sum_milliseconds=ms(first_total),
                           receiver_scan_bytes=3055360, receiver_scan_data_cache_enabled=False,
                           module_bss_bytes=300472, loader_bytes=len(module)),
        automatic_save=dict(disjoint_terms=[dict(name=name, cycles=value, milliseconds=ms(value), scope=scope)
                                            for name, value, scope in terms],
                            sum_cycles=report['complete'], sum_milliseconds=ms(report['complete']),
                            legacy_total_cycles=report['total'], legacy_total_milliseconds=ms(report['total']),
                            encoder_inclusive_cycles=report['encode'], callback_is_nested=True,
                            driver_write_cycles=proof['card']['write_cycles'],
                            driver_ready_cycles=proof['card']['ready_cycles'],
                            driver_counters_additive_with_terms=False),
        missing_evidence=dict(fast_buffer_address='0x343F8000',
            unavailable_snapshot_ids=[431,435,439,436,440],
            adjacent_regular_event_for_snapshot431=31,
            reason='The v60 acquisition persisted regular TRACE/events but not the separate FAST buffer.',
            exact_sensor_stop_duration_available=False, exact_receiver_statistics_scan_duration_available=False,
            exact_file_open_duration_available=False, exact_cached_postwrite_fnv_duration_available=False),
        limits=[
            'The 435.517570 ms bracket combines sensor STOP and the receiver statistics/FNV loop; neither gets an invented separate duration.',
            'Late STROBE IRQ events are not treated as proof that sensor STOP returned.',
            'The final raw-frame FNV verifies retained input RAM, not a readback of the PNG on the card.',
            'Driver ready polling overlaps command/read/write scopes and is not additive or pure card-program time.',
            'The encoder inclusive duration contains callbacks; this audit subtracts them before summing disjoint terms.',
            'COMPLETE is before final terminal publication/return; frame-to-SAVE initialization is outside it.',
            'No v60-to-v61 or instrument-clock subtraction is performed.'],
        evidence_inputs=inputs)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Write the derived audit; does not modify any input')
    args = parser.parse_args()
    result = analyze()
    output = HERE/'phase-audit.json'
    if args.write:
        output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    else:
        require(result == load(output), 'Derived audit does not replay exactly')
    print(json.dumps(dict(passed=True, input_files_verified=len(result['evidence_inputs']),
                         frame_to_save_ms=result['frame_to_save']['sum_milliseconds'],
                         save_complete_ms=result['automatic_save']['sum_milliseconds'],
                         exact_stop_scan_split_available=False, uses_cross_clock_arithmetic=False), indent=2))
