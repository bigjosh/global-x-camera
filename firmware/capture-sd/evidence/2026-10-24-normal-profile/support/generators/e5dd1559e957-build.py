"""Build LED phase/sleep firmware offline from the exact qualified v41 sector.

No debugger, instrument, power-control or flash-programming operation exists
here. The new prefix requires an exact host allowlist and hardware recovery
qualification before normal deployment.
"""
import argparse
import copy
import json
from pathlib import Path
import re
import struct
import sys
import zlib

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from build_raw10 import (ROOT, FLASH_OFFSET, checked_manifest, compile_sources,
                        make_image, inspect_image, replace, sha, write_manifest)

BASE_SECTOR_SHA = 'c92ee95920009b188aef53645fce8e9bb6cb8bd34d78cf789d252037be16af2f'
BASE_PREFIX_SHA = '0886559c3e4b5ddd358eb25a4f0c4ad4b40f588839c089a0fe1320675e28abce'
BASE_RECEIVER_SHA = '6fa14460353979430c4e1dde6ba79e80d865e646a851ea9c09dd00022a6d835e'
GUARD_SHA = '07d6e90b38701308ab6c1c5e9edfca33573dc7073c2626d4c684c5d100bd5cab'
GUARD_HEADER_SHA = '2d1b3acf598021a9122fc2c0ab0474afffd40d2664905ab9e91f276e341d09fc'
PROOF_FIELDS = [
    'magic', 'schema', 'words', 'phase', 'red_cycle', 'red_odr', 'red_idr',
    'blue_cycle', 'blue_odr', 'blue_idr', 'off_cycle', 'off_odr', 'off_idr',
    'sleep_cycle', 'sleep_odr', 'sleep_idr', 'moder', 'otyper', 'ospeedr',
    'pupdr', 'scr', 'primask', 'systick_ctrl', 'icsr', 'sleep_state',
    'nvic_enable_or', 'nvic_pending_or', 'ahb4enr',
    'error_cycle', 'error_odr', 'error_idr', 'reserved',
]


def transform_prefix(text):
    text = replace(text, '#include "recovery_gpio.h"',
                   '#include "recovery_gpio.h"\n#include "status_leds.h"')
    text = replace(text, '    recovery_gpio_begin();',
                   '    status_led_boot_begin();\n    recovery_gpio_begin();')
    return replace(text, '    raw10_memory_init();\n    recovery_gpio_publish();',
                   '    raw10_memory_init();\n    recovery_gpio_publish();\n    status_led_proof_init();')


def transform_capture(text):
    text = replace(text, '#include <stdarg.h>', '#include <stdarg.h>\n#include "status_leds.h"\n'
                   'extern void status_led_complete_sleep(void) __attribute__((noreturn));')
    text = replace(text,
        'void HAL_GPIO_EXTI_Rising_Callback(uint16_t pin) { if(pin==GPIO_PIN_0) { fast_strobes++; event(50); } }',
        '''void HAL_GPIO_EXTI_Rising_Callback(uint16_t pin)
{
  if(pin==GPIO_PIN_0) {
    fast_strobes++; event(50);
    /* Preserve the original timing marker; only the FIRST exposure changes LEDs. */
    if(fast_strobes==1U) status_led_proof_phase(STATUS_LED_ACQUIRE,LED_P_BLUE_CYCLE);
  }
}''')
    text = replace(text,
        '{ (void)h; if (pipe == 0) { frames++; event(30); if(frames==1U) FAST[31]=fast_strobes; fast_snapshot(430); } }',
        '''{
  (void)h;
  if(pipe==0) {
    frames++; event(30);
    if(frames==1U) {
      FAST[31]=fast_strobes;
      status_led_proof_phase(STATUS_LED_OFF,LED_P_OFF_CYCLE);
    }
    fast_snapshot(430);
  }
}''')
    text = replace(text, '  __disable_irq();\n  TRACE[3] = (uint32_t)result;',
                   '  __disable_irq();\n  status_led_proof_phase(STATUS_LED_ERROR,LED_P_ERROR_CYCLE);\n'
                   '  TRACE[3] = (uint32_t)result;')
    text = replace(text, 'void HardFault_Handler(void) {\n',
                   'void HardFault_Handler(void) {\n  status_led_set(STATUS_LED_ERROR);\n')
    return replace(text, '  event(40);\n  for (;;) __NOP();',
                   '  event(40);\n  status_led_complete_sleep();')


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
    if len(original) != 65536 or sha(original) != BASE_SECTOR_SHA or pm['program_sha256'] != BASE_SECTOR_SHA:
        raise ValueError('Only the exact default-exposure v41 sector is supported')
    if sha(prefix) != BASE_PREFIX_SHA or pm['stage1_raw_sha256'] != BASE_PREFIX_SHA:
        raise ValueError('Unexpected v41 prefix')
    if sha(receiver) != BASE_RECEIVER_SHA or rm['raw_sha256'] != BASE_RECEIVER_SHA or pm['stage2_sha256'] != BASE_RECEIVER_SHA:
        raise ValueError('Unexpected v41 receiver')
    if original[FLASH_OFFSET:FLASH_OFFSET+len(receiver)] != receiver:
        raise ValueError('Receiver differs from sector')
    if sha((base/'staged/recovery_gpio.c').read_bytes()) != GUARD_SHA or sha((base/'staged/recovery_gpio.h').read_bytes()) != GUARD_HEADER_SHA:
        raise ValueError('Recovery sources must be the exact qualified guard')
    if (rm.get('force_rx_proof_address') != '0x343f8940' or rm.get('force_rx_proof_words') != 32 or
            rm['coarse_lines'] != 1428 or rm['stop_dwell_cycles'] != 40000 or
            not rm['shutdown_data_off'] or rm['readiness_gate'] != 6):
        raise ValueError('Unexpected receiver configuration or diagnostic map')
    return original, prefix, receiver


