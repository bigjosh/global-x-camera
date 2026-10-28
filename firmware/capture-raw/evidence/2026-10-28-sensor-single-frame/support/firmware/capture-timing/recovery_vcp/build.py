"""Offline PE6 VCP recovery guard around the exact installed v44 receiver.

No debugger, instrument, target-power operation or flash write exists here.
Only the early guard source changes; the complete receiver stays byte-identical.
"""
import argparse
import copy
import json
from pathlib import Path
import re
import shutil
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from build_raw10 import (ROOT, FLASH_OFFSET, checked_manifest, compile_sources,
                        make_image, inspect_image, sha, write_manifest)

BASE_SECTOR_SHA = 'a325b36ed6d3f893ebe0d1153f476fd06fc51c648a1fe55aac15d353c959b4d8'
BASE_PREFIX_SHA = '875d665e050aa2c20e59843c382130d2029035a478230a39f15892ce543c90c6'
BASE_RECEIVER_SHA = '478680d7ca87b19a0bcbab208535b36ab1fd985e141ce69a86b3602963a621ac'
BASE_GUARD_SHA = '07d6e90b38701308ab6c1c5e9edfca33573dc7073c2626d4c684c5d100bd5cab'
VCP_FIELDS = (
    'magic schema words pin nominal_hz window_cycles baud min_low max_low '
    'min_high max_high required first_cycle last_cycle edges good_pulses '
    'bad_pulses max_train last_low last_high request request_cycle initial_level '
    'final_level source_bits polls reserved26 reserved27 reserved28 reserved29 '
    'reserved30 reserved31').split()


def symbol(folder, name):
    match = re.search(r'^([0-9a-fA-F]+) [Tt] ' + re.escape(name) + r'$',
                      (folder/'symbols.txt').read_text(), re.M)
    if not match:
        raise ValueError(f'Missing executable symbol {name}')
    return int(match[1], 16)


def validate_base(base, rm, pm):
    original = (base/'staged/capture_sector_0.bin').read_bytes()
    prefix = (base/'staged/stage1.bin').read_bytes()
    receiver = (base/'receiver/capture.bin').read_bytes()
    if (len(original) != 65536 or sha(original) != BASE_SECTOR_SHA or
            pm['program_sha256'] != BASE_SECTOR_SHA):
        raise ValueError('Only the exact installed v44 sector is supported')
    if sha(prefix) != BASE_PREFIX_SHA or pm['stage1_raw_sha256'] != BASE_PREFIX_SHA:
        raise ValueError('Unexpected v44 prefix')
    if (sha(receiver) != BASE_RECEIVER_SHA or rm['raw_sha256'] != BASE_RECEIVER_SHA or
            pm['stage2_sha256'] != BASE_RECEIVER_SHA):
        raise ValueError('Unexpected v44 receiver')
    if original[FLASH_OFFSET:FLASH_OFFSET+len(receiver)] != receiver:
        raise ValueError('Receiver differs from sector')
    if sha((base/'staged/recovery_gpio.c').read_bytes()) != BASE_GUARD_SHA:
        raise ValueError('Original PE1 guard source differs')
    source = (base/'staged/stage1.c').read_text()
    anchors = ('    status_led_boot_begin();', '    recovery_gpio_begin();',
               '    BSEC->DBGCR =', '    recovery_gpio_check();',
               '    raw10_memory_init();', '    recovery_gpio_publish();',
               'int sensor_result =', 'x->AR=STAGE2_FLASH_OFFSET;')
    positions = [source.index(a) for a in anchors]
    if positions != sorted(positions):
        raise ValueError('Guard hooks moved relative to safety boundaries')
    return original, receiver


