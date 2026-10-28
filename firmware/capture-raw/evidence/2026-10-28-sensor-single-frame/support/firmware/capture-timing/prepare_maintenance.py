"""Abandon a completed capture into a checked integer-only maintenance context.

RAM/core/cache operations only; no reset, power control, or NOR commands. The
immutable cache helper must be unchanged at its reserved address. This does not
return to the application. Run the frozen NOR helper's INFO before any WRITE.
An explicit failed-PHY build permits only separately reviewed PHY terminal
failures, with an exact binary/PC allowlist and live reset/no-DMA evidence.
For raw10, recognized storage-loader/module records must prove completed success
before any halt. Supply --save-build and --save-sha256 to bind that proof to the
exact live module; event40 alone is insufficient after integrated SD saving.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
from bench import REPO, sha, late_phy_region, LATE_PHY_WORDS

CACHE = REPO / 'tmp/bringup/capture-maintenance-cache-20261017/cache_prep.bin'
CACHE_SHA = 'e084dfd2aaedd80c26ffaaf7b51e161ac804edb053f54c9f4ce5a68609f54e9a'
CACHE_LOAD, CACHE_STATUS = 0x341A0000, 0x341A0400
PHY_RECEIVER_LOAD = 0x34300000
APB5RSTR_ADDRESS = 0x5602823C
DCMIPP_RESET = 4
# Populated only with reviewed, built binaries. A self-consistent manifest
# is not authorization: unknown binaries fail closed before any hardware call.
APPROVED_FAILED_PHY_BUILDS = {
    # capture-phy-early-v30b-final-20261017 / receiver
    'ccbb4d1dfd20600668a1f9f776713fade500e94d06da02d9781c7d7772c80bb5':
        dict(raw_bytes=12936, park_address=0x3430142A, phy_release_mode='early'),
    # capture-phy-late-v30b-final-20261017 / receiver
    '057a48e6626e7997efb5fc85945ade44c9e756e33e7057631a2f2c72a53eee2b':
        dict(raw_bytes=12948, park_address=0x3430142A, phy_release_mode='late'),
    # v30d guards diagnostic reads while CSI is reset or unclocked.
    '4ddd5a6c5167ebba4064b92a00d54adbacd7e08cdf3695d2d2dc8b81357b9af6':
        dict(raw_bytes=13020, park_address=0x3430146A, phy_release_mode='early',
             system_core_clock_offset=0x32D8),
    '5882d058f46ec11211cfe39dc1d10319a7eab9ffcd4e6ab2117074b2feefcf22':
        dict(raw_bytes=13032, park_address=0x3430146A, phy_release_mode='late',
             system_core_clock_offset=0x32E4),
    # v31 changes only the matched sensor-clock experiment to noncontinuous.
    '2d582f1c26ba7df95c00d5a7184d62fd41b6fbd15c61bbafdcb2362faf29d239':
        dict(raw_bytes=13020, park_address=0x3430146A, phy_release_mode='early',
             system_core_clock_offset=0x32D8),
    '9c6c93b7fd4ca8703318785c0903020811249b675ef25bb442eeead4d7ce1794':
        dict(raw_bytes=13032, park_address=0x3430146A, phy_release_mode='late',
             system_core_clock_offset=0x32E4),
    # v32 late/noncontinuous diagnostic triggers sensor frame 2 without rearming.
    '4c49b5c339b8ca81b4af154ff341d91baf1be1363fa2f135b64ca8cfbea09895':
        dict(raw_bytes=13484, park_address=0x3430146A, phy_release_mode='late',
             system_core_clock_offset=0x34A8),
    # v33 keeps the early clock receiver enabled and delays both data lanes.
    '678eadf3a9bf424bd7e6ccbe40aeff02f796c02669db158bcde34b455e52b1b8':
        dict(raw_bytes=13160, park_address=0x3430146A, phy_release_mode='early',
             system_core_clock_offset=0x3364),
}

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'boot-timing'))
from nor_bench import Bench


def registers(text):
    return {name: int(value, 16) for name, value in
            re.findall(r'^(PC|XPSR|CONTROL|PRIMASK|FAULTMASK)\s*=\s*0x([0-9A-Fa-f]+)', text, re.M)}


def checked_clock_offset(code, approved):
    """Only the reviewed final .data.SystemCoreClock word can be mutable."""
    offset = approved.get('system_core_clock_offset')
    if offset is not None and (type(offset) is not int or offset < 0 or offset % 4
            or offset != len(code) - 4
            or code[offset:] != struct.pack('<I', 64_000_000)):
        raise ValueError('Failed-PHY SystemCoreClock layout or initializer differs from review')
    return offset


def validate_live_receiver(code, present, approved):
    offset = checked_clock_offset(code, approved)
    immutable_bytes = len(code) if offset is None else offset
    if len(present) != len(code) or present[:immutable_bytes] != code[:immutable_bytes]:
        raise ValueError('Live receiver bytes differ from the reviewed failed-PHY binary')
    proof = dict(live_code_matches=(present == code), live_immutable_code_matches=True,
                 immutable_bytes=immutable_bytes)
    if offset is not None:
        runtime_clock, = struct.unpack('<I', present[offset:])
        if runtime_clock != 400_000_000:
            raise ValueError('Live SystemCoreClock differs from the reviewed 400 MHz profile')
        proof['system_core_clock'] = dict(address=hex(PHY_RECEIVER_LOAD + offset),
                                        initial_hz=64_000_000, runtime_hz=runtime_clock)
    return proof


def checked_failed_phy_build(build):
    manifest = json.loads((build / 'manifest.json').read_text(encoding='utf-8-sig'))
    code = (build / 'capture.bin').read_bytes()
    digest = sha(code)
    approved = APPROVED_FAILED_PHY_BUILDS.get(digest)
    if approved is None or manifest.get('raw_sha256') != digest:
        raise ValueError('Failed-PHY binary is not in the reviewed allowlist')
    expected = dict(raw_bytes=approved['raw_bytes'], vector_address='0x34300000',
                    trace_address='0x343f0000', phy_release_mode=approved['phy_release_mode'],
                    failure_recovery_schema=1, failure_park_symbol='late_failure_idle',
                    failure_park_address=hex(approved['park_address']))
    for key, value in expected.items():
        if type(manifest.get(key)) is not type(value) or manifest[key] != value:
            raise ValueError(f'Failed-PHY manifest mismatch: {key}')
    if (manifest.get('parameters', {}).get('late_phy_experiment') is not True
            or len(code) != approved['raw_bytes']):
        raise ValueError('Not the reviewed late-PHY receiver layout')
    late_phy_region(manifest)
    offset = approved['park_address'] - PHY_RECEIVER_LOAD
    # Thumb B . occupies one instruction; no permissive function/range check.
    if not 0 <= offset < len(code) - 1 or code[offset:offset + 2] != b'\xfe\xe7':
        raise ValueError('Failed-PHY terminal instruction is not the reviewed branch-to-self')
    checked_clock_offset(code, approved)
    return manifest, code, dict(approved, raw_sha256=digest)


def validate_failed_phy_evidence(trace, status, live_reset, approved):
    if len(trace) != 64 or len(status) != LATE_PHY_WORDS:
        raise ValueError('Incomplete failed-PHY proof')
    where = status[16]
    expected_mode = 1 if approved['phy_release_mode'] == 'late' else 0
    if (status[0] != 0x4C505231 or not 0 < where <= 0x98
            or status[1] != (0xF0000000 | where) or not 0 < status[2] <= 128
            or status[6] != expected_mode or status[17] == 0
            or trace[0] != 0x43545031 or trace[1] != (0x80000000 | where)
            or trace[3] != status[17] or not 0 < trace[2] <= 200):
        raise ValueError('Failed-PHY terminal trace and diagnostic proof do not agree')
    if (status[18] != 1 or status[19] != 0x51554945
            or not status[29] & DCMIPP_RESET
            or (status[28] ^ status[29]) & ~DCMIPP_RESET
            or live_reset != status[29]):
        raise ValueError('Failed-PHY DCMIPP reset/no-DMA proof is absent or no longer live')


def validate_context(context, failed_phy=None):
    if (context.get('XPSR', 511) & 511 or context.get('CONTROL', 3) & ~0xC
            or context.get('FAULTMASK') != 0):
        raise ValueError('Require idle privileged MSP Thread mode, FP ownership flags only')
    if failed_phy is not None and (context.get('PC') != failed_phy['park_address']
                                    or context.get('PRIMASK') != 1
                                    or not context.get('XPSR', 0) & (1 << 24)):
        raise ValueError('Failed-PHY core is not at the exact IRQ-masked terminal instruction')


def read_failed_phy_proof(bench, trace, manifest, code, approved):
    """Read-only authorization before halting; no RAM writes or resets here."""
    address, count = late_phy_region(manifest)
    status = struct.unpack(f'<{count}I', bench.upload(address, count * 4, 'failed-phy-status.bin'))
    reset, = struct.unpack('<I', bench.upload(APB5RSTR_ADDRESS, 4, 'failed-phy-reset.bin'))
    validate_failed_phy_evidence(trace, status, reset, approved)
    present = bench.upload(PHY_RECEIVER_LOAD, len(code), 'failed-phy-live-code.bin')
    code_proof = validate_live_receiver(code, present, approved)
    return dict(raw_sha256=approved['raw_sha256'], **code_proof,
                park_address=hex(approved['park_address']), failure_where=status[16],
                failure_result=status[17], live_apb5rstr=hex(reset),
                diagnostic_status_words=list(status), no_dma_reset_proven=True)


def save_guard_module():
    """Load the shared RAM-save proof decoder without invoking its CLI."""
    path = REPO / 'firmware/capture-sd/bench.py'
    spec = importlib.util.spec_from_file_location('capture_sd_maintenance_guards', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_storage_proof(bench, checked_save=None):
    """Read-only gate: event40 alone does not prove SD/NOR storage is idle."""
    guard = save_guard_module()
    guard.reject_low_power_completion(bench)
    loader = struct.unpack('<16I', bench.upload(guard.LOADER, 64, 'storage-loader.bin'))
    raw = bench.upload(guard.REPORT, 512, 'storage-report.bin')
    report = guard.decode_report(raw)
    if not guard.validate_storage_activity(loader, report):
        return dict(recognized=False, legacy_completed_capture=True)
    if checked_save is None:
        raise ValueError('Recognized storage proof requires --save-build and --save-sha256 before any halt')
    manifest, code = checked_save
    proof = guard.exact_storage_proof(bench, manifest, code, loader, raw, 'storage')
    # Completion-enabled firmware announces LPL ownership before SAVE starts.
    # Recheck after DONE so a host read spanning the save cannot miss ownership.
    guard.reject_low_power_completion(bench, 'post-save-')
    return dict(recognized=True, **proof)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--layout', choices=('raw8', 'raw10'), default='raw8')
    p.add_argument('--failed-phy-build', type=Path,
                   help='Explicit reviewed receiver failure only; never prefix failures')
    p.add_argument('--save-build', type=Path,
                   help='Exact storage-module build for recognized post-capture storage proof')
    p.add_argument('--save-sha256',
                   help='Explicit reviewed storage-module SHA-256; required with --save-build')
    a = p.parse_args()
    if bool(a.save_build) != bool(a.save_sha256):
        p.error('--save-build and --save-sha256 must be supplied together')
    if a.save_build and a.layout != 'raw10':
        p.error('Storage-module proof requires --layout raw10')
    checked_save = None
    if a.save_build:
        checked_save = save_guard_module().checked_build(a.save_build.resolve(), a.save_sha256)
    failed_phy = None
    if a.failed_phy_build:
        if a.layout != 'raw10':
            p.error('--failed-phy-build requires --layout raw10')
        failed_phy = checked_failed_phy_build(a.failed_phy_build)
    cache_path, cache_sha = CACHE, CACHE_SHA
    cache_load, cache_status = CACHE_LOAD, CACHE_STATUS
    trace_address = 0x341F0000
    if a.layout == 'raw10':
        trace_address = 0x343F0000
        cache_path = REPO / 'tmp/bringup/capture-maintenance-cache-raw10-20261017/cache_prep.bin'
        cache_sha = '59427aa1c107a24378a35c3f85eb7f7d4fc1209115a319f05d3322646f62943d'
        cache_load, cache_status = 0x343C0000, 0x343C0400
    b = Bench(a.out)
    trace = struct.unpack('<64I', b.upload(trace_address, 256, 'capture-trace.bin'))
    failure_proof = None
    if failed_phy:
        failure_proof = read_failed_phy_proof(b, trace, *failed_phy)
    elif trace[0] != 0x43545031 or trace[1] != 40:
        raise ValueError('Require a completed capture; no interruption of active operations')
    # The integrated receiver publishes loader ACTIVE before event40. Recognized
    # partial/error/nonidle storage records must never reach the first halt.
    storage_proof = read_storage_proof(b, checked_save) if a.layout == 'raw10' else None
    context = registers(b.call('-halt', '-coreReg'))
    validate_context(context, failed_phy[2] if failed_phy else None)
    if failed_phy:
        # Recheck the safety condition after the exact terminal PC is observed.
        reset, = struct.unpack('<I', b.upload(APB5RSTR_ADDRESS, 4, 'failed-phy-reset-halted.bin'))
        validate_failed_phy_evidence(trace, failure_proof['diagnostic_status_words'], reset, failed_phy[2])
    fpccr, = struct.unpack('<I', b.upload(0xE000EF34, 4, 'fpccr.bin'))
    if fpccr & 1:
        raise ValueError('Lazy FP save active; do not discard this context')
    code = cache_path.read_bytes()
    if sha(code) != cache_sha:
        raise ValueError('Frozen cache helper hash mismatch')
    present = b.upload(cache_load, len(code), 'cache-before.bin')
    if present != code and any(present):
        raise ValueError('RAM helper differs; fresh cold-boot procedure required')
    clear = b.output / 'clear-cache.bin'
    clear.write_bytes(bytes(20))
    b.call('-halt', '-w', clear, hex(cache_status), '-v',
           '-w', cache_path, hex(cache_load), '-v', '-coreReg',
           'PRIMASK=1', f'PC={hex(cache_load + 1)}', 'XPSR=0x01000000', '-run', success='Core run')
    status = struct.unpack('<5I', b.upload(cache_status, 20, 'cache-after.bin'))
    if status[0] != 0x43414348 or status[3] != 0 or status[4] & 0x30000:
        raise RuntimeError('Cache helper did not complete as expected')
    parked = registers(b.call('-halt', '-coreReg'))
    if parked.get('PC') not in (cache_load + 0x72, cache_load + 0x74) or parked.get('PRIMASK') != 1:
        raise RuntimeError('Cache helper not in its IRQ-masked idle loop')
    b.call('-coreReg', 'CONTROL=0', 'PRIMASK=1')
    final = registers(b.call('-coreReg'))
    if final.get('CONTROL') != 0 or final.get('PRIMASK') != 1 or final.get('FAULTMASK') != 0 or final.get('XPSR', 511) & 511:
        raise RuntimeError('Core context did not read back as requested')
    result = dict(initial=context, fpccr=fpccr, cache_status=status, final=final,
                  flash_commands_sent=False, application_abandoned=True, layout=a.layout,
                  cache_helper_sha256=cache_sha)
    if failure_proof:
        result['failed_phy_recovery'] = failure_proof
    if storage_proof is not None:
        result['storage_proof'] = storage_proof
    (b.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
