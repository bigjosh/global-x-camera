"""Build an experimental post-marker debug baseline and inert size variants.

Purely local build; never connects to hardware. Original baseline source and
binaries are unchanged. Replace its six-byte idle loop with an equal-size
branch/nop and append a stub after the original literal pool and fault handler.
Binary comparisons enforce identical bytes through both measured marker edges.

The stub enables volatile debug ONLY AFTER both markers, using ST's documented
BSEC_DBGCR/AP_UNLOCK values. It writes no OTP, lifecycle or flash register.
ST notes these settings persist until power cycle, potentially across NRST.
https://wiki.st.com/stm32mcu/wiki/Security:Security_features_on_STM32N6_MCUs

Revision 2 explicitly enables the RCC debug clocks, DBGMCU DBGCLKEN and
DBG_SLEEP after the markers and stays awake. Revision 1's WFI without these
settings may prevent later HOTPLUG access; this is a diagnostic mitigation,
not proof of the observed failure's cause. Awake idle is not a power baseline.

RAM status at 0x34182000: BSEC_DBGCR, AP_UNLOCK, RCC_RDCR, magic 0x44424732,
DBGMCU_CR, RCC_MISCENR, RCC_MISCLPENR.
RDCR is only read, never changed. This record lies in inert padding in the
larger variants. The cache line is cleaned so a later debugger sees the record.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

BOOT = Path(__file__).resolve().parents[2]
REPO = BOOT.parents[1]
sys.path.insert(0, str(BOOT))
from add_boot_header import make_image, inspect_image

PIN = 'e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a'
PAYLOAD_HASH = '14d4c8ff2fc72c9df04dafa4a1a910a5f9fec39f09cc9e2d3e10e91105e34c44'
STUB = r'''
/* EXPERIMENT ONLY: secure debug enable after the original two marker edges.
 * ST's documented debug-control writes; no OTP or lifecycle programming. */
.section .text.Debug_After_Markers,"ax",%progbits
.global Debug_After_Markers
.type Debug_After_Markers,%function
.thumb_func
Debug_After_Markers:
    ldr r0, =BT_RCC_BASE
    movs r1, #2
    str r1, [r0, #0xA78]  /* RCC_APB4ENSR2.BSECENS */
    ldr r1, [r0, #0x278]
    dsb sy
    ldr r0, =0x56009000
    ldr r1, =0xB451B400
    str r1, [r0, #0xE8C]  /* BSEC_DBGCR */
    movs r1, #0xB4
    str r1, [r0, #0xE90]  /* BSEC_AP_UNLOCK */
    dsb sy
    isb sy

    ldr r0, =BT_RCC_BASE
    movs r1, #1
    str r1, [r0, #0xA48]  /* RCC_MISCENSR.DBGENS */
    str r1, [r0, #0xA88]  /* RCC_MISCLPENSR.DBGLPENS */
    ldr r1, [r0, #0x248]
    dsb sy
    ldr r0, =0x54001000
    ldr r1, [r0, #4]
    orr r1, r1, #0x00100000  /* DBGMCU_CR.DBGCLKEN */
    orr r1, r1, #1           /* DBGMCU_CR.DBG_SLEEP */
    str r1, [r0, #4]
    dsb sy
    isb sy

    ldr r2, =0x34182000
    ldr r1, [r0, #4]
    str r1, [r2, #16]
    ldr r0, =0x56009000
    ldr r1, [r0, #0xE8C]
    str r1, [r2, #0]
    ldr r1, [r0, #0xE90]
    str r1, [r2, #4]
    ldr r0, =BT_RCC_BASE
    ldr r1, [r0, #0x44C]  /* RCC_RDCR: read only */
    str r1, [r2, #8]
    ldr r1, [r0, #0x248]
    str r1, [r2, #20]
    ldr r1, [r0, #0x288]
    str r1, [r2, #24]
    ldr r1, =0x44424732
    str r1, [r2, #12]
    dsb sy
    ldr r0, =0xE000EF68   /* SCB_DCCMVAC: clean status cache line */
    str r2, [r0]
    dsb sy
    isb sy
.global debug_ready
debug_ready:
    nop                    /* Stay awake so HOTPLUG need not wake the core. */
    b debug_ready
.size Debug_After_Markers, .-Debug_After_Markers
.ltorg
'''
CHECKS = r'''
#include <stddef.h>
#include "stm32n657xx.h"
_Static_assert(BSEC_BASE_S == 0x56009000, "BSEC base");
_Static_assert(offsetof(BSEC_TypeDef, DBGCR) == 0xE8C, "DBGCR offset");
_Static_assert(offsetof(BSEC_TypeDef, AP_UNLOCK) == 0xE90, "AP_UNLOCK offset");
_Static_assert(offsetof(RCC_TypeDef, APB4ENSR2) == 0xA78, "BSEC clock set offset");
_Static_assert(offsetof(RCC_TypeDef, APB4ENR2) == 0x278, "BSEC clock readback offset");
_Static_assert(RCC_APB4ENSR2_BSECENS == 2, "BSEC clock bit");
_Static_assert(offsetof(RCC_TypeDef, RDCR) == 0x44C, "RDCR offset");
_Static_assert(DBGMCU_BASE_S == 0x54001000, "DBGMCU base");
_Static_assert(offsetof(DBGMCU_TypeDef, CR) == 4, "DBGMCU CR offset");
_Static_assert(DBGMCU_CR_DBG_SLEEP == 1, "Debug sleep bit");
_Static_assert(DBGMCU_CR_DBGCLKEN == 0x00100000, "Debug clock bit");
_Static_assert(offsetof(RCC_TypeDef, MISCENSR) == 0xA48, "DBG clock set offset");
_Static_assert(offsetof(RCC_TypeDef, MISCENR) == 0x248, "DBG clock read offset");
_Static_assert(offsetof(RCC_TypeDef, MISCLPENSR) == 0xA88, "DBG sleep clock set offset");
_Static_assert(offsetof(RCC_TypeDef, MISCLPENR) == 0x288, "DBG sleep clock read offset");
_Static_assert(RCC_MISCENSR_DBGENS == 1, "DBG clock bit");
_Static_assert(RCC_MISCLPENSR_DBGLPENS == 1, "DBG sleep clock bit");
_Static_assert(SCB_BASE + offsetof(SCB_Type, DCCMVAC) == 0xE000EF68, "Cache clean address");
'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


def prepare_sector_buffers(output, snapshot_path):
    snapshot = snapshot_path.read_bytes()
    baseline = (BOOT / 'build/first_gpio.bin').read_bytes()
    if sha(baseline) != PAYLOAD_HASH or len(snapshot) != 65536:
        raise ValueError('Expected known baseline payload and exact 64 KiB current snapshot')
    original_image = make_image(baseline)
    if snapshot[:len(original_image)] != original_image:
        raise ValueError('Snapshot does not begin with the measured original boot image')
    manifest_path = output / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    for variant in manifest['variants']:
        image = (output / variant['boot_file']).read_bytes()
        inspect_image(image)
        if sha(image) != variant['sha256'] or len(image) > len(snapshot):
            raise ValueError('Variant differs from manifest or exceeds saved sector')
        program = image + snapshot[len(image):]
        name = variant['boot_file'].replace('_boot.bin', '_sector_0.bin')
        path = output / name
        if path.exists() and path.read_bytes() != program:
            raise ValueError(f'Refusing to replace different programming buffer {path}')
        path.write_bytes(program)
        if path.read_bytes() != program:
            raise ValueError('Sector buffer readback failed')
        variant.update({'program_file': name, 'program_bytes': len(program),
                        'program_sha256': sha(program)})
    restore = output / 'restore_original_sector_0.bin'
    if restore.exists() and restore.read_bytes() != snapshot:
        raise ValueError('Refusing to replace different restoration file')
    restore.write_bytes(snapshot)
    if restore.read_bytes() != snapshot:
        raise ValueError('Restoration-file readback failed')
    manifest.update({'snapshot_path': str(snapshot_path.resolve()),
                     'snapshot_sha256': sha(snapshot),
                     'restoration_file': restore.name,
                     'programming_buffers_preserve_bytes_after_each_image': True})
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


def build(output, toolchain):
    vendor = REPO / 'tmp/bringup/x-cube-n6-camera-capture'
    head = subprocess.check_output(['git', '-C', str(vendor), 'rev-parse', 'HEAD'], text=True).strip()
    if head != PIN:
        raise ValueError('Unexpected pinned vendor checkout')
    baseline = (BOOT / 'build/first_gpio.bin').read_bytes()
    if sha(baseline) != PAYLOAD_HASH:
        raise ValueError('Measured baseline payload changed')
    source = (BOOT / 'first_gpio.S').read_text(encoding='utf-8')
    old = 'boot_idle:\n    wfi\n    b boot_idle\n'
    if source.count(old) != 1:
        raise ValueError('Expected unique original idle loop')
    generated = source.replace(old, 'boot_idle:\n    b.w Debug_After_Markers\n    nop\n') + STUB
    output.mkdir(parents=True, exist_ok=False)
    asm = output / 'first_gpio_debug.S'
    asm.write_text(generated, encoding='utf-8')
    checks = output / 'debug_address_check.c'
    checks.write_text(CHECKS, encoding='utf-8')
    gcc = toolchain / 'arm-none-eabi-gcc.exe'
    cmsis = vendor / 'STM32Cube_FW_N6/Drivers/CMSIS'
    flags = ['-mcpu=cortex-m55', '-mthumb', '-mcmse', '-mfloat-abi=soft']
    def run(args):
        subprocess.run([str(arg) for arg in args], check=True)
    for check in (BOOT / 'address_check.c', checks):
        run([gcc, *flags, '-std=c11', '-fsyntax-only', '-Wall', '-Wextra', '-Werror',
             '-DSTM32N657xx', f'-I{cmsis / "Device/ST/STM32N6xx/Include"}',
             f'-I{cmsis / "Include"}', f'-I{BOOT}', check])
    elf = output / 'first_gpio_debug.elf'
    binary = output / 'first_gpio_debug.bin'
    run([gcc, *flags, '-g3', '-nostdlib', '-nostartfiles', '-Wl,--build-id=none',
         '-Wl,--fatal-warnings', f'-Wl,-Map,{output / "first_gpio_debug.map"}',
         f'-I{BOOT}', '-T', BOOT / 'first_gpio.ld', asm, '-o', elf])
    run([toolchain / 'arm-none-eabi-objcopy.exe', '-O', 'binary', elf, binary])
    for program, arguments, filename in (
            ('arm-none-eabi-objdump.exe', ['-d'], 'first_gpio_debug.lst'),
            ('arm-none-eabi-nm.exe', ['--numeric-sort'], 'first_gpio_debug.symbols.txt')):
        result = subprocess.check_output([str(toolchain / program), *arguments, str(elf)])
        (output / filename).write_bytes(result)
    payload = binary.read_bytes()
    if payload[:0xD4] != baseline[:0xD4] or payload[0xDA:0x100] != baseline[0xDA:0x100]:
        raise ValueError('Generated code moved or changed original pre-marker instructions/data')
    manifest = {'experiment': 'post-marker-debug size comparison',
                'revision': 2, 'post_marker_idle': 'awake busy loop',
                'no_hardware_access': True, 'original_payload_sha256': PAYLOAD_HASH,
                'original_source_sha256': sha(source.encode('utf-8')),
                'generated_source_sha256': sha(generated.encode('utf-8')),
                'debug_payload_bytes': len(payload), 'debug_payload_sha256': sha(payload),
                'unchanged_baseline_ranges': ['0x000..0x0d3', '0x0da..0x0ff'],
                'changed_baseline_range': '0x0d4..0x0d9 (post-marker idle loop only)',
                'status_address': '0x34182000',
                'status_words': ['BSEC_DBGCR', 'AP_UNLOCK', 'RDCR (read only)',
                                 'magic 0x44424732', 'DBGMCU_CR',
                                 'RCC_MISCENR', 'RCC_MISCLPENR'],
                'variants': [],
                'notes': ['Experimental debug authorization persists until power cycle; no OTP writes.',
                          'Use HOTPLUG after markers; reset-mode connection can restart the ROM.',
                          'Compare all size variants against this matched debug baseline.',
                          'No debugger should be connected during the measured autonomous boot.',
                          'Post-marker debug clocks and awake idle are unsuitable for power comparison.',
                          'Back up/read-verify sector 0 and restore its exact saved bytes afterward.']}
    for padding in (0, 8192, 32768):
        padded = payload + bytes([0xA5]) * padding
        image = make_image(padded)
        if len(image) > 65536:
            raise ValueError('Experiment escaped first erase sector')
        name = f'first_gpio_debug_plus_{padding}_boot.bin'
        path = output / name
        path.write_bytes(image)
        metadata = inspect_image(path.read_bytes())
        manifest['variants'].append({**metadata, 'padding_bytes': padding, 'boot_file': name})
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=REPO / 'tmp/bringup/debug-awake-payload-size-20261017')
    parser.add_argument('--toolchain', type=Path, default=Path('D:/ST/STM32CubeIDE_1.15.1/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.12.3.rel1.win32_1.0.200.202406191623/tools/bin'))
    parser.add_argument('--snapshot', type=Path, help='Verified current 64 KiB sector, beginning with original baseline')
    parser.add_argument('--prepare-sectors-only', action='store_true', help='Use already-built output and --snapshot without rebuilding')
    args = parser.parse_args()
    if args.prepare_sectors_only and not args.snapshot:
        parser.error('--prepare-sectors-only requires --snapshot')
    try:
        if not args.prepare_sectors_only:
            result = build(args.output.resolve(), args.toolchain)
        if args.snapshot:
            result = prepare_sector_buffers(args.output.resolve(), args.snapshot)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'Error: {exc}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
