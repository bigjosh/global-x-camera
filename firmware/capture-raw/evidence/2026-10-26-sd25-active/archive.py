"""Offline evidence for the exact 25 MHz cold-flash/Standby promotion.

No instrument, debugger, serial, subprocess, power or network API is used.
Private photos are compared locally, then represented publicly only by hashes.
Freeze refuses incomplete or failed evidence and never overwrites a bundle.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[4]
BASE_PATH = Path(__file__).with_name('base_archive.py')
BASE_SHA = '39391fb566ee839d91ace743bf0e7bcf77a9c5b372905c69013bc4479cbbb7b0'
if hashlib.sha256(BASE_PATH.read_bytes()).hexdigest() != BASE_SHA:
    raise ValueError('Pinned independent readback verifier changed')
spec = importlib.util.spec_from_file_location('active25_base', BASE_PATH)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
read, write, bound, digest, require = base.read, base.write, base.bound, base.digest, base.require

IDENTITIES = {
    'flash25-awake': ('c8b4d9af368803571359331257722231647327371efbe6c96eaa09088e2c7910',
        '39cdee32788c08ae81d8b3e35de6ec846d50044433f6aad6633a645585ff2bc7',
        '571660be49caafcfc167e295514c4c1863b8fe35c06192a3cdd184647e39ba38'),
    'flash25-standby': ('4dbe72895705a30b3c699500d90517e2424676d732c18eb944971560901e6512',
        'c68593cebeddf5b9c24f85249505ae719dd1ea73d11f309e3a8553e9c1a9fa47',
        '0592a543cb1e75b176e97f715f139a0a13d8a4d791ba44efd0ec94dc4f5b6754'),
}
OLD_SECTOR = 'c03e40c8ceea09bd9c171c179f2191a1ef9799c9e615db979a84b9c53ad66010'
OLD_PREFIX = '4ef99d3b0b8ac7b790265cd1994428a5804dd3a20ad5587dd1585d2544a74b0b'
FOLLOWING = '01cc465d3a7581d9d003b09e5db684eb7bec8e8512e12ce3565154c3aced816f'
READER = ROOT / 'tmp/bringup/sd25-stress-20261026/ram25-scene'
LIMITS = [
    'The 25 MHz link was qualified on the reported card/wiring with the LP8 probes removed and the 27-ohm CLK resistor retained. No analog eye/timing margins or formal SD certification are established.',
    'The awake cold capture is compared against its original camera RAM. Standby discards that RAM; its image is checked for complete markers, same-speed read integrity and independent PNG decoding only.',
    'SBF/PDDS are observed after warm UART recovery without an intervening power-off. The guarded reader retains trial_entry_proven:false; it does not independently attribute the flag to this specific entry.',
    'Cold-start evidence is a measured JS110-off interval of at least 15 seconds and near-zero current; target rails were not probed. Completion current is a signature, not by itself an idle or Standby proof.',
    'No new cycle-energy or power-on timing comparison is made. Current statistics are not an integrated energy measurement.',
    'GXR2/GXRE markers do not checksum pixels or establish arbitrary power-loss atomicity. Existing CRC, ownership, recovery and cleanup gates remain enabled.',
]


def build(source, name):
    folder = source / name
    m, s = read(folder / 'manifest.json'), read(folder / 'staged/manifest.json')
    binary, sector, prefix = IDENTITIES[name]
    require(digest((folder / 'capture.bin').read_bytes()) == m['binary_sha256'] == binary, 'Receiver identity differs')
    require(digest((folder / 'staged/capture_sector_0.bin').read_bytes()) == s['program_sha256'] == sector, 'NOR image differs')
    require(digest((folder / 'staged/stage1.bin').read_bytes()) == s['stage1_raw_sha256'] == prefix, 'Prefix differs')
    expected = dict(flash=True, standby=name.endswith('standby'), pattern=0, sd_bus_width=4,
        sd_clock_hz=25000000, sd_gpio_speed=3, sd_clock_negedge=True, sd_clock_negedge_init=True,
        sd_review_profile=True, sd_startup_opt=True, sd_early_run_clock=False, sd_high_speed=False,
        sd_idma_read=False, sd_fixed_compensation=False, sd_compensation_modified=False,
        raw_dma_tail_wait=False, dma_sleep=False, magic_format=True, magic_layout_version=2,
        image_offset=156, metadata_bytes=152, line_stream=True, async_stop=True, transport='idma')
    require(all(m.get(k) == v and type(m.get(k)) is type(v) for k, v in expected.items()), 'Promotion profile differs')
    require(not m.get('cycle_trace') and m['late_load']['early_bytes'] == s['stage2_bytes'] == 15804,
            'Trace or early-load geometry differs')
    for rel, value in m['source_hashes'].items():
        require(digest((folder / rel).read_bytes()) == value, 'Receiver source differs: ' + rel)
    for rel, value in s['sources'].items():
        require(digest((ROOT / rel).read_bytes()) == value, 'Prefix source differs: ' + rel)
    review = read(source / ('standby-prefix-review.json' if m['standby'] else 'awake-prefix-review.json'))
    require(review['passed'] and review['binary_sha256'] == binary and review['sector_sha256'] == sector
            and review['prefix_sha256'] == prefix and review['early_load_bytes'] == 15804
            and review['changed_prefix_bytes'] == [3228, 3229, 3230, 3231, 4948, 4949, 4950, 4951]
            and review['recovery_schema_unchanged'], 'Exact-prefix review differs')
    return m


def recovery(path, prefix):
    v = read(path)
    require(v['passed'] and v['prefix_sha256'] == prefix and v['context']['PC'] == 0x3418078C,
            'Exact recovery identity/park differs')
    require(v['context']['PRIMASK'] == 1 and v['context']['CONTROL'] == 0
            and not v['ccr'] & 0x30000 and not v['fpccr'] & 1, 'Recovery context differs')
    p = v['vcp_status']
    require(p['request'] == 1 and p['good_pulses'] >= 3 and p['bad_pulses'] == 0,
            'UART recovery pulse proof differs')
    return dict(proof=bound(path), good_pulses=p['good_pulses'], bad_pulses=p['bad_pulses'], prefix_sha256=prefix)


def install(source, label, before_sector, before_prefix):
    folder, name = source / ('install-' + label), 'flash25-' + label
    selected = IDENTITIES[name][1]
    result = dict(passed=True, stages={}, recovery=recovery(folder / 'park/result.json', before_prefix))
    for name, offset, count, expected in (
        ('nor-before', 0, 65536, before_sector), ('nor-after', 0, 65536, selected),
        ('following-before', 65536, 4096, FOLLOWING), ('following-after', 65536, 4096, FOLLOWING)):
        v = read(folder / name / 'verified.json')
        raw = (folder / name / 'readback.bin').read_bytes()
        require(v['matches'] is True and v['offset'] == offset and v['bytes'] == len(raw) == count
                and v['sha256'] == digest(raw) == expected, 'Physical NOR readback differs: ' + name)
        result['stages'][name] = dict(proof=bound(folder / name / 'verified.json'), bytes=count,
                                     sha256=expected, private_readback=bound(folder / name / 'readback.bin'))
    require((folder / 'following-before/readback.bin').read_bytes() ==
            (folder / 'following-after/readback.bin').read_bytes(), 'Following 4 KiB changed')
    status, diag = read(folder / 'write/status.json'), read(folder / 'completion-diagnostic/result.json')
    require(status['result'] == status['cleanup_result'] == status['failure_stage'] == 0
            and status['stage'] == 12 and status['command'] == 3
            and status['current_crc'] == status['expected_current_crc']
            and status['input_crc'] == status['final_crc'] == status['expected_input_crc']
            and status['completed_mask'] == status['changed_mask'], 'NOR programming status differs')
    require(diag['diag_state'] == 2 and diag['pending_operations'] == diag['first_failure_result'] == 0
            and diag['diag_sequence'] == status['sequence'], 'NOR completion diagnostic differs')
    done = read(folder / 'complete.json')
    require(done['passed'] and done['independent_full_readback'] and done['following4096_unchanged']
            and done['old_sector_sha256'] == before_sector and done['new_sector_sha256'] == selected,
            'Installation completion record differs')
    result.update(new_sector_sha256=selected, full_physical_readback_equal=True, following_4096_unchanged=True,
                  write_status=bound(folder / 'write/status.json'), diagnostic=bound(folder / 'completion-diagnostic/result.json'))
    return result


def cold(source, label):
    folder = source / (label + '-cold')
    profile = 'standby' if label == 'final' else label
    v, events = read(folder / 'boot-proof.json'), read(folder / 'events.json')
    require(v['cold_boot_confirmed'] and v['no_debugger_or_uart_during_boot']
            and v['binary_sha256'] == IDENTITIES['flash25-' + profile][0]
            and v['sector_sha256'] == IDENTITIES['flash25-' + profile][1], 'Cold boot binding differs')
    require([e['name'] for e in events] == ['before', 'off', 'measured_off', 'off_15s', 'on', 'completion_signature'],
            'Cold event sequence differs')
    for e in events:
        require(e['response']['ok'] is True, 'Power-control response failed')
    for index in (2, 3):
        r = events[index]['response']
        require(r['range'] == 0 and abs(r['statistics']['current']['avg']) < 0.0001,
                'Measured off current/range differs')
    off_time = datetime.fromisoformat(events[1]['utc'])
    on_time = datetime.fromisoformat(events[4]['utc'])
    duration = (on_time - off_time).total_seconds()
    require(duration >= 15 and events[4]['response']['range'] == 128, 'Cold off interval is too short')
    r = events[-1]['response']
    amps = r['statistics']['current']['avg']
    require(r['range'] == 128 and ((0.006 < amps < 0.012) if profile == 'standby' else (0.03 < amps < 0.25)),
            'Completion current signature differs')
    for item in v['evidence']:
        require(digest(Path(item['path']).read_bytes()) == item['sha256'], 'Cold source binding changed')
    return dict(passed=True, proof=bound(folder / 'boot-proof.json'), events=bound(folder / 'events.json'),
                off_seconds=duration, completion_current_mA=amps * 1000,
                completion_voltage_V=r['statistics']['voltage']['avg'], qualification='Current signature, not an independent idle proof')


def awake_capture(source, m):
    path = source / 'awake-inspect/verified.json'
    v, frame = read(path), (source / 'awake-inspect/frame.bin').read_bytes()
    p, c = v['proof'], v['card']
    require(v['passed'] and v['kind'] == 'raw-flash-inspection' and v['binary_sha256'] == m['binary_sha256']
            and v['sector_sha256'] == IDENTITIES['flash25-awake'][1]
            and v['boot_proof_sha256'] == digest((source / 'awake-cold/boot-proof.json').read_bytes()),
            'Awake flash inspection/build/boot binding differs')
    expected = dict(nonce=0, operation=1, state=3, result=0, stage=8, terminal=0x5253444E,
        media_idle=1, initialized=0, controller_owned=0, cleanup_error=0, sd_error=0,
        clock_hz=25000000, control=0, ipsr=0, primask=1, completion=0,
        frame=0x340000A0, bytes=1909600, width=1120, height=1364, flags=m['expected_flags'],
        transport=1, chunk_sectors=3730, pattern=0, written_sectors=3730, chunk_count=1,
        chunk_overflow=0, frames=1, camera_ready=1909600, dma_bytes=1909600, errors=0, capture_error=0, canary=0)
    require(all(p.get(k) == value for k, value in expected.items()), 'Awake capture terminal differs')
    require(not p['ccr'] & 0x30000 and not p['fpccr'] & 1 and not p['systick'] & 3
            and v['context']['registers']['PC'] == m['park'], 'Awake context differs')
    require(all(c[k] == 0 for k in ('error', 'error_stage', 'error_command', 'error_sta', 'cleanup_error',
        'controller_owned', 'initialized', 'timer_owned')) and c['media_idle'] == 1 and c['clock_hz'] == 25000000,
        'Awake card errors/ownership/clock differ')
    require(c['bus_width_proof']['negotiated_width'] == 4 and c['bus_width_proof']['configured_clkcr'] == 0x34003
            and c['startup_proof']['run_hz'] == 25000000 and c['startup_proof']['scr_hits'] == 1,
            'Awake width/startup profile differs')
    require(p['payload_lba'] == p['slot'] * 3730 and p['scan_headers'] == p['slot'] + 1
            and c['written_sectors'] == 3730 and p['last_ready'] & 0x1F00 == 0x900,
            'Awake slot/card completion differs')
    require(len(frame) == 1909600 and digest(frame) == v['frame_sha256'], 'Original camera frame binding differs')
    require(v['whole_image']['metadata_hex'] == bytes(152).hex(), 'Capture metadata is not zeroed')
    return dict(passed=True, slot=p['slot'], proof=bound(path), frame=bound(source / 'awake-inspect/frame.bin'),
                card_identity={k: c[k] for k in base.IDENTITY}, frame_bytes=len(frame),
                stream_mode='IDMA' if v['slots']['stream']['mode'] == 1 else 'progressive PIO')


def image(source, label, slot, reader, identity, reference=None):
    import numpy as np
    from PIL import Image
    folder, parts = source / (label + '-readback'), []
    for offset in range(0, 3730, 512):
        chunk = folder / f'payload-{offset:04d}'
        v = read(chunk / 'verified.json')
        base.check_proof(v, reader, 3, identity)
        p, data = v['proof'], (chunk / 'sectors.bin').read_bytes()
        require(p['read_lba'] == slot * 3730 + offset and p['read_count'] == min(512, 3730 - offset)
                and len(data) == p['read_count'] * 512 and digest(data) == v['read_sha256'], 'SD chunk extent/hash differs')
        parts.append(data)
    raw_slot = b''.join(parts)
    frame = raw_slot[156:-4]
    require(len(raw_slot) == 1909760 and raw_slot == (folder / 'slot.bin').read_bytes()
            and raw_slot[:4] == b'GXR2' and raw_slot[-4:] == b'GXRE'
            and raw_slot[4:156] == bytes(152) and frame == (folder / 'frame.bin').read_bytes(),
            'Complete slot, metadata or frame differs')
    if reference is not None:
        require(frame == reference.read_bytes(), 'SD image differs from original camera RAM')
    groups = np.frombuffer(frame, dtype=np.uint8).reshape(-1, 5).astype(np.uint16)
    pixels = np.empty((len(groups), 4), dtype=np.uint16)
    for lane in range(4):
        pixels[:, lane] = (((groups[:, lane] << 2) | ((groups[:, 4] >> (lane * 2)) & 3)) << 6)
    pixels = pixels.reshape(1364, 1120)
    with Image.open(folder / 'scene.png') as png:
        decoded = np.asarray(png)
    require(np.array_equal(decoded, pixels), 'Independent PNG sample decoding differs')
    report = read(folder / 'readback-validation.json')
    require(report['passed'] and report['slot'] == slot and report['raw_sha256'] == digest(frame)
            and report['slot_sha256'] == digest(raw_slot) and report['png_samples_match_read_raw']
            and report['original_sensor_frame_comparison'] == (reference is not None), 'Saved readback report differs')
    return dict(passed=True, slot=slot, sectors=3730, bytes=len(raw_slot), image_bytes=len(frame),
        clock_hz=25000000, bus_width=4, read_operations=8, original_camera_bytes_equal=reference is not None,
        png_samples_equal=True, zero_error_read_operations=8, sample_min=int(pixels.min()) >> 6,
        sample_max=int(pixels.max()) >> 6, private_images={n: bound(folder / n) for n in ('slot.bin', 'frame.bin', 'scene.png')})


def collect(source):
    source = Path(source).resolve()
    result = dict(schema=1, generated_utc=datetime.now(timezone.utc).isoformat(), hardware_access=False,
                  source=str(source), complete=False, checks={}, pending=[], errors=[], limits=LIMITS)
    checks = result['checks']
    def check(name, function):
        try:
            checks[name] = function()
            return checks[name]
        except FileNotFoundError as e:
            result['pending'].append(dict(check=name, file=str(e.filename)))
        except Exception as e:
            result['errors'].append(dict(check=name, error=f'{type(e).__name__}: {e}'))
        return None
    builds = {}
    for name in IDENTITIES:
        m = check(name, lambda name=name: build(source, name))
        if m is not None:
            builds[name] = m
    check('install_awake', lambda: install(source, 'awake', OLD_SECTOR, OLD_PREFIX))
    check('awake_cold', lambda: cold(source, 'awake'))
    capture = check('awake_capture', lambda: awake_capture(source, builds['flash25-awake'])) if 'flash25-awake' in builds else None
    reader = check('reader_build', lambda: base.check_build(READER, 'ram25-scene'))
    if capture and reader:
        check('awake_image', lambda: image(source, 'awake', capture['slot'], reader, capture['card_identity'], source / 'awake-inspect/frame.bin'))
    check('awake_recovery', lambda: recovery(source / 'awake-park/result.json', IDENTITIES['flash25-awake'][2]))
    def before_header():
        slot = capture['slot'] + 1
        folder = source / 'pre-standby-headers' / ('slot-' + str(slot))
        v, data = read(folder / 'verified.json'), (folder / 'sectors.bin').read_bytes()
        base.check_proof(v, reader, 3, capture['card_identity'])
        require(v['proof']['read_lba'] == slot * 3730 and v['proof']['read_count'] == 1
                and len(data) == 512 and digest(data) == v['read_sha256'], 'Pre-save header extent/hash differs')
        report = read(source / 'pre-standby-headers/summary.json')
        erased = report['layout']['erased_byte']
        captured_erased = read(source / 'awake-inspect/verified.json')['slots']['erased_byte']
        require(erased == captured_erased == report['scr_source']['erased_byte']
                and report['slots'][0]['slot'] == report['slots'][0]['header']['index'] == slot
                and report['slots'][0]['header']['slot_lba'] == slot * 3730
                and data[:4] == bytes([erased]) * 4 and report['passed'] and report['slots'][0]['header']['state'] == 'FREE',
                'Expected Standby slot was not free before the cold capture')
        return dict(passed=True, slot=slot, erased_byte=erased, header_sha256=digest(data),
                    proof=bound(folder / 'verified.json'), qualification='First four erased bytes establish FREE under the selected format')
    if capture and reader:
        check('standby_slot_was_free', before_header)
    check('install_standby', lambda: install(source, 'standby', IDENTITIES['flash25-awake'][1], IDENTITIES['flash25-awake'][2]))
    check('standby_cold', lambda: cold(source, 'standby'))
    check('standby_recovery', lambda: recovery(source / 'standby-park/result.json', IDENTITIES['flash25-standby'][2]))
    def flag():
        v = read(source / 'standby-flag/result.json')
        require(v['passed'] and v['sbf'] is True and v['pdds'] is True and v['stopf'] is False
                and v['prefix_sha256'] == IDENTITIES['flash25-standby'][2]
                and not v['reset_or_power_changed'] and not v['cpucr_written'], 'Standby flag proof differs')
        return dict(passed=True, proof=bound(source / 'standby-flag/result.json'), sbf=v['sbf'], pdds=v['pdds'],
                    stopf=v['stopf'], trial_entry_proven=v['trial_entry_proven'], interpretation=v['interpretation'])
    check('standby_flag', flag)
    if capture and reader:
        check('standby_image', lambda: image(source, 'standby', capture['slot'] + 1, reader, capture['card_identity']))
    check('final_cold_signature', lambda: cold(source, 'final'))
    def final():
        v = read(source / 'final-state.json')
        require(v.get('installed_sector_sha256') == IDENTITIES['flash25-standby'][1]
                and v['installed_receiver_sha256'] == IDENTITIES['flash25-standby'][0]
                and v['installed_prefix_sha256'] == IDENTITIES['flash25-standby'][2], 'Final installed identity differs')
        require(v['awake_qualified_slot'] == capture['slot'] and v['standby_qualified_slot'] == capture['slot'] + 1
                and v['final_expected_slot'] == capture['slot'] + 2
                and v['awake_original_camera_ram_comparison'] is True
                and v['standby_original_camera_ram_comparison'] is False
                and v['final_extra_image_reread'] is False and v['final_extra_sbf_reread'] is False
                and v['com8_closed_break_released'] is True and v['active_bench_helpers'] == 0
                and v['card_erased'] is False and v['new_energy_comparison'] is False, 'Final-state scope differs')
        gate = read(source / v['fresh_idle_before_final_boot'])
        last_proof = source / 'standby-readback/payload-3584/verified.json'
        require((ROOT / gate['prior']).resolve() == last_proof.resolve()
                and gate['binary_sha256'] == reader['binary_sha256']
                and gate['context']['registers']['PC'] == reader['park']
                and gate['context']['registers']['PRIMASK'] == 1 and gate['context']['registers']['CONTROL'] == 0
                and not gate['context']['ccr'] & 0x30000 and not gate['context']['fpccr'] & 1,
                'Fresh idle proof before final normal boot differs')
        js = read(source / 'js-response.json')
        last = json.loads((source / 'js-session.jsonl').read_text(encoding='utf-8').splitlines()[-1])
        require(js == last and js['event'] == 'stopped' and js['ok'] is True
                and js['starting_range'] == js['range'] == 128 and js['restore_error'] is None,
                'Joulescope did not close cleanly preserving range128')
        require(datetime.fromisoformat(js['utc']) >= datetime.fromisoformat(read(source / 'final-cold/boot-proof.json')['observed_utc']),
                'Instrument-close proof predates the final normal boot')
        require(v['joulescope_closed_cleanly'] and v['joulescope_restored_range'] == 128
                and v['joulescope_target_left_on'] and v['last_input_voltage_V'] == js['statistics']['voltage']['avg']
                and v['last_current_A'] == js['statistics']['current']['avg'], 'Final instrument state differs')
        return dict(passed=True, record=v, proof=bound(source / 'final-state.json'),
                    instrument_stop=bound(source / 'js-response.json'), stopped_utc=js['utc'], range_preserved=128)
    check('final_state', final)
    expected = {'flash25-awake', 'flash25-standby', 'install_awake', 'awake_cold', 'awake_capture', 'reader_build',
                'awake_image', 'awake_recovery', 'standby_slot_was_free', 'install_standby', 'standby_cold',
                'standby_recovery', 'standby_flag', 'standby_image', 'final_cold_signature', 'final_state'}
    operations = []
    for path in sorted(source.rglob('verified.json')):
        v = read(path)
        p, card = v.get('proof', {}), v.get('card', {})
        if not isinstance(p, dict) or 'operation' not in p:
            continue
        fields = dict(result=p.get('result'), sd_error=p.get('sd_error'), cleanup_error=p.get('cleanup_error'),
                      card_error=card.get('error'), card_cleanup_error=card.get('cleanup_error'),
                      error_sta=card.get('error_sta'))
        operations.append(dict(source=bound(path), operation=p['operation'], fields=fields))
        if v.get('passed') is not True or any(x not in (0, None) for x in fields.values()):
            result['errors'].append(dict(check='operation_ledger', source=str(path), fields=fields))
    result['operation_ledger'] = operations
    correction = source / 'readback-preflight-correction.json'
    if correction.exists():
        v = read(correction)
        require(v['reset_or_power_cycle_for_correction'] is False and v['sd_operation_retry'] is False
                and v['guards_relaxed'] is False, 'Host preflight correction had unreported hardware effects')
        result['host_preflight_correction'] = dict(source=bound(correction), record=v)
    result['complete'] = set(checks) == expected and not result['pending'] and not result['errors']
    result['input_sources'] = [bound(p) for p in inputs(source)]
    return result


def inputs(source):
    for path in sorted(source.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts:
            continue
        rel = path.relative_to(source)
        selected_build = rel.parts[0] in IDENTITIES
        keep = path.suffix.lower() in ('.json', '.jsonl', '.py') and not path.name.startswith('independent-')
        keep |= len(rel.parts) == 1 and path.suffix.lower() in ('.txt', '.log')
        keep |= selected_build and (path.suffix.lower() in ('.c', '.h', '.s', '.ld', '.inc')
            or path.name in ('capture.bin', 'stage1.bin', 'stage1_boot.bin', 'capture_sector_0.bin'))
        if keep:
            yield path


def markdown(s):
    c = s['checks']
    awake, standby = c['awake_image'], c['standby_image']
    lines = ['# Active four-bit 25 MHz cold-flash firmware', '',
        '**Passed and installed.** The reviewed startup/no-tail profile now runs four-bit SD at 25 MHz, with falling-edge launch during identification and transfer, GPIO speed3 and unchanged compensation. The final installed image captures to GXR2 packed RAW slots and then enters Standby. Earlier-clock-transition, tail-wait, receive-IDMA, DMA-WFI, tracing and electrical experiments remain disabled.', '',
        'This promotion follows the [twenty-image RAM campaign](../2026-10-26-sd25-twenty/README.md) and [illuminated-scene addendum](../2026-10-26-sd25-lit-scene/README.md). Those frozen records remain unchanged.', '',
        '| Qualification | Observed result |', '| --- | --- |',
        '| Awake NOR installation | All 65,536 bytes match; following 4,096 bytes unchanged |',
        f"| Awake cold capture, slot {awake['slot']} | All 1,909,600 SD pixel bytes equal original camera RAM; independent PNG decoding passed |",
        '| Final Standby NOR installation | All 65,536 bytes match; following 4,096 bytes unchanged |',
        f"| Standby cold capture, slot {standby['slot']} | Complete 3,730-sector readback at 25 MHz; GXR2/GXRE and PNG samples passed |",
        '| New-slot attribution | The Standby slot header was read and confirmed FREE before the cold capture |',
        f"| Post-save current signature | {c['standby_cold']['completion_current_mA']:.3f} mA at {c['standby_cold']['completion_voltage_V']:.3f} V on the JS-fed board branch |",
        '| Warm UART recovery | Exact final prefix/early park; retained pulse proof passed |',
        '| Guarded power flag read | SBF=1, PDDS=1, STOPF=0; trial_entry_proven:false retained |', '',
        'Both readbacks have eight guarded operations with zero retained card/command/data/cleanup errors. The awake cold write and source-RAM comparison qualify the installed transport path before the separately tested Standby build. Standby loses original camera RAM; its pixel source equality is therefore not claimed.', '',
        'One host-only readback preflight was rejected because its SCR source pointed to a READ record rather than the required CAPTURE record. The output folder had not been created and no hardware operation occurred. The corrected invocation used the original awake capture/SCR proof; no guard, reset or SD retry was involved. Both logs and the correction record are preserved.', '',
        '## Exact final identities', '',
        f"- Receiver SHA-256: `{IDENTITIES['flash25-standby'][0]}`",
        f"- 64 KiB NOR sector SHA-256: `{IDENTITIES['flash25-standby'][1]}`",
        f"- Recovery-prefix SHA-256: `{IDENTITIES['flash25-standby'][2]}`", '',
        'The early load remains 15,804 bytes. Independent prefix review found only the two expected CRC data words changed, with all recovery instructions/literals retained. Build manifests retain their original `hardware_status: untested` creation-time field; this evidence supplies the later measured qualification.', '',
        '## Final bench state', '',
        f"After the complete slot{standby['slot']} qualification, a separate final normal cold boot left the target powered on the installed 25 MHz Standby image's low-current plateau: {c['final_cold_signature']['completion_current_mA']:.3f} mA. Expected next slot{standby['slot'] + 1} and SBF were not reread after this final boot. This final observation is a power signature only; it is not counted as another verified image.", '',
        'The exact final state and preserved instrument settings are in [final-state.json](inputs/final-state.json). Do not infer live bench state from this historical report; use the latest repository checkpoint before hardware work.', '',
        '## Limits', '', *['- ' + item for item in s['limits']], '',
        '## Offline replay', '',
        'The public bundle contains exact firmware, source/manifest hashes, cold-power events, both NOR installation proofs, operation records, recovery and final-state records. Photos, SD-sector payloads and original camera RAM remain private; hashes bind those locally compared bytes. The pinned prior verifier supplies the reviewed same-speed RAM READ checks. The archive verifier has no hardware access; copied bench scripts are historical sources and are not part of offline verification.', '',
        '```text', 'python -B archive.py inspect --source <private promotion folder> --out <report.json>',
        'python -B archive.py freeze --source <private promotion folder> --out <new evidence folder>',
        'python -B archive.py verify --out <frozen evidence folder>', '```', '',
        'Full pixel replay requires private source data and the frozen `ram25-scene` helper from the prior campaign. `verify` checks every public file hash and refuses missing, changed or extra files. `freeze` requires all expected independent checks and the final-state record.', '',
        'Build both candidates from the repository with the same existing capture receiver/prefix bases used in the manifests:', '',
        '```text',
        'python -B firmware/capture-raw/build.py --out tmp/bringup/rebuild-active25-awake --base tmp/bringup/sd-normal-20261024/v66c-normal-standby --flash --sd-bus-width 4 --sd-clock-hz 25000000 --sd-clock-negedge --sd-clock-negedge-init --sd-review-profile --sd-startup-opt --magic-format --line-stream --async-stop --transport idma',
        'python -B firmware/capture-raw/build.py --out tmp/bringup/rebuild-active25-standby --base tmp/bringup/sd-normal-20261024/v66c-normal-standby --flash --standby --sd-bus-width 4 --sd-clock-hz 25000000 --sd-clock-negedge --sd-clock-negedge-init --sd-review-profile --sd-startup-opt --magic-format --line-stream --async-stop --transport idma',
        '```', '',
        'These commands require the existing frozen base and STM32 toolchain/vendor sources. Their identities, every generated source hash and exact compiler flags are retained in the manifests; a build alone does not authorize hardware installation.', '']
    return '\n'.join(lines)


def freeze(source, out, summary):
    require(summary['complete'], 'Promotion evidence is incomplete or failed')
    source, out = Path(source).resolve(), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    require({p.name for p in out.iterdir()} <= {'archive.py', 'base_archive.py', '.gitattributes'}, 'Refusing to overwrite frozen evidence')
    def unchanged(value):
        if isinstance(value, dict):
            if {'path', 'bytes', 'sha256'} <= value.keys():
                require(bound(value['path']) == value, 'Evidence changed since independent verification: ' + value['path'])
            for item in value.values():
                unchanged(item)
        elif isinstance(value, list):
            for item in value:
                unchanged(item)
    unchanged(summary)
    copies = []
    for item in summary['input_sources']:
        p = Path(item['path'])
        require(bound(p) == item, 'Source changed during verification: ' + str(p))
        dest = out / 'inputs' / p.relative_to(source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dest)
        copies.append(dict(source=str(p), path=dest.relative_to(out).as_posix(), bytes=item['bytes'], sha256=item['sha256']))
    for filename, path in (('archive.py', Path(__file__)), ('base_archive.py', BASE_PATH)):
        if path.resolve() != (out / filename).resolve():
            shutil.copyfile(path, out / filename)
    (out / '.gitattributes').write_text('# Preserve exact bytes covered by SHA256SUMS.json, including copied sources.\n* -text\n', encoding='utf-8', newline='\n')
    write(out / 'summary.json', summary)
    write(out / 'source-copies.json', copies)
    (out / 'README.md').write_text(markdown(summary), encoding='utf-8')
    entries = [dict(path=p.relative_to(out).as_posix(), bytes=p.stat().st_size, sha256=digest(p.read_bytes()))
               for p in sorted(out.rglob('*')) if p.is_file()]
    write(out / 'SHA256SUMS.json', dict(schema=1, files=entries))
    return base.verify_bundle(out)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('inspect', 'freeze', 'verify'))
    p.add_argument('--source', type=Path, default=ROOT / 'tmp/bringup/sd25-promote-20261026')
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.action == 'verify':
        result = base.verify_bundle(a.out)
    else:
        summary = collect(a.source)
        if a.action == 'inspect':
            write(a.out, summary)
            result = {k: summary[k] for k in ('complete', 'pending', 'errors')}
            result['passed_checks'] = list(summary['checks'])
        else:
            result = freeze(a.source, a.out, summary)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
