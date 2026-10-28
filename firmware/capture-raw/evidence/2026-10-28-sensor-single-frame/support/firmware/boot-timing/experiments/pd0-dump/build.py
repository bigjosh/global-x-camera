"""Build the separate PD0 diagnostic fallback; local files only, no hardware.

The original 256-byte baseline is unchanged except for its post-marker branch.
TIM2 CNT/PSC are sampled before entering C only if its existing RCC enable bit
is set. This does not enable/reset/configure TIM2. If that access itself faults,
no serial dump follows; --skip-tim2 avoids the optional timer read.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BOOT = HERE.parents[1]
REPO = BOOT.parents[1]
sys.path.insert(0, str(BOOT))
from add_boot_header import make_image, inspect_image

BASE_HASH = '14d4c8ff2fc72c9df04dafa4a1a910a5f9fec39f09cc9e2d3e10e91105e34c44'
VENDOR_PIN = 'e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a'
ENTRY = r'''
.section .text.Post_Marker_Entry,"ax",%progbits
.global Post_Marker_Entry
.type Post_Marker_Entry,%function
.thumb_func
Post_Marker_Entry:
    ldr r3, =0x56028000
    ldr r0, [r3, #0x264]
    mov r1, #-1
    mov r2, #-1
#ifndef SKIP_TIM2
    tst r0, #1
    beq 1f
    ldr r3, =0x50000000
    ldr r1, [r3, #0x24]
    ldr r2, [r3, #0x28]
#endif
1:  mrs r3, CONTROL
    b.w fallback_dump
.size Post_Marker_Entry, .-Post_Marker_Entry
.ltorg
'''

def sha(data): return hashlib.sha256(data).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=REPO/'tmp/bringup/pd0-dump-20261017')
    p.add_argument('--skip-tim2', action='store_true')
    p.add_argument('--snapshot', type=Path)
    p.add_argument('--toolchain', type=Path, default=Path('D:/ST/STM32CubeIDE_1.15.1/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.12.3.rel1.win32_1.0.200.202406191623/tools/bin'))
    args = p.parse_args()
    vendor = REPO/'tmp/bringup/x-cube-n6-camera-capture'
    if subprocess.check_output(['git','-C',str(vendor),'rev-parse','HEAD'], text=True).strip() != VENDOR_PIN:
        p.error('Unexpected vendor revision')
    baseline = (BOOT/'build/first_gpio.bin').read_bytes()
    if sha(baseline) != BASE_HASH: p.error('Original baseline changed')
    source = (BOOT/'first_gpio.S').read_text()
    old = 'boot_idle:\n    wfi\n    b boot_idle\n'
    if source.count(old) != 1: p.error('Original idle loop changed')
    asm = source.replace(old, 'boot_idle:\n    b.w Post_Marker_Entry\n    nop\n') + ENTRY
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out/'first_gpio_dump.S').write_text(asm)
    tc = args.toolchain
    cmsis = vendor/'STM32Cube_FW_N6/Drivers/CMSIS'
    flags = ['-mcpu=cortex-m55','-mthumb','-mcmse','-mfloat-abi=soft','-Os',
             '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-unwind-tables',
             '-fno-asynchronous-unwind-tables','-fstack-usage','-g3','-Wa,--noexecstack',
             '-Wall','-Wextra','-Werror','-DSTM32N657xx',
             f'-I{BOOT}', f'-I{cmsis/"Device/ST/STM32N6xx/Include"}', f'-I{cmsis/"Include"}']
    if args.skip_tim2: flags.append('-DSKIP_TIM2')
    gcc = str(tc/'arm-none-eabi-gcc.exe')
    for src, name in ((out/'first_gpio_dump.S','entry.o'), (HERE/'dump.c','dump.o')):
        subprocess.run([gcc,*flags,'-c',str(src),'-o',str(out/name)],check=True)
    elf=out/'first_gpio_dump.elf'
    subprocess.run([gcc,*flags,'-nostdlib','-nostartfiles','-Wl,--build-id=none',
                    '-Wl,--fatal-warnings',f'-Wl,-Map,{out/"first_gpio_dump.map"}',
                    '-T',str(BOOT/'first_gpio.ld'),str(out/'entry.o'),str(out/'dump.o'),
                    '-o',str(elf)],check=True)
    subprocess.run([str(tc/'arm-none-eabi-objcopy.exe'),'-O','binary',str(elf),str(out/'first_gpio_dump.bin')],check=True)
    payload=(out/'first_gpio_dump.bin').read_bytes()
    if payload[:0xD4] != baseline[:0xD4] or payload[0xDA:0x100] != baseline[0xDA:0x100]:
        p.error('Original pre-marker code/data changed')
    image=make_image(payload)
    if len(image)>65536: p.error('Image exceeds sector 0')
    (out/'first_gpio_dump_boot.bin').write_bytes(image)
    (out/'first_gpio_dump.lst').write_bytes(subprocess.check_output([str(tc/'arm-none-eabi-objdump.exe'),'-d',str(elf)]))
    m={**inspect_image(image),'raw_payload_bytes':len(payload),'raw_payload_sha256':sha(payload),
       'dump_source_sha256':sha((HERE/'dump.c').read_bytes()),'assembly_sha256':sha(asm.encode()),
       'tim2_read_if_clock_enabled':not args.skip_tim2,'no_hardware_access':True,
       'original_ranges_identical':['0x000..0x0d3','0x0da..0x0ff'],
       'trace_buffers':{'0x341037f0':2048,'0x241077f0':2048},'status':'UNTESTED HARDWARE'}
    if args.snapshot:
        saved=args.snapshot.read_bytes()
        if len(saved)!=65536 or saved[:1280]!=make_image(baseline): p.error('Wrong snapshot size/prefix')
        program=image+saved[len(image):]
        (out/'first_gpio_dump_sector_0.bin').write_bytes(program)
        (out/'restore_original_sector_0.bin').write_bytes(saved)
        assert (out/'first_gpio_dump_sector_0.bin').read_bytes()[len(image):]==saved[len(image):]
        m.update(program_sha256=sha(program),snapshot_sha256=sha(saved))
    (out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
    print(json.dumps(m,indent=2))

if __name__=='__main__': main()