def led_manifest():
    return {
        'schema': 1, 'active_low': True, 'pins': {'red': 'PG10', 'green': 'PG0', 'blue': 'PG8'},
        'proof_address': '0x343f89c0', 'proof_words': 32, 'proof_fields': PROOF_FIELDS,
        'red_start': 'first operation in stage1_main; ROM boot precedes application code',
        'red_snapshot': 'after raw10_memory_init; not a timestamp of initial LED assertion',
        'blue_start': 'first PA0 rising STROBE, after original event50',
        'blue_end': 'first DCMIPP frame callback, after original event30',
        'green_start': 'reserved helper; no current NAND write caller',
        'completion': 'all off; shallow WFI after event40, checksum, idle capture stop and sensor STOP',
        'failure': 'solid red; existing awake debug failure behavior retained',
        'sleep': 'CPU-only ordinary sleep; no deep sleep, regulator hold release or rail shutdown',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base, out = args.base.resolve(), args.output.resolve()
    rm, pm = (checked_manifest(base/name) for name in ('receiver', 'staged'))
    original, old_prefix, old_receiver = validate_base(base, rm, pm)
    out.mkdir(parents=True, exist_ok=False)
    rdir, pdir = out/'receiver', out/'staged'
    rdir.mkdir(); pdir.mkdir()
    generator_inputs = {str(p.relative_to(ROOT)): sha(p.read_bytes())
                        for p in (Path(__file__), HERE/'status_leds.h', HERE/'sleep.c')}
    sources = []
    for path in rm['sources']:
        source = ROOT/path
        target = rdir/source.name
        if source.name == 'capture.c':
            target.write_text(transform_capture(source.read_text()), encoding='utf-8', newline='\n')
        else:
            target.write_bytes(source.read_bytes())
        sources.append(target)
    for name in ('status_leds.h', 'sleep.c'):
        target = rdir/name
        target.write_bytes((HERE/name).read_bytes()); sources.append(target)
    flags = list(rm['compile_flags'])
    raw, size = compile_sources(rdir, [p for p in sources if p.suffix in ('.c', '.s', '.S')],
                                flags, rdir/'capture.ld', 'capture', libc=True)
    sp, entry = struct.unpack_from('<II', raw)
    vectors = struct.unpack_from('<198I', raw)
    if sp != 0x343B0000 or not all(v == 0 or (v & 1 and 0x34300000 <= v-1 < 0x34300000+len(raw)) for v in vectors[1:]):
        raise ValueError('Receiver vector validation failed')
    if len(raw) >= 65536-FLASH_OFFSET:
        raise ValueError('Receiver exceeds first sector')
    failure, sleep_idle = (symbol(rdir, n) for n in ('fast_failure_idle', 'status_led_sleep_idle'))
    if raw[failure-0x34300000:failure-0x34300000+2] != bytes.fromhex('fee7'):
        raise ValueError('Failure park changed')
    if raw[sleep_idle-0x34300000:sleep_idle-0x34300000+4] != bytes.fromhex('30bffde7'):
        raise ValueError('Completion sleep must remain WFI followed by branch back to WFI')
    manifest = copy.deepcopy(rm)
    manifest.update(hardware_status='untested', raw_bytes=len(raw), raw_sha256=sha(raw), size=size,
                    entry_point=hex(entry), compile_flags=flags, failure_park_address=hex(failure),
                    sleep_idle_address=hex(sleep_idle), status_leds=led_manifest(),
                    frozen_receiver_manifest_sha256=sha((base/'receiver/manifest.json').read_bytes()),
                    generator_inputs=generator_inputs)
    manifest['parameters']['first_frame_qualification'] = 'pending hardware qualification of this exact LED variant'
    write_manifest(rdir, manifest, sources)

    psources = []
    for path in pm['sources']:
        source = ROOT/path
        target = pdir/source.name
        if source.name == 'stage1.c':
            target.write_text(transform_prefix(source.read_text()), encoding='utf-8', newline='\n')
        else:
            target.write_bytes(source.read_bytes())
        psources.append(target)
    target = pdir/'status_leds.h'
    target.write_bytes((HERE/'status_leds.h').read_bytes()); psources.append(target)
    crc = zlib.crc32(raw) & 0xFFFFFFFF
    pflags = [f for f in pm['compile_flags'] if not f.startswith(('-DSTAGE2_BYTES=', '-DSTAGE2_EXPECTED_CRC32='))]
    pflags += [f'-DSTAGE2_BYTES={len(raw)}U', f'-DSTAGE2_EXPECTED_CRC32=0x{crc:08X}U']
    prefix, psize = compile_sources(pdir, [p for p in psources if p.suffix in ('.c', '.S')],
                                    pflags, pdir/'stage1.ld', 'stage1')
    park = symbol(pdir, 'recovery_gpio_park')
    if prefix[park-0x34180400:park-0x34180400+2] != bytes.fromhex('fee7'):
        raise ValueError('Recovery park is not the qualified branch-to-self instruction')
    for name in ('recovery_gpio.c', 'recovery_gpio.h', 'stage1_sensor.c', 'raw10_memory.c'):
        if (pdir/name).read_bytes() != (base/'staged'/name).read_bytes():
            raise ValueError(f'Unrelated prefix source changed: {name}')
    boot = make_image(prefix)
    if len(boot) > FLASH_OFFSET:
        raise ValueError('Prefix exceeds reserved NOR region')
    combined = bytearray(original)
    combined[:len(boot)] = boot
    combined[FLASH_OFFSET:FLASH_OFFSET+len(raw)] = raw
    if (combined[len(boot):FLASH_OFFSET] != original[len(boot):FLASH_OFFSET] or
            combined[FLASH_OFFSET+len(raw):] != original[FLASH_OFFSET+len(raw):]):
        raise ValueError('Changed NOR beyond prefix and receiver')
    (pdir/'stage1_boot.bin').write_bytes(boot)
    (pdir/'stage2.bin').write_bytes(raw)
    (pdir/'capture_sector_0.bin').write_bytes(combined)
    manifest = copy.deepcopy(pm)
    for name in ('recovery_code_and_literals_bytes_identical', 'prefix_first_bytes_identical_to_v36',
                 'prefix_same_size_as_v36', 'prefix_byte_differences_vs_v36'):
        manifest.pop(name, None)
    manifest.update(hardware_status='untested', stage1=inspect_image(boot), stage1_raw_bytes=len(prefix),
                    stage1_raw_sha256=sha(prefix), stage2_bytes=len(raw), stage2_crc32=f'0x{crc:08x}',
                    stage2_sha256=sha(raw), stage2_build_manifest=str(rdir/'manifest.json'),
                    stage2_manifest_sha256=sha((rdir/'manifest.json').read_bytes()), program_sha256=sha(combined),
                    size=psize, compile_flags=pflags, status_leds=led_manifest(),
                    frozen_program_sha256=BASE_SECTOR_SHA,
                    frozen_prefix_manifest_sha256=sha((base/'staged/manifest.json').read_bytes()),
                    guard_sources_byte_identical_to_v41=True, prefix_requires_new_exact_allowlist=True,
                    generator_inputs=generator_inputs)
    manifest['recovery_gpio'].update(park_address=hex(park), receiver_unchanged=False,
        clock_qualification='Source-identical v41 recovery guard; LED prefix requires hardware qualification')
    write_manifest(pdir, manifest, psources)
    print(json.dumps(dict(receiver=str(rdir), staged=str(pdir), receiver_bytes=len(raw),
        receiver_sha256=sha(raw), prefix_raw_bytes=len(prefix), prefix_boot_bytes=len(boot),
        prefix_raw_sha256=sha(prefix), program_sha256=sha(combined),
        recovery_park_address=hex(park), failure_park_address=hex(failure), sleep_idle_address=hex(sleep_idle),
        status='built offline; hardware untested')))


if __name__ == '__main__':
    main()
