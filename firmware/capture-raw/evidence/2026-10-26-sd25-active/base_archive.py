"""Offline independent verification and evidence freezing for the 20-image run.

No instrument, debugger, serial, power, subprocess, or network API is used.
`inspect` accepts an incomplete campaign. `freeze` refuses an incomplete or
failed campaign unless --allow-incomplete is explicit; neither can label fewer
than twenty independently verified images complete. Private image/snapshot bytes
are compared locally and represented in the public bundle only by hashes.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import statistics
import struct

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SOURCE = ROOT / 'tmp/bringup/sd25-stress-20261026'
BUILD_SHA = {
    'ram25-scene': '30c6a539a506a1b5ec963c382f190987aef6f8f68a0baa2e533c70a1a651b866',
    'ram25-long': '92e8a57126a02982bd7df3b37f3aeadac515dcfededdb457de158e1306b3ee08',
    'ram25-pattern': '1f7d3b157e058068f17fc42243ee3c6179b1b737d9909edb8550e4ff24583933',
}
NOR_SHA = 'c03e40c8ceea09bd9c171c179f2191a1ef9799c9e615db979a84b9c53ad66010'
PREFIX_SHA = '4ef99d3b0b8ac7b790265cd1994428a5804dd3a20ad5587dd1585d2544a74b0b'
IDENTITY = ('sector_count', 'cid0', 'cid1', 'cid2', 'cid3', 'csd0', 'csd1', 'csd2', 'csd3', 'ocr')
FRAME_BYTES, SLOT_BYTES, SECTORS, HZ = 1909600, 1909760, 3730, 400000000
ERROR_MASK = 0xFDFFE008


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def bound(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=digest(raw))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def build_for(number):
    return 'ram25-long' if 9 <= number <= 12 else 'ram25-scene'


def ms(cycles):
    return cycles / (HZ / 1000)


def delta(start, end):
    return ms((end - start) & 0xFFFFFFFF)


def check_build(folder, name):
    m = read(folder / 'manifest.json')
    code = (folder / 'capture.bin').read_bytes()
    require(m['binary_sha256'] == digest(code) == BUILD_SHA[name], 'Build identity changed: ' + name)
    for rel, expected in m['source_hashes'].items():
        source = (folder / rel).resolve()
        source.relative_to(folder.resolve())
        require(digest(source.read_bytes()) == expected, 'Build source changed: ' + rel)
    expected = dict(flash=False, standby=False, pattern=int(name == 'ram25-pattern'), sd_bus_width=4,
        sd_clock_hz=25000000, sd_gpio_speed=3, sd_clock_negedge=True,
        sd_clock_negedge_init=True, sd_review_profile=True, sd_startup_opt=True,
        sd_early_run_clock=False, sd_high_speed=False, sd_idma_read=False,
        sd_fixed_compensation=False, sd_compensation_modified=False,
        raw_dma_tail_wait=False, dma_sleep=False, magic_format=True,
        magic_layout_version=2, image_offset=156, metadata_bytes=152,
        line_stream=True, async_stop=True, transport='idma',
        exposure_coarse=30000 if name == 'ram25-long' else 1428,
        line_snapshots=name == 'ram25-long', line_poison=name == 'ram25-long')
    require(all(m.get(k) == v and type(m.get(k)) is type(v) for k, v in expected.items()),
            'Unexpected campaign profile: ' + name)
    require(bool(m.get('cycle_trace')), 'Cycle trace is not enabled')
    require('-DRAW_SD_CLOCK_HZ=25000000U' in m['flags'], 'Clock compiler flag missing')
    return m


def check_proof(v, m, operation, identity=None):
    p, c, q = v['proof'], v['card'], v['request_words']
    require(v.get('passed') is True and v['binary_sha256'] == m['binary_sha256'], 'Operation identity/result differs')
    require(len(q) == 16 and q[0] == 0x52535131 and q[1] == p['nonce'] and q[1] != 0
            and q[2] == operation and not any(q[6:]), 'Request/nonce differs')
    expected = dict(magic=0x52535731, schema=1, words=96, operation=operation,
        state=3, result=0, stage=8, terminal=0x5253444E, clock_hz=25000000,
        media_idle=1, initialized=0, controller_owned=0, cleanup_error=0, sd_error=0,
        control=0, ipsr=0, primask=1, completion=0, frame=0x340000A0, bytes=FRAME_BYTES,
        width=1120, height=1364, flags=m['expected_flags'], transport=1,
        chunk_sectors=3730, pattern=m['pattern'])
    require(all(p.get(k) == value for k, value in expected.items()), 'Terminal/context proof differs')
    require(not p['ccr'] & 0x30000 and not p['fpccr'] & 1 and not p['systick'] & 3,
            'Caches/FP/SysTick active at terminal')
    require(v['context']['registers']['PC'] == m['park'], 'Terminal PC differs')
    require(all(c[k] == 0 for k in ('error', 'error_stage', 'error_command', 'error_sta',
                'cleanup_error', 'controller_owned', 'initialized', 'timer_owned'))
            and c['media_idle'] == 1 and c['stage'] == 9 and c['clock_hz'] == 25000000,
            'Card error, clock or ownership differs')
    require(c['last_ready_r1'] & 0x1F00 == p['last_ready'] & 0x1F00 == 0x900
            and not c['last_ready_r1'] & ERROR_MASK, 'Card is not error-free READY/TRAN')
    require(c['read_sectors'] == (p['card_read_hi'] << 32 | p['card_read_lo'])
            and c['written_sectors'] == (p['card_write_hi'] << 32 | p['card_write_lo']),
            'Card/terminal sector counts differ')
    w = c['bus_width_proof']
    require(w['requested_width'] == w['negotiated_width'] == 4 and w['scr_widths'] & 5 == 5
            and w['acmd6_accepted'] == 1 and not w['acmd6_r1'] & ERROR_MASK
            and w['acmd6_r1'] & 0x20 and w['configured_clkcr'] == 0x34003,
            'Four-bit 25 MHz falling-launch proof differs')
    s = c['startup_proof']
    require(s['magic'] == 0x31504F53 and s['version'] == 1 and s['train_hz'] == 100000
            and s['train_min_cycles'] == 400000 and s['gpio_settle_cycles'] >= 400000
            and s['train_cycles'] >= 400000 and s['run_settle_cycles'] >= 400
            and s['run_hz'] == 25000000 and s['scr_reads'] == 1
            and s['scr_hits'] == int(operation == 1)
            and not any(s[k] for k in ('scr_valid', 'cache_owner', 'result', 'reserved0', 'reserved1', 'reserved2')),
            'Startup/cache proof differs')
    current = {k: c[k] for k in IDENTITY}
    require(identity is None or current == identity, 'Card identity changed')
    if operation == 1:
        require(p['written_sectors'] == c['written_sectors'] == SECTORS and p['chunk_count'] == 1
                and not p['chunk_overflow'] and p['frames'] == 1
                and p['camera_ready'] == p['dma_bytes'] == FRAME_BYTES
                and not any(p[k] for k in ('errors', 'capture_error', 'canary')),
                'Capture/frame/slot counts differ')
        require(p['slot_count'] == c['sector_count'] // SECTORS and 0 <= p['slot'] < p['slot_count']
                and p['payload_lba'] == p['slot'] * SECTORS and p['scan_headers'] == p['slot'] + 1
                and c['read_sectors'] == p['scan_headers'] and not any(q[3:6]),
                'Slot geometry/allocation differs')
        stream = v['magic_format']['stream']
        require(stream['mode'] in (1, 2) and stream['published_bytes'] == stream['queued_bytes'] == SLOT_BYTES
                and not stream['producer_error'] and stream['publication_calls'] > 0
                and 512 <= stream['initial_available_bytes'] <= SLOT_BYTES
                and (stream['mode'] == 1) == (stream['initial_available_bytes'] == SLOT_BYTES),
                'Stream mode/publication proof differs')
    else:
        require(p['read_lba'] == q[3] and p['read_count'] == q[4] and 1 <= q[4] <= 512
                and p['read_bytes'] == q[4] * 512 and p['read_dest'] == 0x34200000
                and c['read_sectors'] == q[4] and not c['written_sectors'] and not p['camera_ready'],
                'Read extent/counter differs')
    return current


def trace_summary(folder, build, m):
    decoder = module('twenty_cycle_trace', ROOT / 'firmware/capture-raw/cycle_trace.py')
    headers = [build / name for name in ('cycle_trace_events.h', 'cycle_trace_sd.h')]
    hashes = {str(p): m['source_hashes'][p.name] for p in headers}
    definitions = decoder.load_definitions(headers, hashes)
    raw = (folder / 'trace/reads/cycle-trace.bin').read_bytes()
    t = decoder.decode(raw, definitions, require_complete=True)
    saved = read(folder / 'trace/cycle-trace.json')
    require(t['result'] == 0 and t['clock_hz'] == HZ and saved['sha256'] == digest(raw), 'Trace completion/hash differs')
    canonical = lambda v: [(x['id'], x['ticks']) for x in v['events']]
    require(canonical(t) == canonical(saved)
            and [(x['id'], x['value']) for x in t['counters']] == [(x['id'], x['value']) for x in saved['counters']],
            'Saved trace decoding differs from independent decode')
    e = {x['name']: x['ticks'] for x in t['events']}
    counters = {x['name']: x['value'] for x in t['counters']}
    for name in ('SD_INIT_CALLS', 'SD_WRITE_TRANSFERS', 'SD_PREANNOUNCE_CALLS', 'SD_CMD25_CALLS', 'SD_CMD12_WRITE_CALLS'):
        require(counters[name] == 1, 'Unexpected capture counter: ' + name)
    require(counters['SD_ERROR_CALLS'] == 0, 'Captured SD error counter nonzero')
    pairs = {
        'sd_init': ('SD_INIT_BEGIN', 'SD_INIT_DONE'),
        'acmd41_polling': ('SD_ACMD41_BEGIN', 'SD_ACMD41_DONE'),
        'slot_scan': ('SLOT_SCAN_BEGIN', 'SLOT_SCAN_DONE'),
        'slot_write': ('SLOT_WRITE_BEGIN', 'SLOT_WRITE_DONE'),
        'cmd25_data_envelope': ('SD_CMD25_DONE', 'SD_DATAEND'),
        'write_final_ready': ('SD_WRITE_FINAL_READY_BEGIN', 'SD_WRITE_FINAL_READY_DONE'),
        'runtime_to_terminal': ('RUNTIME_BEGIN', 'TERMINAL'),
    }
    durations = {k: delta(e[a], e[b]) for k, (a, b) in pairs.items() if a in e and b in e}
    durations['trace_init_to_completion'] = t['completion_since_init_ms']
    return dict(nominal_dwt_hz=HZ, header_hashes_independently_verified=True,
                durations_ms=durations, counters=counters, events=e)


def snapshots(folder, frame):
    raw = (folder / 'capture/producer.bin').read_bytes()
    require(len(raw) == 416, 'Producer telemetry length differs')
    p = struct.unpack('<104I', raw)
    require(p[:3] == (0x50524431, 1, 1) and p[4:8] == (1, 1, 0, FRAME_BYTES)
            and 21 <= p[3] <= 22 and p[15] == 20 and p[13] == 20 * 89600,
            'Long producer/snapshot count differs')
    data = (folder / 'capture/snapshots.bin').read_bytes()
    require(len(data) == 20 * 512, 'Long snapshot length differs')
    result = []
    for i in range(p[3]):
        require(p[16 + i * 2 + 1] == (min(i + 1, 21) - 1) * 89600, 'LINE publication watermark differs')
    for i in range(20):
        offset, length = p[64 + i * 2:66 + i * 2]
        chunk = data[i * 512:(i + 1) * 512]
        require((offset, length) == ((i + 1) * 89600 - 512, 512)
                and chunk == frame[offset:offset + 512], 'Immediate snapshot differs: ' + str(i))
        result.append(dict(offset=offset, bytes=length, sha256=digest(chunk)))
    return result


def verify_cycle(source, number, manifests, name_override=None):
    import numpy as np
    from PIL import Image
    folder = source / (f'cycle{number:02d}' if isinstance(number, int) else number)
    name = name_override or build_for(number)
    m = manifests[name]
    result = dict(run=number, present=folder.exists(), passed=False, status='not_started',
                  expected_build=name, binary_sha256=m['binary_sha256'])
    if not folder.exists():
        return result
    result['status'] = 'incomplete'
    try:
        capture = read(folder / 'capture/verified.json')
        identity = check_proof(capture, m, 1)
        p = capture['proof']
        frame = (folder / 'capture/frame.bin').read_bytes()
        require(len(frame) == FRAME_BYTES and digest(frame) == capture['frame_sha256'], 'Original camera frame hash differs')
        parts, read_proofs = [], []
        for offset in range(0, SECTORS, 512):
            part = folder / f'readback/payload-{offset:04d}'
            v = read(part / 'verified.json')
            check_proof(v, m, 3, identity)
            rp = v['proof']
            require(rp['read_lba'] == p['payload_lba'] + offset
                    and rp['read_count'] == min(512, SECTORS - offset), 'Read chunk is not contiguous/exact')
            data = (part / 'sectors.bin').read_bytes()
            require(len(data) == rp['read_count'] * 512 and digest(data) == v['read_sha256'], 'Read chunk bytes/hash differ')
            parts.append(data)
            read_proofs.append(v)
        slot = b''.join(parts)
        require(slot == (folder / 'readback/slot.bin').read_bytes() and len(slot) == SLOT_BYTES,
                'Full slot assembly differs')
        require(slot[:4] == b'GXR2' and slot[-4:] == b'GXRE' and slot[4:156] == bytes(152),
                'Slot magic/front metadata differs')
        require(slot[156:-4] == frame == (folder / 'readback/frame.bin').read_bytes(), 'SD/original camera image bytes differ')
        require(capture['whole_image']['metadata_hex'] == slot[4:156].hex(), 'Stored metadata differs from capture RAM')
        # Independent RAW10 arithmetic plus Pillow decoding, without using the repository PNG encoder.
        groups = np.frombuffer(frame, dtype=np.uint8).reshape(-1, 5).astype(np.uint16)
        pixels = np.empty((len(groups), 4), dtype=np.uint16)
        for i in range(4):
            pixels[:, i] = (((groups[:, i] << 2) | ((groups[:, 4] >> (i * 2)) & 3)) << 6)
        pixels = pixels.reshape(1364, 1120)
        png_path = folder / 'readback/scene.png'
        with Image.open(png_path) as image:
            decoded = np.asarray(image)
        require(decoded.shape == (1364, 1120) and np.array_equal(decoded, pixels), 'Independent PNG sample comparison differs')
        prior_validation = read(folder / 'readback/readback-validation.json')
        require(prior_validation.get('passed') is True and prior_validation['original_sensor_frame_comparison'] is True
                and prior_validation['raw_sha256'] == digest(frame) and prior_validation['slot_sha256'] == digest(slot)
                and prior_validation['png_sha256'] == digest(png_path.read_bytes()), 'Original readback report differs')
        trace = trace_summary(folder, source / name, m)
        stream = capture['magic_format']['stream']
        require(trace['counters']['SD_IDMA_TRANSFERS'] == int(stream['mode'] == 1)
                and trace['counters']['SD_PIO_TRANSFERS'] == int(stream['mode'] == 2), 'Stream/counter mode differs')
        t = trace['durations_ms']
        t.update(sd_init_card_counter=ms(capture['card']['init_cycles']),
                 write_driver_counter=ms(capture['card']['write_cycles']),
                 write_transfer_counter=ms(capture['card']['transfer_cycles']),
                 readback_data_transactions=sum(ms(v['card']['read_cycles']) for v in read_proofs),
                 readback_eight_reinitializations=sum(ms(v['card']['init_cycles']) for v in read_proofs),
                 readback_eight_runtime_intervals=sum(delta(v['proof']['begin'], v['proof']['end']) for v in read_proofs))
        elapsed = lambda value: (value - p['begin']) & 0xFFFFFFFF
        overlap = ms(elapsed(p['frame_done']) - elapsed(p['first_write']))
        snap = snapshots(folder, frame) if name == 'ram25-long' else []
        result.update(status='passed', passed=True, card_identity=identity, slot=p['slot'],
            lba=p['payload_lba'], sectors=SECTORS, image_bytes=FRAME_BYTES, slot_bytes=SLOT_BYTES,
            original_camera_bytes_equal=True, png_samples_equal=True,
            frame_sha256=digest(frame), slot_sha256=digest(slot), png_sha256=digest(png_path.read_bytes()),
            image_min=int(pixels.min()) >> 6, image_max=int(pixels.max()) >> 6,
            image_mean=float(pixels.mean()) / 64, distinct_image_levels=int(np.unique(pixels).size),
            read_operations=8, read_transactions=59,
            scan_header_reads=p['scan_headers'], clock_hz=25000000, configured_clkcr=0x34003,
            exposure_us=capture['magic_format']['sensor']['exposure_us'],
            exposure_coarse=m['exposure_coarse'], stream_mode='IDMA' if stream['mode'] == 1 else 'progressive PIO',
            stream=stream, starts_before_frame=overlap > 0, first_write_before_frame_ms=overlap,
            timing=trace, immediate_snapshots=snap, immediate_snapshot_count=len(snap),
            proof_sources=[bound(folder / 'capture/verified.json'),
                *[bound(folder / f'readback/payload-{i:04d}/verified.json') for i in range(0, SECTORS, 512)]],
            private_images={n: bound(folder / n) for n in ('capture/frame.bin', 'readback/slot.bin', 'readback/frame.bin', 'readback/scene.png')})
    except FileNotFoundError as error:
        result['pending_file'] = str(error.filename)
    except Exception as error:
        result.update(status='verification_failed', error=f'{type(error).__name__}: {error}')
    return result


def verify_preservation(source, manifests):
    """Re-read of cycle01 after later writes; never counted as a new capture."""
    import numpy as np
    from PIL import Image
    folder = source / 'preservation01'
    result = dict(present=folder.exists(), passed=False, status='not_started',
                  counts_toward_twenty=False, reference_cycle=1)
    if not folder.exists():
        return result
    result['status'] = 'incomplete'
    readback = folder / 'readback' if (folder / 'readback').exists() else folder
    try:
        original = read(source / 'cycle01/capture/verified.json')
        identity = {k: original['card'][k] for k in IDENTITY}
        reference = (source / 'cycle01/capture/frame.bin').read_bytes()
        require(digest(reference) == original['frame_sha256'], 'Preservation original frame changed')
        first = read(readback / 'payload-0000/verified.json')
        matching = [m for m in manifests.values() if m['binary_sha256'] == first['binary_sha256']]
        require(len(matching) == 1, 'Preservation reader build not pinned')
        m = matching[0]
        parts, timings, proofs = [], [], []
        for offset in range(0, SECTORS, 512):
            part = readback / f'payload-{offset:04d}'
            v = read(part / 'verified.json')
            check_proof(v, m, 3, identity)
            p = v['proof']
            require(p['read_lba'] == original['proof']['payload_lba'] + offset
                    and p['read_count'] == min(512, SECTORS-offset), 'Preservation read range differs')
            raw = (part / 'sectors.bin').read_bytes()
            require(len(raw) == p['read_count'] * 512 and digest(raw) == v['read_sha256'], 'Preservation read hash differs')
            parts.append(raw)
            timings.append(ms(v['card']['read_cycles']))
            proofs.append(bound(part / 'verified.json'))
        slot = b''.join(parts)
        expected = b'GXR2' + bytes(152) + reference + b'GXRE'
        require(slot == expected == (source / 'cycle01/readback/slot.bin').read_bytes()
                and slot == (readback / 'slot.bin').read_bytes(), 'Preservation full slot differs')
        require((readback / 'frame.bin').read_bytes() == reference, 'Preservation frame differs')
        groups = np.frombuffer(reference, dtype=np.uint8).reshape(-1, 5).astype(np.uint16)
        expected_pixels = np.empty((len(groups), 4), dtype=np.uint16)
        for i in range(4):
            expected_pixels[:, i] = (((groups[:, i] << 2) | ((groups[:, 4] >> (2*i)) & 3)) << 6)
        with Image.open(readback / 'scene.png') as image:
            require(np.array_equal(np.asarray(image), expected_pixels.reshape(1364, 1120)),
                    'Preservation PNG samples differ')
        result.update(passed=True, status='passed', slot=original['proof']['slot'],
            binary_sha256=m['binary_sha256'], card_identity=identity,
            slot_bytes=SLOT_BYTES, image_bytes=FRAME_BYTES, slot_sha256=digest(slot),
            original_camera_bytes_equal=True, first_readback_bytes_equal=True,
            png_samples_equal=True, readback_data_transactions_ms=sum(timings),
            proof_sources=proofs, private_images={n: bound(readback / n)
                for n in ('slot.bin', 'frame.bin', 'scene.png')})
    except FileNotFoundError as error:
        result['pending_file'] = str(error.filename)
    except Exception as error:
        result.update(status='verification_failed', error=f'{type(error).__name__}: {error}')
    return result


def observed_attempts(source):
    """Retain failed/unfinished records too; do not double count before-state snapshots."""
    attempts, failures, recovery = [], [], []
    folders = sorted({p for glob in ('cycle*', 'pattern*', 'preservation*') for p in source.glob(glob)})
    for cycle in folders:
        if not cycle.is_dir():
            continue
        for folder in [cycle / 'capture', *sorted((cycle / 'readback').glob('payload-*')),
                       *sorted(cycle.glob('payload-*'))]:
            if not folder.exists():
                continue
            file = folder / 'verified.json'
            if not file.exists():
                file = folder / 'proof.json'
            if not file.exists():
                file = folder / 'incomplete.json'
            record = dict(folder=str(folder.resolve()), verified=file.name == 'verified.json' and file.exists())
            if file.exists():
                try:
                    v = read(file)
                    p = v.get('proof', v)
                    c = v.get('card', {})
                    record.update(proof=bound(file), result=p.get('result'), sd_error=p.get('sd_error'),
                        cleanup_error=p.get('cleanup_error'), card_error=c.get('error'),
                        error_stage=c.get('error_stage'), error_command=c.get('error_command'),
                        error_sta=c.get('error_sta'), passed=v.get('passed'),
                        command_crc_flag=bool(c.get('error_sta', 0) & 1) or c.get('error') == 8,
                        data_crc_flag=bool(c.get('error_sta', 0) & 2))
                except Exception as error:
                    record['parse_error'] = str(error)
            attempts.append(record)
    for file in sorted(source.rglob('*failed.json')):
        failures.append(dict(source=bound(file), record=read(file)))
    for file in sorted(source.rglob('result.json')):
        if file.parent.name not in ('park', 'initial-park'):
            continue
        value = read(file)
        if 'prefix_sha256' in value:
            require(value['prefix_sha256'] == PREFIX_SHA, 'Recovery prefix changed')
            recovery.append(dict(source=bound(file), passed=value.get('passed'),
                prefix_sha256=value['prefix_sha256'], vcp_status=value.get('vcp_status'),
                context=value.get('context')))
    return attempts, failures, recovery


def collect(source):
    source = Path(source).resolve()
    manifests = {name: check_build(source / name, name) for name in BUILD_SHA if (source / name).exists()}
    require('ram25-scene' in manifests and 'ram25-long' in manifests, 'Main campaign builds missing')
    cycles = [verify_cycle(source, number, manifests) for number in range(1, 21)]
    good = [c for c in cycles if c['passed']]
    supplemental = [verify_cycle(source, label, manifests, 'ram25-pattern')
                    for label in ('pattern01', 'pattern02') if (source / label).exists()]
    preservation = verify_preservation(source, manifests)
    extra_good = [c for c in supplemental if c['passed']]
    identities = {json.dumps(c['card_identity'], sort_keys=True) for c in good + extra_good}
    slots = [c['slot'] for c in good + extra_good]
    require(len(identities) <= 1, 'Independent verified runs used different cards')
    require(len(slots) == len(set(slots)), 'A slot was reused in the campaign')
    attempts, failures, recovery = observed_attempts(source)
    has_errors = any(a.get('result') not in (0, None) or a.get('sd_error') not in (0, None)
                     or a.get('card_error') not in (0, None) or a.get('cleanup_error') not in (0, None)
                     or a.get('command_crc_flag') or a.get('data_crc_flag') or a.get('parse_error') for a in attempts)
    unfinished = [a for a in attempts if not a.get('verified') or a.get('passed') is not True]
    complete = len(good) == 20 and not failures and not has_errors and not unfinished
    # The extra build records the root's planned two pattern captures and final
    # preservation read. Their results never inflate the requested20 count.
    expected_supplemental = 2 if 'ram25-pattern' in manifests else 0
    supplementary_complete = (len(extra_good) == expected_supplemental
        and (preservation['passed'] if expected_supplemental else not preservation['present'] or preservation['passed']))
    pattern_repeat_equal = (extra_good[0]['frame_sha256'] == extra_good[1]['frame_sha256']) if len(extra_good) == 2 else None
    groups = {}
    for name in ('normal', 'long', 'all'):
        selected = [c for c in good if name == 'all' or (c['exposure_coarse'] == 30000) == (name == 'long')]
        metrics = sorted({k for c in selected for k in c['timing']['durations_ms']})
        groups[name] = dict(count=len(selected), timings_ms={k: dict(
            minimum=min(values), median=statistics.median(values), maximum=max(values))
            for k in metrics if (values := [c['timing']['durations_ms'][k] for c in selected if k in c['timing']['durations_ms']])})
    return dict(schema=1, generated_utc=datetime.now(timezone.utc).isoformat(), hardware_access=False,
        source=str(source), complete=complete, requested_images=20, verified_images=len(good),
        card_identity=good[0]['card_identity'] if good else None,
        initial_state_source=bound(source / 'initial-state.json') if (source / 'initial-state.json').exists() else None,
        final_state_source=bound(source / 'final-state.json') if (source / 'final-state.json').exists() else None,
        present_cycles=sum(c['present'] for c in cycles), cycles=cycles, attempts=attempts,
        supplemental_captures=supplemental, supplemental_verified=len(extra_good),
        supplemental_expected=expected_supplemental, pattern_repeat_equal=pattern_repeat_equal,
        pattern_repeat_scope='Descriptive only; each pattern is qualified against its own camera RAM. Sensor pattern phase may differ.',
        preservation=preservation, supplementary_complete=supplementary_complete,
        failures=failures, unfinished_attempts=unfinished, recovery=recovery, group_statistics=groups,
        build_sha256=BUILD_SHA, installed_nor_changed=False, installed_nor_checkpoint_sha256=NOR_SHA,
        build_artifacts={name: {file: bound(source / name / file) for file in ('manifest.json', 'capture.bin')}
                         for name in manifests},
        host_verifier_sources={name: bound(ROOT / 'firmware/capture-raw' / name)
                               for name in ('cycle_trace.py',)},
        installed_nor_identity_scope='Previous independently read NOR identity; this RAM campaign does not reread/program NOR.',
        slot_bytes_verified=len(good)*SLOT_BYTES, image_bytes_compared=len(good)*FRAME_BYTES,
        write_sectors_verified=len(good)*SECTORS, readback_sectors_verified=len(good)*SECTORS,
        readback_host_operations=len(good)*8, readback_native_transactions=len(good)*59,
        stream_modes=dict(Counter(c['stream_mode'] for c in good)),
        all_image_bytes_compared=(len(good)+len(extra_good)+int(preservation['passed']))*FRAME_BYTES,
        all_slot_read_bytes_verified=(len(good)+len(extra_good)+int(preservation['passed']))*SLOT_BYTES,
        reported_errors=dict(operation_failures=sum(a.get('result') not in (None, 0) for a in attempts),
            cleanup_failures=sum(a.get('cleanup_error') not in (None, 0) for a in attempts),
            unfinished_operations=len(unfinished),
            command_crc_flagged_operations=sum(a.get('command_crc_flag', False) for a in attempts),
            data_crc_flagged_operations=sum(a.get('data_crc_flag', False) for a in attempts),
            captured_error_counter=sum(c['timing']['counters']['SD_ERROR_CALLS'] for c in good),
            scope='First retained error/flags per operation, plus capture logger error calls; not individual CRC error-bit counts.'),
        limits=[
            'Probe-free functional stress at the observed voltage, temperature, wiring and card; no analog margin or formal SD certification.',
            'No logic-analyzer recording in this campaign; hardware CRC/response checks and complete SD/original-RAM equality establish observed operation.',
            'Warm RAM capture/read operations do not requalify cold flash boot, Standby, power-loss tolerance or total cycle energy.',
            'Timings use nominal 400 MHz CYCCNT; overlapping intervals are not additive. Readback sums exclude host/debugger gaps and separately report eight card initializations.',
            'Transfer time includes controller/card stalls; it is not isolated card flash-programming time.',
            'The prior HAL DTMODE0 versus reference-manual mode3 discrepancy remains explicitly unresolved.',
            'Pixel, SD-sector and immediate snapshot bytes stay private; public evidence contains hashes and operation/trace proofs.',
        ])


def markdown(summary):
    verdict = '20/20 images independently verified' if summary['complete'] else f"INCOMPLETE: {summary['verified_images']}/20 images independently verified"
    lines = ['# Four-bit 25 MHz, probes removed: twenty-image stress test', '',
        f"**{verdict}.** Report generated {summary['generated_utc']}.", '',
        'The replacement card was tested with falling-edge host launch, GPIO speed 3, inherited compensation, reviewed startup/completion/abort guards, and PIO readback. LP8 signal probes were removed; the 27-ohm CLK resistor and bench wiring were retained according to the bench owner. The first eight and final eight requested captures use normal exposure; captures 9–12 use long exposure plus immediate producer snapshots.', '',
        f"Verified {summary['slot_bytes_verified']:,} stored bytes in each direction across {summary['verified_images']} images. Every verified image matched all original camera-RAM bytes and independently decoded PNG samples. The public bundle omits image bytes.", '',
        '| Run | Slot | Exposure ms | Actual write path | SD init ms | Slot write ms | SD read transactions ms | Match |',
        '| ---: | ---: | ---: | --- | ---: | ---: | ---: | --- |']
    for c in summary['cycles']:
        if c['passed']:
            t = c['timing']['durations_ms']
            lines.append(f"| {c['run']} | {c['slot']} | {c['exposure_us']/1000:.3f} | {c['stream_mode']} | {t['sd_init']:.3f} | {t['slot_write']:.3f} | {t['readback_data_transactions']:.3f} | Full RAM + PNG |")
        else:
            lines.append(f"| {c['run']} | — | — | — | — | — | — | {c['status']} |")
    good = [c for c in summary['cycles'] if c['passed']]
    if good:
        identity = summary['card_identity']
        cid = ' '.join(f"{identity['cid'+str(i)]:08X}" for i in range(4))
        lines += ['', f"Card identity stayed constant: {identity['sector_count']:,} logical 512-byte sectors; captured CID register words `{cid}`. The complete CSD/OCR and width/startup proofs are retained for every operation.", '',
            f"Primary scene data spans 10-bit values {min(c['image_min'] for c in good)}–{max(c['image_max'] for c in good)}. This limited scene range does not exercise every pixel bit combination; supplementary sensor-generated patterns provide broader data coverage."]
        modes = summary['stream_modes']
        lines += ['', f"The primary campaign exercised {modes.get('IDMA', 0)} complete-buffer IDMA write and {modes.get('progressive PIO', 0)} progressive PIO writes. Every readback also used four-bit 25 MHz. The requested images account for {summary['write_sectors_verified']:,} written sectors and the same number read back, through {summary['readback_host_operations']} guarded read operations."]
        longs = [c for c in good if c['exposure_coarse'] == 30000]
        if longs:
            margins = [c['first_write_before_frame_ms'] for c in longs]
            lines += ['', f"All {sum(c['immediate_snapshot_count'] for c in longs)} immediate 512-byte LINE snapshots matched the final camera RAM. Each long exposure began writing before FRAME, by {min(margins):.3f}–{max(margins):.3f} ms. These checks exercise partial-frame publication while SD writes proceed."]
    lines += ['', 'Read timing sums the 59 PIO multiblock transactions needed for one complete slot. Each host read request is capped at 512 sectors, giving eight requests and eight initializations. Host/debugger gaps and these initializations are excluded from the data-transaction column; their separate totals are in [summary.json](summary.json). Slot-write timing includes preparation, all data/card stalls and final completion. These are nominal 400 MHz counter timings, not power-on or energy measurements.', '',
        f"Recorded command-CRC-flagged operations: **{summary['reported_errors']['command_crc_flagged_operations']}**. Data-CRC-flagged operations: **{summary['reported_errors']['data_crc_flagged_operations']}**. Failed operation records: **{summary['reported_errors']['operation_failures']}**. These count retained operation records, not raw wire-bit errors. Failed/incomplete attempts and recovery records are retained in summary.json and the evidence inputs.", '',
        'The installed NOR remains the reviewed 12.5 MHz startup/no-tail Standby firmware. This campaign runs 25 MHz from RAM; it does not promote a new flash profile.', '']
    if summary['initial_state_source']:
        lines += ['The [initial-state record](inputs/initial-state.json) separately records a disconnected target-power lead, its user-restored connection and successful UART recovery before the campaign. That preflight interruption is not counted as a storage test failure. A possible ordinary boot during power restoration is not counted as a measured 25 MHz image.', '']
    if summary['final_state_source']:
        lines += ['The bench owner recorded the [final state and instrument closure](inputs/final-state.json) after the tests. The hardware qualification above is based on the frozen operation proofs, not current alone.', '']
    if summary['supplemental_captures'] or summary['preservation']['present']:
        lines += ['## Supplementary coverage', '',
                  'These checks are additional to the requested twenty images; they do not inflate that count.', '']
        for c in summary['supplemental_captures']:
            if c['passed']:
                lines.append(f"- {c['run']}: sensor-generated diagonal pattern, slot {c['slot']}, full original-RAM/SD/PNG match, {c['distinct_image_levels']} distinct 10-bit levels ({c['image_min']}–{c['image_max']}), actual {c['stream_mode']} write.")
            else:
                lines.append(f"- {c['run']}: {c['status']}.")
        p = summary['preservation']
        if p['passed']:
            lines.append(f"- Preservation: complete slot {p['slot']} reread matches the first original camera frame and its first readback byte-for-byte; PNG samples also match.")
        elif p['present']:
            lines.append(f"- Preservation: {p['status']}.")
        lines.append('')
    lines += ['## Qualification limits', '']
    lines += ['- ' + item for item in summary['limits']]
    lines += ['', 'See the [prior protocol review](../2026-10-26-sd-review/PROTOCOL-REVIEW.md) for retained command/busy/abort requirements and the DTMODE discrepancy.', '',
        '## Reproduce offline', '',
        '```text', 'python archive.py inspect --source <private campaign folder> --out <report.json>',
        'python archive.py freeze --source <private campaign folder> --out <new evidence folder>',
        'python archive.py verify --out <frozen evidence folder>', '```', '',
        'Inspect may report partial progress. Freeze refuses an incomplete campaign unless explicitly passed `--allow-incomplete`; the resulting verdict still remains incomplete. `verify` checks every frozen file against its manifest. Full pixel re-comparison requires the private source artifacts.', '']
    return '\n'.join(lines)


def freeze(source, out, summary):
    out = Path(out).resolve()
    if out.exists():
        require({p.name for p in out.iterdir()} <= {'archive.py'}, 'Refusing to overwrite an existing evidence bundle')
        require(not (out / 'archive.py').exists() or (out / 'archive.py').read_bytes() == Path(__file__).read_bytes(),
                'Destination archiver differs')
    else:
        out.mkdir(parents=True, exist_ok=False)
    def check_sources(value):
        if isinstance(value, dict):
            if 'path' in value and 'sha256' in value:
                path = Path(value['path'])
                require(path.is_file() and digest(path.read_bytes()) == value['sha256'],
                        'Source changed between verification and freezing: ' + str(path))
            for child in value.values():
                check_sources(child)
        elif isinstance(value, list):
            for child in value:
                check_sources(child)
    check_sources(summary)
    copies = []
    # JSON reports never contain image bytes; trace/producer binary records are fixed telemetry only.
    for path in sorted(source.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(source)
        keep = path.suffix.lower() == '.json' and 'independent-' not in path.name
        keep |= path.name == 'events.jsonl' and path.parent.name.startswith('invocation-')
        keep |= path.name == 'supplement-events.jsonl' and path.parent == source
        keep |= path.name in ('cycle-trace.bin', 'producer.bin')
        keep |= rel.parts[0] in BUILD_SHA and path.suffix.lower() in ('.c', '.h', '.s', '.ld')
        keep |= rel.parts[0] in BUILD_SHA and path.name == 'capture.bin'
        keep |= len(rel.parts) == 1 and path.name in ('run_campaign.py', 'run_supplement.py', 'test_archive_offline.py')
        if keep:
            destination = out / 'inputs' / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            raw = path.read_bytes()
            destination.write_bytes(raw)
            copies.append(dict(source=str(path.resolve()), path=destination.relative_to(out).as_posix(),
                               bytes=len(raw), sha256=digest(raw)))
    write(out / 'source-copies.json', copies)
    for name in summary['host_verifier_sources']:
        target = out / 'host-source' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / 'firmware/capture-raw' / name, target)
    write(out / 'summary.json', summary)
    (out / 'README.md').write_text(markdown(summary), encoding='utf-8')
    if Path(__file__).resolve() != (out / 'archive.py').resolve():
        shutil.copyfile(__file__, out / 'archive.py')
    entries = [dict(path=p.relative_to(out).as_posix(), bytes=p.stat().st_size, sha256=digest(p.read_bytes()))
               for p in sorted(out.rglob('*')) if p.is_file()]
    write(out / 'SHA256SUMS.json', dict(schema=1, files=entries))
    return verify_bundle(out)


def verify_bundle(out):
    out = Path(out).resolve()
    manifest = read(out / 'SHA256SUMS.json')
    for item in manifest['files']:
        path = (out / item['path']).resolve()
        path.relative_to(out)
        raw = path.read_bytes()
        require(len(raw) == item['bytes'] and digest(raw) == item['sha256'], 'Frozen artifact changed: ' + item['path'])
    actual = {p.relative_to(out).as_posix() for p in out.rglob('*') if p.is_file()}
    expected = {item['path'] for item in manifest['files']} | {'SHA256SUMS.json'}
    require(actual == expected, 'Unmanifested or missing files in frozen bundle')
    return dict(passed=True, files_verified=len(manifest['files']), hardware_access=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=('inspect', 'freeze', 'verify'))
    ap.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--allow-incomplete', action='store_true')
    a = ap.parse_args()
    if a.action == 'verify':
        result = verify_bundle(a.out)
    else:
        summary = collect(a.source)
        if a.action == 'inspect':
            write(a.out, summary)
            result = {k: summary[k] for k in ('complete', 'verified_images', 'present_cycles', 'reported_errors', 'stream_modes')}
        else:
            require((summary['complete'] and summary['supplementary_complete']) or a.allow_incomplete,
                    'Campaign or present supplementary work is incomplete; inspect its report first')
            result = freeze(a.source.resolve(), a.out, summary)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
