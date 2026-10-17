"""Run/read the RAM-only capture harness through bounded HOTPLUG AP1 calls.

Root bench owner only. Before `run`, cold boot the known awake marker image.
This program writes internal RAM only and never resets or changes target power.
An image's early debug opening is not a substitute for the cold-boot precondition.
The first cache-preparation helper is frozen and must have fresh instruction RAM.
`read` inspects an already-running autonomous capture without loading any code.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / 'firmware/boot-timing'))
from nor_bench import Bench

TRACE = 0x341F0000
EVENTS = 0x341F0100
CACHE = REPO / 'tmp/bringup/cache-prep-20261017/cache_prep.bin'
CACHE_SHA = 'bd34d1290a3e446aa3a01b99f2bc53707b12708eac92da1afabe6de50ea64dbf'
NAMES = ['magic', 'stage', 'event_count', 'result', 'camera_error',
         'frames', 'vsyncs', 'errors', 'minimum', 'maximum', 'sum', 'fnv1a',
         'frame_address', 'frame_bytes', 'width', 'height', 'entry_cfgr1',
         'entry_cfgr2', 'entry_ccr', 'debug_cr', 'debug_unlock']
LATE_PHY_ADDRESS = 0x343F8000
LATE_PHY_WORDS = 32 + 128 * 12
LATE_PHY_FIELDS = ['id', 'cycles', 'tick_ms', 'sr0', 'sr1', 'ier0', 'ier1',
                   'prcr', 'pcr', 'cr', 'lmcfgr', 'apb5rstr']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def late_phy_region(manifest):
    """Permit only the reviewed v30 snapshot layout, never a manifest RAM range."""
    expected = dict(late_phy_status_address='0x343f8000', late_phy_status_words=1568,
                    late_phy_header_words=32, late_phy_record_words=12,
                    late_phy_max_records=128, late_phy_status_schema=1)
    for key, value in expected.items():
        actual = manifest.get(key)
        if type(actual) is not type(value) or actual != value:
            raise ValueError(f'Unexpected late-PHY diagnostic layout: {key}')
    return LATE_PHY_ADDRESS, LATE_PHY_WORDS


def decode_late_phy(diagnostic):
    if len(diagnostic) != LATE_PHY_WORDS * 4:
        raise ValueError('Incomplete late-PHY diagnostic region')
    words = struct.unpack(f'<{LATE_PHY_WORDS}I', diagnostic)
    valid = words[0] == 0x4C505231 and words[2] <= 128 and words[6] in (0, 1)
    records = []
    if valid:
        for offset in range(32, 32 + words[2] * 12, 12):
            records.append(dict(zip(LATE_PHY_FIELDS, words[offset:offset + 12])))
    # Keep invalid/uninitialized header evidence too; do not turn it into a
    # valid empty history or discard diagnostics on a failed capture.
    return dict(late_phy_status_words=list(words), late_phy_header_valid=valid,
                late_phy_snapshots=records)


def inspect(bench, manifest, timeout):
    trace_address = int(manifest.get('trace_address', hex(TRACE)), 0)
    event_address = int(manifest.get('event_address', hex(EVENTS)), 0)
    error_address = int(manifest.get('error_address', '0x341f1000'), 0)
    prefix_address = int(manifest.get('prefix_status_address', '0x341f3000'), 0)
    late_region = late_phy_region(manifest) if 'late_phy_status_address' in manifest else None
    deadline = time.monotonic() + timeout
    for i in range(60):
        raw = bench.upload(trace_address, 256, f'trace-{i:02d}.bin')
        words = struct.unpack('<64I', raw)
        if words[0] == 0x43545031 and (words[1] == 40 or words[1] & 0x80000000):
            break
        if time.monotonic() > deadline:
            break
        time.sleep(.2)
    summary = dict(zip(NAMES, words))
    summary['words'] = list(words)
    summary['build_sha256'] = manifest['raw_sha256']
    summary['completed'] = words[0] == 0x43545031 and words[1] == 40
    for key, count in [('memory_status_address', 32), ('raw10_status_address', 10)]:
        if key in manifest:
            diagnostic = bench.upload(int(manifest[key], 0), count * 4,
                                      key.replace('_address', '') + '.bin')
            summary[key.replace('_address', '_words')] = list(struct.unpack(f'<{count}I', diagnostic))
    if 'timer_status_address' in manifest:
        timer_words = manifest.get('timer_status_words')
        if (manifest['timer_status_address'].lower() != '0x343f7000'
                or not isinstance(timer_words, int) or not 32 <= timer_words <= 256):
            raise ValueError('Unexpected timer diagnostic region')
        diagnostic = bench.upload(0x343F7000, timer_words * 4, 'timer-status.bin')
        summary['timer_status_words'] = list(struct.unpack(f'<{timer_words}I', diagnostic))
    if late_region:
        address, count = late_region
        summary.update(decode_late_phy(bench.upload(address, count * 4, 'late-phy-status.bin')))
    if summary['completed'] and manifest.get('parameters', {}).get('stage2'):
        prefix = bench.upload(prefix_address, 256, 'prefix-status.bin')
        summary['prefix_status_words'] = list(struct.unpack('<64I', prefix))
    count = min(words[2], 200) if words[0] == 0x43545031 else 0
    if count:
        raw_events = bench.upload(event_address, count * 16, 'events.bin')
        summary['events'] = [dict(zip(['id', 'cycles', 'tick_ms', 'core_hz'], record))
                             for record in struct.iter_unpack('<4I', raw_events)]
        # DWT crosses a clock transition. Only constant-frequency adjacent
        # intervals can be converted directly; external markers anchor others.
        for previous, current in zip(summary['events'], summary['events'][1:]):
            if previous['id'] >= 3 and previous['core_hz'] == current['core_hz'] and current['core_hz']:
                current['since_previous_us'] = ((current['cycles'] - previous['cycles']) & 0xffffffff) * 1e6 / current['core_hz']
    if words[0] == 0x43545031 and words[36]:
        count_errors = min(words[36], 16)
        error_width = words[38] or 8
        if error_width not in (8, 12):
            raise ValueError('Unknown error record width')
        raw_errors = bench.upload(error_address, count_errors * error_width * 4, 'error-events.bin')
        fields = ['id', 'cycles', 'tick_ms', 'error', 'csi_sr0', 'csi_sr1', 'cmsr2',
                  'previous_stage', 'ier0_entry', 'ier1_entry', 'ier0_callback', 'ier1_callback']
        summary['error_events'] = [dict(zip(fields, record))
                                   for record in struct.iter_unpack(f'<{error_width}I', raw_errors)]
    if summary['completed']:
        bytes_per_pixel = manifest.get('bytes_per_pixel', 1)
        if bytes_per_pixel not in (1, 2):
            raise ValueError('Unsupported frame memory layout')
        if (words[12] != int(manifest['frame_address'], 16)
                or words[13] != manifest['frame_bytes']
                or words[14] * words[15] * bytes_per_pixel != words[13]):
            raise ValueError('Firmware frame geometry differs from the build manifest')
        (bench.output / 'capture-result.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
        pixels = bench.upload(words[12], words[13], 'frame.bin')
        fnv = 2166136261
        for value in pixels:
            fnv = ((fnv ^ value) * 16777619) & 0xffffffff
        summary['host_image'] = dict(sha256=sha(pixels), minimum=min(pixels),
                                     maximum=max(pixels), sum=sum(pixels), fnv1a=fnv)
        summary['image_integrity_matches'] = (fnv == words[11] and sum(pixels) == words[10]
                                               and min(pixels) == words[8] and max(pixels) == words[9])
        summary['zero_camera_errors'] = words[4] == 0 and words[7] == 0
        summary['visual_qualification'] = 'pending human/model inspection; statistics alone do not prove a valid image'
        from PIL import Image
        if bytes_per_pixel == 1:
            Image.frombytes('L', (words[14], words[15]), pixels).save(bench.output / 'frame.png')
        else:
            if (manifest.get('pixel_format') != 'raw10_le16'
                    or manifest.get('sample_alignment') != 'right'):
                raise ValueError('Require explicitly described right-aligned RAW10 words')
            import numpy as np
            samples = np.frombuffer(pixels, dtype='<u2').reshape(words[15], words[14])
            summary['sample_statistics'] = dict(minimum=int(samples.min()), maximum=int(samples.max()),
                invalid_upper_bits=int(np.count_nonzero(samples & 0xfc00)),
                low_two_bits_histogram=np.bincount((samples & 3).ravel(), minlength=4).tolist())
            if summary['sample_statistics']['invalid_upper_bits']:
                raise ValueError('RAW10 padded words have nonzero upper six bits')
            Image.fromarray(samples).save(bench.output / 'frame-16bit.png')
            Image.fromarray((samples >> 2).astype('uint8')).save(bench.output / 'frame.png')
            summary['preview_conversion'] = 'RAW10 >> 2; fixed full-scale display, no adaptive gain'
    (bench.output / 'capture-result.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))
    if not summary['completed']:
        raise RuntimeError('Capture did not complete; preserved diagnostics, no reset or retry')
    if not summary.get('image_integrity_matches'):
        raise RuntimeError('Host frame differs from MCU checksum/statistics')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=['run', 'read'])
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--timeout', type=float, default=12)
    a = p.parse_args()
    manifest = json.loads((a.build / 'manifest.json').read_text(encoding='utf-8-sig'))
    payload = a.build / 'capture.bin'
    if sha(payload.read_bytes()) != manifest['raw_sha256']:
        raise ValueError('Payload changed since manifest creation')
    stack, entry = struct.unpack_from('<2I', payload.read_bytes())
    vector = int(manifest['vector_address'], 16)
    limits = {0x34180400: (0x34190000, 0x341B0000),
              0x34190000: (0x341A0000, 0x341B0000),
              0x34300000: (0x343A0000, 0x343B0000)}
    if vector not in limits:
        raise ValueError('Unknown memory layout')
    code_limit, stack_limit = limits[vector]
    if (entry != int(manifest['entry_point'], 16) or not entry & 1
            or not vector <= (entry & ~1) < vector + payload.stat().st_size
            or vector + payload.stat().st_size > code_limit
            or stack != int(manifest['stack_pointer'], 16) or stack > stack_limit
            or stack <= vector + payload.stat().st_size):
        raise ValueError('Payload vectors or bounds conflict with manifest/maintenance regions')
    bench = Bench(a.out)
    if a.operation == 'run':
        if vector != 0x34180400:
            raise ValueError('Staged image must be launched through its prefix, not this RAM runner')
        if sha(CACHE.read_bytes()) != CACHE_SHA:
            raise ValueError('Cache helper differs from reviewed immutable revision')
        # Check the expected ROM-clock baseline before replacing any code.
        clock = bench.upload(0x56028020, 8, 'entry-clock.bin')
        if struct.unpack('<2I', clock) != (0x33330000, 0x00100000):
            raise ValueError('Not the expected fresh ROM-clock baseline; cold boot first')
        context = bench.call('-halt', '-coreReg')
        registers = dict((name, int(value, 16)) for name, value in
                         re.findall(r'^(XPSR|CONTROL|FAULTMASK)\s*=\s*0x([0-9A-Fa-f]+)', context, re.M))
        if (registers.get('XPSR', 0x1ff) & 0x1ff or registers.get('CONTROL') != 0
                or registers.get('FAULTMASK') != 0):
            raise RuntimeError('Expected privileged thread mode with no fault mask; left halted')
        clear_cache = bench.output / 'clear-cache.bin'
        clear_cache.write_bytes(bytes(20))
        clear_trace = bench.output / 'clear-trace.bin'
        clear_trace.write_bytes(bytes(256))
        bench.call('-halt', '-w', clear_cache, '0x34190400', '-v',
                   '-w', CACHE, '0x34190000', '-v',
                   '-coreReg', 'PC=0x34190001', 'XPSR=0x01000000', '-run', success='Core run')
        cache = struct.unpack('<5I', bench.upload(0x34190400, 20, 'cache-status.bin'))
        if cache[0] != 0x43414348 or cache[3] or cache[4] & 0x30000:
            raise RuntimeError('Cache preparation failed; target left for diagnosis')
        bench.call('-halt', '-w', clear_trace, hex(TRACE), '-v',
                   '-w', payload.resolve(), '0x34180400', '-v',
                   '-coreReg', 'PC=' + manifest['entry_point'], 'XPSR=0x01000000',
                   '-run', success='Core run')
    inspect(bench, manifest, a.timeout)


if __name__ == '__main__':
    main()