def compose_sector(original, boot):
    if len(original) != 65536 or len(boot) > FLASH_OFFSET:
        raise ValueError('Prefix overlaps receiver or sector size is wrong')
    combined = bytearray(original)
    combined[:len(boot)] = boot
    if combined[len(boot):] != original[len(boot):]:
        raise ValueError('Only occupied boot-prefix bytes may change')
    return bytes(combined)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base, out = args.base.resolve(), args.output.resolve()
    rm, pm = (checked_manifest(base/name) for name in ('receiver', 'staged'))
    original, receiver = validate_base(base, rm, pm)
    out.mkdir(parents=True, exist_ok=False)
    rdir, pdir = out/'receiver', out/'staged'
    shutil.copytree(base/'receiver', rdir)
    pdir.mkdir()
    sources = []
    for path in pm['sources']:
        source = ROOT/path
        target = pdir/source.name
        target.write_bytes((HERE/source.name if source.name == 'recovery_gpio.c'
                            else source).read_bytes())
        sources.append(target)
    target = pdir/'pulse_detector.h'
    target.write_bytes((HERE/'pulse_detector.h').read_bytes())
    sources.append(target)
    flags = list(pm['compile_flags'])
    raw, size = compile_sources(pdir, [p for p in sources if p.suffix in ('.c', '.S')],
                                flags, pdir/'stage1.ld', 'stage1')
    park = symbol(pdir, 'recovery_gpio_park')
    if park & 1 or raw[park-0x34180400:park-0x34180400+2] != bytes.fromhex('fee7'):
        raise ValueError('Recovery park must remain the exact branch-to-self instruction')
    for source in sources:
        if source.name not in ('recovery_gpio.c', 'pulse_detector.h'):
            if source.read_bytes() != (base/'staged'/source.name).read_bytes():
                raise ValueError(f'Unrelated prefix source changed: {source.name}')
    if (rdir/'capture.bin').read_bytes() != receiver:
        raise ValueError('Copied receiver changed')
    boot = make_image(raw)
    combined = compose_sector(original, boot)
    (pdir/'stage1_boot.bin').write_bytes(boot)
    (pdir/'stage2.bin').write_bytes(receiver)
    (pdir/'capture_sector_0.bin').write_bytes(combined)
    manifest = copy.deepcopy(pm)
    for name in tuple(manifest):
        if name.startswith('guard_sources_byte_identical') or name in (
                'recovery_code_and_literals_bytes_identical',
                'prefix_first_bytes_identical_to_v36', 'prefix_same_size_as_v36',
                'prefix_byte_differences_vs_v36'):
            manifest.pop(name)
    manifest.update(
        hardware_status='untested', stage1=inspect_image(boot),
        stage1_raw_bytes=len(raw), stage1_raw_sha256=sha(raw),
        program_sha256=sha(combined), size=size, compile_flags=flags,
        stage2_build_manifest=str(rdir/'manifest.json'),
        stage2_manifest_sha256=sha((rdir/'manifest.json').read_bytes()),
        frozen_program_sha256=BASE_SECTOR_SHA,
        frozen_prefix_manifest_sha256=sha((base/'staged/manifest.json').read_bytes()),
        receiver_byte_identical_to_v44=True, prefix_requires_new_exact_allowlist=True,
        generator_inputs={str(p.relative_to(ROOT)): sha(p.read_bytes())
                          for p in (Path(__file__), HERE/'recovery_gpio.c',
                                    HERE/'pulse_detector.h')})
    manifest['recovery_gpio'].update(
        park_address=hex(park), receiver_unchanged=True,
        clock_qualification='Existing 40000-cycle deadline, additive PE6 detector; hardware untested',
        reserved_semantics='request source bits: bit0 PE1 low, bit1 qualified PE6 pulse train',
        source_compatibility='PE1 behavior and cache/context checks retained; guard binary changed')
    manifest['recovery_vcp'] = dict(
        schema=1, pin='PE6', header='CN15.2', internal_pull='up',
        status_address='0x341f7080', published_status_address='0x343f7080',
        status_words=len(VCP_FIELDS), status_fields=VCP_FIELDS,
        baud=1000000, pattern='three complete 0x00-byte low pulses, 8N1',
        min_low_cycles=2400, max_low_cycles=5200,
        min_high_cycles=100, max_high_cycles=1600,
        required_pulses=3, window_cycles=40000, nominal_clock_hz=400000000,
        deadline='same begin timestamp and deadline as PE1 settling; no wait extension',
        retries='host bounded reset/retry after safe idle verification; long USB gaps may miss',
        break_behavior='ST-LINK BREAK controls NRST on measured V3J15M6, not PE6',
        qualification='offline tested only; no claim of installed or qualified hardware recovery')
    write_manifest(pdir, manifest, sources)
    print(json.dumps(dict(
        receiver=str(rdir), staged=str(pdir), receiver_bytes=len(receiver),
        receiver_sha256=sha(receiver), prefix_raw_bytes=len(raw),
        prefix_boot_bytes=len(boot), prefix_raw_sha256=sha(raw),
        program_sha256=sha(combined), recovery_park_address=hex(park),
        recovery_status_address='0x341f7000', vcp_status_address='0x341f7080',
        status='built offline; hardware untested')))


if __name__ == '__main__':
    main()
