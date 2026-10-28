"""Read-only observation of the exact installed normal cold-error firmware.

No halt/reset/download, UART stimulus, power control, NOR/SD command or live
SD-register read. Start beside the root-owned cold_led_trace.py launch; this
observer only consumes that helper's fresh power-on event and current bins.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
INSTALLED_SHA = 'fd37dde1ac7e26918346eafd0d5ecc20f0551553fff82bd0126b716cf6d7303a'
HEADER_SHA = 'cb34f62aaf04ec1856f9546d83326157c64f6fa47cf10b8d35e0e16e65de8bf5'
FIXED = dict(proof=0x343FD100, proof_words=96, card=0x34307F80,
             slots=0x34307D00, magic_slots=0x34307AC0, magic_slots_bytes=576,
             sd_startup_proof=0x34308348, sd_width_proof=0x34308388)
CARD_NAMES = ('sector_count read_sectors written_sectors read_cycles write_cycles ready_cycles '
    'initialized controller_owned media_idle clock_hz ocr rca cid0 cid1 cid2 cid3 '
    'csd0 csd1 csd2 csd3 error error_stage error_command error_sta stage last_command '
    'last_argument last_sta last_r1 command_count last_ready_r1 last_stop_r1 cleanup_error '
    'transfer_words transfer_sta transfer_cycles init_cycles gpioc_idr gpioe_idr '
    'vddio5_control saved_sdmmc_mux saved_demcr saved_dwt timer_owned').split()
SLOT_NAMES = ('card slot_count selected_slot slot_lba erased_byte opened selected_valid '
              'active error scan_headers read_sectors written_sectors write_sectors').split()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')


def load_manifest(path):
    m = json.loads(path.read_text())
    assert m['binary_sha256'] == INSTALLED_SHA
    assert sha((path.parent/'capture.bin').read_bytes()) == INSTALLED_SHA
    assert all(m.get(k) == v for k, v in FIXED.items()), 'Installed record layout changed'
    header = (path.parent/'runtime.h').read_bytes()
    assert sha(header) == HEADER_SHA == m['source_hashes']['runtime.h']
    enum = header.decode().split(' RP_MAGIC,', 1)[1].split('};', 1)[0]
    names = ['magic']+[n.lower() for n in re.findall(r'\bRP_([A-Z0-9_]+)\b', enum)]
    assert len(names) == 96 and len(set(names)) == 96
    assert m['error_runtime_copy']['destination'] == 0x343C8000
    assert m['error_runtime_copy']['bytes'] == 1536
    return m, names


def decode_proof(raw, names):
    return dict(zip(names, struct.unpack('<96I', raw)))


def proof_identity(p):
    return (p['magic'] == 0x52535731 and p['schema'] == 1 and p['words'] == 96 and
            p['operation'] == 1 and p['nonce'] == 0 and p['frame'] == 0x340000A0 and
            p['bytes'] == 1909600 and p['completion'] == 1)


def error_ready(p):
    # The nonreturning blink engine runs BEFORE RP_TERMINAL=RSDN is written.
    return proof_identity(p) and p['state'] == 15 and p['result'] not in (0, 0xFFFFFFFF)


def check_pointers(p):
    assert (p['card'], p['card_size'], p['slots'], p['slots_size']) == (
        FIXED['card'], 200, FIXED['slots'], 640), 'Retained pointers differ; do not follow them'


def decode_card(raw):
    return dict(zip(CARD_NAMES, struct.unpack('<6Q38I', raw)))


def fresh_bin(row, launch, now):
    mean = row.get('mean')
    return (row.get('signal') == 'current' and row.get('complete_bin') is True and
            row.get('nonfinite_count') == 0 and isinstance(mean, (float, int)) and math.isfinite(mean) and
            0 <= now-row.get('processed_monotonic', 0) < .5 and
            row.get('first_chunk_received', {}).get('monotonic_ns', 0) >= launch['monotonic_ns'])


class StopObservation(Exception):
    pass


def current_guard(trace, launch, deadline):
    now = time.monotonic()
    if now >= deadline:
        raise StopObservation('Conservative pre-Standby observation deadline reached')
    latest = None
    for line in trace.read_text(encoding='utf-8').splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get('signal') == 'current':
            latest = row
    if latest is None or not fresh_bin(latest, launch, now):
        raise StopObservation('No fresh complete finite post-launch current bin; no further debug read')
    if latest['mean'] < .02:
        raise StopObservation('Already at low current; skip debugger access and preserve the state')
    if not .02 <= latest['mean'] < .8:
        raise StopObservation('Current outside the reviewed awake range; no further debug read')
    return latest


def summarize(p, card, slots=None):
    names = ('begin arm frame_done camera_stop sd_begin sd_ready scan_done slot_begin '
             'first_write payload_done commit_done deinit_done end').split()
    times = {}
    for key in names:
        value = p[key]
        if value:
            delta = (value-p['begin']) & 0xFFFFFFFF
            times[key] = dict(cycles=value, ms_from_runtime_begin=delta/400000.0)
    result = dict(result=p['result'], result_hex=hex(p['result']), stage=p['stage'],
        sd_error=card['error'], error_stage=card['error_stage'], error_command=card['error_command'],
        error_sta=card['error_sta'], error_sta_hex=hex(card['error_sta']), cleanup_error=card['cleanup_error'],
        scan_headers=p['scan_headers'], image_sectors_written=p['written_sectors'],
        card_sectors_written=card['written_sectors'], frames=p['frames'], timestamps=times,
        timestamp_scope='Retained 400MHz DWT counters; not external cold power timing',
        last_argument=card['last_argument'],
        last_argument_caveat='May belong to cleanup; not assumed to be the failed command argument')
    if (p['result'] == 0x324 and card['error_command'] == 17 and slots is not None and
            slots['error'] == 4 and slots['scan_headers'] == p['scan_headers']):
        result['inferred_failed_slot_header_lba'] = p['scan_headers']*3730
        result['lba_basis'] = 'Derived from zero-based sequential scan and successful-header count; not a retained command argument'
    return result


def run(args):
    m, names = load_manifest(args.manifest.resolve())
    plan = dict(manifest=str(args.manifest.resolve()), installed_receiver_sha256=INSTALLED_SHA,
        power_on=str(args.power_on.resolve()), current=str(args.current.resolve()), addresses=FIXED,
        execute=args.execute, halt=False, reset=False, target_writes=False, power_control=False,
        nor_commands=False, sd_commands=False, live_sd_register_reads=False)
    if not args.execute:
        print(json.dumps(plan, indent=2)); return 0
    args.out.mkdir(parents=True, exist_ok=False)
    write_json(args.out/'plan.json', plan)
    report = dict(debug_reads=False, halt=False, reset=False, target_writes=False,
                  idle_permission=False, fresh_error_proof=False, observations=[])
    try:
        wait_until = time.monotonic()+90
        while not args.power_on.exists():
            if time.monotonic() > wait_until:
                raise StopObservation('No new cold power-on event within90s')
            time.sleep(.05)
        launch = json.loads(args.power_on.read_text())
        age = time.monotonic()-launch['monotonic_ns']/1e9
        utc_age = (datetime.now(timezone.utc)-datetime.fromisoformat(launch['utc'])).total_seconds()
        if not (launch.get('event') == 'power_on' and launch.get('range') == 128 and
                launch.get('off_s', 0) >= 15 and 0 <= age < 5 and 0 <= utc_age < 5 and abs(age-utc_age) < 1):
            raise StopObservation('Power-on event is stale, unqualified or clock-inconsistent')
        report['power_on'] = launch
        deadline = launch['monotonic_ns']/1e9+12
        time.sleep(max(0, 1.5-age))
        current_guard(args.current, launch, deadline)
        sys.path.insert(0, str(ROOT/'firmware/boot-timing'))
        from nor_bench import Bench
        b = Bench(args.out/'reads')

        def read(address, count, name):
            row = current_guard(args.current, launch, deadline)
            remain = deadline-time.monotonic()
            if remain < 2:
                raise StopObservation('Insufficient time for another bounded read')
            path = b.output/name
            b.call('-u', hex(address), str(count), path, timeout=min(2.5, remain-.25))
            report['debug_reads'] = True
            raw = path.read_bytes()
            report['observations'].append(dict(file=name, address=address, bytes=len(raw),
                sha256=sha(raw), current_A=row['mean'], utc=datetime.now(timezone.utc).isoformat()))
            write_json(args.out/'observation.json', report)
            if len(raw) != count:
                raise RuntimeError('Incomplete read; stop without retry')
            return raw

        p = None
        for index in range(6):
            p = decode_proof(read(FIXED['proof'], 384, f'raw-proof-{index:02}.bin'), names)
            report['raw_proof'] = p
            write_json(args.out/'observation.json', report)
            if error_ready(p):
                break
            if proof_identity(p) and p['result'] == 0:
                raise StopObservation('Successful cycle observed; no error to classify')
            if not proof_identity(p):
                raise StopObservation('Installed normal capture proof not present; preserve raw bytes and stop')
            time.sleep(.15)
        if not error_ready(p):
            raise StopObservation('No failure state observed within bounded proof reads')
        report['fresh_error_proof'] = True
        check_pointers(p)
        card = decode_card(read(FIXED['card'], 200, 'card.bin'))
        report['card'] = card
        report['summary'] = summarize(p, card)
        write_json(args.out/'observation.json', report)
        slot_raw = read(FIXED['magic_slots'], 576, 'magic-slots.bin')
        slots = dict(zip(SLOT_NAMES, struct.unpack_from('<13I', slot_raw)))
        report['magic_slots'] = slots
        report['summary'] = summarize(p, card, slots)
        write_json(args.out/'observation.json', report)
        for extra in args.extras:
            if deadline-time.monotonic() < 3:
                report.setdefault('skipped_extras', []).append(extra); continue
            if extra == 'scb':
                report['cfsr'], report['hfsr'] = struct.unpack('<2I', read(0xE000ED28, 8, 'fault-status.bin'))
            elif extra == 'engine':
                raw = read(0x343C8000, 1536, 'runtime-engine.bin')
                report['runtime_engine_sha256'] = sha(raw)
                report['runtime_engine_matches'] = sha(raw) == m['error_runtime_copy']['sha256']
        report['complete_core_observation'] = True
    except StopObservation as exc:
        report['stopped_reason'] = str(exc)
    except Exception as exc:
        report['error'] = repr(exc)
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        write_json(args.out/'observation.json', report)
    print(json.dumps(report.get('summary', report), indent=2))
    return 1 if 'error' in report else 0


def self_test():
    folder = ROOT/'tmp/bringup/error-relocate-20261026'
    m, names = load_manifest(folder/'flash-normal-v2/manifest.json')
    old = folder/'normal-live-proof'
    p = decode_proof((old/'reads/raw-proof.bin').read_bytes(), names)
    expected = json.loads((old/'observation.json').read_text())
    assert p == {k.removeprefix('RP_').lower(): v for k, v in expected['raw_proof'].items()}
    assert error_ready(p) and p['terminal'] == 0
    check_pointers(p)
    c = decode_card((old/'reads/card.bin').read_bytes())
    assert (c['error'], c['error_stage'], c['error_command'], c['error_sta'], c['cleanup_error']) == (14,5,17,2,10)
    assert summarize(p,c)['result'] == 0x324 and p['scan_headers'] == 2
    altered = dict(p, card=0x40000000)
    try: check_pointers(altered)
    except AssertionError: pass
    else: raise AssertionError('Untrusted pointer admitted')
    launch = dict(monotonic_ns=100000000000)
    row = dict(signal='current', complete_bin=True, nonfinite_count=0, mean=.08,
               processed_monotonic=101.1, first_chunk_received=dict(monotonic_ns=101000000000))
    assert fresh_bin(row,launch,101.2)
    assert not fresh_bin(dict(row, nonfinite_count=1),launch,101.2)
    assert not fresh_bin(row,launch,102)
    assert not fresh_bin(dict(row,first_chunk_received=dict(monotonic_ns=99000000000)),launch,101.2)
    print('Offline parser, fixed pointers, non-RSDN failure and current freshness tests passed; no instrument imported')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--power-on', type=Path)
    parser.add_argument('--current', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--extras', choices=('scb','engine'), nargs='*', default=[])
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:return self_test()
    if any(getattr(args,k) is None for k in ('manifest','power_on','current','out')):
        parser.error('--manifest, --power-on, --current and --out are required')
    return run(args)


if __name__ == '__main__':
    raise SystemExit(main())
