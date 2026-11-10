"""One guarded physical NOR READ, using the immutable qualified read-only helper.

Offline by default. Root alone may pass --execute after independently entering
normal firmware's UART recovery park. This script rechecks that park live; it
never requests reset, power control, UART recovery, erase, program or a retry.
All target writes are to fixed SRAM locations or core registers to run READ.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BUILD = ROOT / 'tmp/bringup/rom-nor-maintenance-readonly-20261017'
NORMAL = ROOT / 'tmp/bringup/sensor-autostop-promote-20261028/flash-standby-v1/staged'
PREFIX_SHA = '6378483a91b560ffc6b31d74a9dd1205996a14c8030447ffddf7deddc9d23874'
SECTOR_SHA = '79a379470927135bc03841098fe070912cad8275e91c5d5985cc066c294cf64e'
HELPER_SHA = 'd6b63e6e993a9cb872cfe482c0fd4f8954f8edc398a7dfb1db25982b9e255b5d'
PINNED = {
    'firmware/boot-timing/nor_bench.py': 'd76e1bb8156deaafc9508468be9ec52c12d2a924dbe8559ae503f369127feeb2',
    'firmware/capture-timing/recovery_gpio/check_park.py': '9671bca1b4299118a0b36c8e958b9e4274fd56f1708bb0d369cd98d1974ee2ca',
    'firmware/capture-timing/prepare_maintenance.py': 'f2be3965d29fb1fc1f8337ee39d349b4d074eff9da30893c6d126cf946bf5013',
    'firmware/capture-timing/bench.py': '5850e7afeb84e8cc33f862aea2105270920a3dce85d81ab23fdfE0434d33fd9f'.lower(),
}
FIELDS = ('magic result requested_bytes read_count polls last_sr control ipsr cpu_ccr original_msp original_msplim '
          'ahb5enr ahb5rstr mux_cr cr dcr1 dcr2 initial_sr ccr tcr ir initial_dlr initial_ar sequence command flash_offset').split()
CONFIG = dict(mux_cr=2, cr=0x10000001, dcr1=0x001F0000, dcr2=1,
              ccr=0x01002101, tcr=8, ir=0x0B)
REGISTERS = dict(mux_cr=0x5802B400, cr=0x58025000, dcr1=0x58025008,
                 dcr2=0x5802500C, initial_sr=0x58025020,
                 ccr=0x58025100, tcr=0x58025108, ir=0x58025110)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def save(path, data):
    with path.open('x', encoding='utf-8') as output:
        json.dump(data, output, indent=2, allow_nan=False)
        output.write('\n')


def validate_configuration(status):
    require(status['ahb5enr'] & 0x2020 == 0x2020 and not status['ahb5rstr'] & 0x2020,
            'Required XSPI/XSPIM clock or reset state invalid')
    require(all(status[key] == value for key, value in CONFIG.items()), 'ROM XSPI configuration differs')
    require(not status['initial_sr'] & 0x7F21, 'XSPI BUSY, FIFO or error before read')


def validate_done(status, sequence):
    require(status['magic'] == 0x444F4E45 and status['sequence'] == sequence,
            'No fresh matching DONE record')
    require(status['result'] == 0 and status['command'] == 1 and status['flash_offset'] == 0,
            'READ refused or failed')
    require(status['requested_bytes'] == status['read_count'] == 65536, 'Incomplete NOR read')
    require(status['control'] == status['ipsr'] == 0 and not status['cpu_ccr'] & 0x30000,
            'Unexpected CPU context/cache state')
    require(0 < status['polls'] <= 8000000, 'Invalid finite poll evidence')
    validate_configuration(status)
    require(status['last_sr'] == 2, 'NOR controller not complete and idle')


def check_assets():
    for path, expected in PINNED.items():
        require(sha(ROOT / path) == expected, 'Host support changed: ' + path)
    require(sha(BUILD / 'read.bin') == HELPER_SHA, 'Read-only helper differs')
    require(len((BUILD / 'read.bin').read_bytes()) == 728, 'Helper length differs')
    manifest = json.loads((BUILD / 'manifest.json').read_text())
    require(manifest['binary_sha256'] == HELPER_SHA and manifest['load'] == '0x341B0000'
            and manifest['thumb_entry'] == '0x341B0001' and manifest['ready_loop'] == '0x341b0252'
            and manifest['status_fields_in_word_order'] == FIELDS, 'Read helper layout differs')
    require(sha(NORMAL / 'stage1.bin') == PREFIX_SHA, 'Selected normal prefix differs')
    require(sha(NORMAL / 'capture_sector_0.bin') == SECTOR_SHA, 'Selected reference sector differs')
    require(len((NORMAL / 'capture_sector_0.bin').read_bytes()) == 65536, 'Wrong reference size')
    return dict(host_sources=PINNED, helper_sha256=HELPER_SHA, selected_prefix_sha256=PREFIX_SHA,
                selected_sector_sha256=SECTOR_SHA, runner_sha256=sha(Path(__file__)))


def load_support():
    sys.path.insert(0, str(ROOT / 'firmware/boot-timing'))
    from nor_bench import Bench
    spec = importlib.util.spec_from_file_location('identity_check_park', ROOT / 'firmware/capture-timing/recovery_gpio/check_park.py')
    park = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(park)
    return Bench, park


def execute(out, sequence, assets):
    out.mkdir(parents=True, exist_ok=False)
    state = dict(passed=False, started_utc=now(), phase='before_live_park_check', assets=assets,
                 sequence=sequence, nor_programming=False, sd_commands=False,
                 reset_requested=False, power_control=False, target_state='not yet checked')
    save(out / 'request.json', state)
    try:
        # Fresh proof in this invocation, not permission inferred from an old JSON.
        check = ROOT / 'firmware/capture-timing/recovery_gpio/check_park.py'
        command = [sys.executable, str(check), '--build', str(NORMAL), '--out', str(out / 'park')]
        save(out / 'park-command.json', dict(argv=command, utc=now()))
        with (out / 'park.log').open('xb') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True,
                           timeout=240, creationflags=subprocess.CREATE_NO_WINDOW)
        proof = json.loads((out / 'park/result.json').read_text())
        require(proof['passed'] and proof['prefix_sha256'] == PREFIX_SHA and proof['ccr'] == 0x201,
                'Fresh normal recovery context not proven')
        Bench, park = load_support()
        bench = Bench(out / 'read')
        def word(address, name):
            return struct.unpack('<I', bench.upload(address, 4, name + '.bin'))[0]
        state['phase'] = 'read_live_controller_configuration'
        before = dict(ahb5enr=word(0x56028260, 'ahb5enr'), ahb5rstr=word(0x56028220, 'ahb5rstr'))
        park.validate_xspi_clock(before['ahb5enr'], before['ahb5rstr'])
        for key, address in REGISTERS.items():
            before[key] = word(address, 'before-' + key)
        save(out / 'controller-before.json', before)
        validate_configuration(before)
        stale = bench.upload(0x341B4100, 104, 'old-status.bin')
        require(sequence != struct.unpack('<26I', stale)[23], 'Sequence collides with existing status')
        cmd = out / 'command.bin'
        cmd.write_bytes(struct.pack('<5I', 0x4E4F5244, sequence, 1, 65536, 0))
        clear = out / 'clear-status.bin'
        clear.write_bytes(bytes(104))
        state['phase'] = 'load_immutable_read_helper_and_clear_status'
        bench.call('-halt', '-w', BUILD / 'read.bin', '0x341B0000', '-v',
                   '-w', clear, '0x341B4100', '-v', '-w', cmd, '0x341B4000', '-v',
                   success='Download verified successfully')
        require(hashlib.sha256(bench.upload(0x341B0000, 728, 'helper-readback.bin')).hexdigest() == HELPER_SHA,
                'Helper RAM readback differs')
        require(bench.upload(0x341B4100, 104, 'cleared-status-readback.bin') == bytes(104), 'Status did not clear')
        require(bench.upload(0x341B4000, 20, 'command-readback.bin') == cmd.read_bytes(), 'Command readback differs')
        context = park.registers(bench.call('-halt', '-coreReg'))
        ccr, fpccr = word(0xE000ED14, 'immediate-ccr'), word(0xE000EF34, 'immediate-fpccr')
        park.validate_context(context, 0x3418078C, ccr, fpccr)
        require(not word(0x58025020, 'immediate-xspi-sr') & 0x7F21, 'XSPI became busy before entry')
        save(out / 'immediate-entry-proof.json', dict(context=context, ccr=ccr, fpccr=fpccr))
        state['phase'] = 'execute_one_physical_READ'
        bench.call('-halt', '-coreReg', 'PC=0x341B0001', 'XPSR=0x01000000', '-run', success='Core run')
        state['target_state'] = 'read helper may be executing; no automatic recovery on failure'
        deadline = time.monotonic() + 30
        for index in range(6):
            raw = bench.upload(0x341B4100, 104, f'status-{index:02d}.bin')
            status = dict(zip(FIELDS, struct.unpack('<26I', raw)))
            save(out / f'status-{index:02d}.json', status)
            if status['magic'] == 0x444F4E45 and status['sequence'] == sequence:
                break
            require(time.monotonic() < deadline, 'No fresh DONE by deadline; target left as-is')
            time.sleep(.05)
        else:
            raise TimeoutError('No fresh DONE in bounded polling; target left as-is')
        validate_done(status, sequence)
        state['phase'] = 'compare_physical64KiB_readback'
        context = park.registers(bench.call('-halt', '-coreReg'))
        require(context.get('PC') in (0x341B0252, 0x341B0254) and context.get('CONTROL') == 0
                and context.get('PRIMASK') == 1 and context.get('FAULTMASK') == 0
                and not context.get('XPSR', 511) & 511 and context.get('XPSR', 0) & (1 << 24),
                'Read helper is not at its reviewed awake completion loop')
        raw = bench.upload(0x341D0000, 65536, 'readback.bin')
        actual = hashlib.sha256(raw).hexdigest()
        expected = (NORMAL / 'capture_sector_0.bin').read_bytes()
        mismatches = [i for i, (left, right) in enumerate(zip(raw, expected)) if left != right]
        save(out / 'comparison.json', dict(bytes=len(raw), actual_sha256=actual, expected_sha256=SECTOR_SHA,
            exact_match=not mismatches, mismatching_bytes=len(mismatches), first_mismatch_offsets=mismatches[:32]))
        require(not mismatches and actual == SECTOR_SHA, 'Full physical NOR differs from selected normal firmware')
        require(word(0x58025020, 'final-xspi-sr') == 2, 'Controller not idle after readback')
        state.update(passed=True, phase='complete', finished_utc=now(), physical_nor_sha256=actual,
            bytes_read=65536, matching_reference=True, target_state='read-only helper awake completion loop',
            final_context=context, persistent_halt_after_disconnect='not guaranteed; may resume only exact ready loop',
            normal_firmware_restored_to_execution=False, followup='Root must separately recover or power off; no automatic boot performed')
        save(out / 'verified.json', state)
        print(json.dumps(state, indent=2))
    except BaseException as exc:
        state.update(finished_utc=now(), error=repr(exc), traceback=traceback.format_exc(),
                     failure_action='No reset, retry, power change or further target access')
        save(out / 'failure.json', state)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--sequence', type=int, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    out = args.out.resolve()
    out.relative_to(HERE)
    require(not out.exists(), 'Output must be new')
    require(0 < args.sequence < 2**32, 'Sequence must be a nonzero32bit value')
    assets = check_assets()
    if not args.execute:
        print(json.dumps(dict(offline=True, assets=assets, output=str(out), sequence=args.sequence,
            hardware_access=False, next='Root only: enter fresh normal UART recovery, then review --execute'), indent=2))
        return
    execute(out, args.sequence, assets)


if __name__ == '__main__':
    main()
