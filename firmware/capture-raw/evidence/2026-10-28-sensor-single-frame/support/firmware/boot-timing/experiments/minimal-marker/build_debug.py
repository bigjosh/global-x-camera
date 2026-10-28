"""Build the 196-byte marker variant with the exact revision 2 awake debug hook.

Local build only; no hardware. The original tiny source, original baseline and
revision 2 files remain unchanged. Verifies the appended hook byte-for-byte
against the already-built revision 2 payload, then prepares a complete NOR
sector preserving the saved tail and an exact restore file.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BOOT = HERE.parents[1]
REPO = BOOT.parents[1]
sys.path.insert(0, str(BOOT))
from add_boot_header import make_image, inspect_image

SPEC = importlib.util.spec_from_file_location('awake_builder', HERE.parent/'payload-size/build_debug.py')
awake = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(awake)

TINY_HASH = 'c053b3e12c3478d6a054fd427f5d14e1c85613c6a1a08f0bdc622397c8373aee'
AWAKE_HASH = '942a4dcf7ab99cad9c2556d9c41cefebfd1eae87cb3a8d216029cc8651785507'


def sha(data): return hashlib.sha256(data).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=REPO/'tmp/bringup/tiny-debug-awake-20261017')
    p.add_argument('--snapshot',type=Path,required=True)
    p.add_argument('--awake-reference',type=Path,default=REPO/'tmp/bringup/debug-awake-payload-size-20261017/first_gpio_debug.bin')
    p.add_argument('--toolchain',type=Path,default=Path('D:/ST/STM32CubeIDE_1.15.1/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.12.3.rel1.win32_1.0.200.202406191623/tools/bin'))
    a=p.parse_args()
    vendor=REPO/'tmp/bringup/x-cube-n6-camera-capture'
    if subprocess.check_output(['git','-C',str(vendor),'rev-parse','HEAD'],text=True).strip()!=awake.PIN:
        p.error('Unexpected vendor checkout')
    reference=a.awake_reference.read_bytes()
    original=(BOOT/'build/first_gpio.bin').read_bytes()
    saved=a.snapshot.read_bytes()
    if sha(reference)!=AWAKE_HASH or sha(original)!=awake.PAYLOAD_HASH:
        p.error('Expected pinned revision 2 and original payload bytes')
    if len(saved)!=65536 or saved[:1280]!=make_image(original):
        p.error('Expected exact first sector beginning with the original baseline')
    source=(HERE/'first_gpio_tiny.S').read_text()
    old='boot_idle:\n    wfi\n    b boot_idle\n'
    if source.count(old)!=1: p.error('Unexpected tiny idle loop')
    generated=source.replace(old,'boot_idle:\n    b.w Debug_After_Markers\n    nop\n')+awake.STUB
    out=a.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    (out/'first_gpio_tiny_debug.S').write_text(generated)
    (out/'debug_address_check.c').write_text(awake.CHECKS)
    tc=a.toolchain
    gcc=str(tc/'arm-none-eabi-gcc.exe')
    flags=['-mcpu=cortex-m55','-mthumb','-mcmse','-mfloat-abi=soft']
    cmsis=vendor/'STM32Cube_FW_N6/Drivers/CMSIS'
    for check in (BOOT/'address_check.c',out/'debug_address_check.c'):
        subprocess.run([gcc,*flags,'-std=c11','-fsyntax-only','-Wall','-Wextra','-Werror',
                        '-DSTM32N657xx',f'-I{cmsis/"Device/ST/STM32N6xx/Include"}',
                        f'-I{cmsis/"Include"}',str(check)],check=True)
    def build(src,stem):
        elf=out/f'{stem}.elf'
        subprocess.run([gcc,*flags,'-g3','-nostdlib','-nostartfiles','-Wl,--build-id=none',
                        '-Wl,--fatal-warnings',f'-Wl,-Map,{out/(stem+".map")}',
                        f'-I{BOOT}','-T',str(BOOT/'first_gpio.ld'),str(src),'-o',str(elf)],check=True)
        binary=out/f'{stem}.bin'
        subprocess.run([str(tc/'arm-none-eabi-objcopy.exe'),'-O','binary',str(elf),str(binary)],check=True)
        symbols=subprocess.check_output([str(tc/'arm-none-eabi-nm.exe'),'--numeric-sort',str(elf)],text=True)
        (out/f'{stem}.symbols.txt').write_text(symbols)
        (out/f'{stem}.lst').write_bytes(subprocess.check_output([str(tc/'arm-none-eabi-objdump.exe'),'-d',str(elf)]))
        mapping={row.split()[2]:int(row.split()[0],16) for row in symbols.splitlines() if len(row.split())==3}
        return binary.read_bytes(),mapping
    tiny,tiny_symbols=build(HERE/'first_gpio_tiny.S','tiny_reference')
    if len(tiny)!=196 or sha(tiny)!=TINY_HASH: p.error('Tiny source no longer builds the known 196-byte payload')
    payload,symbols=build(out/'first_gpio_tiny_debug.S','first_gpio_tiny_debug')
    idle=tiny_symbols['boot_idle']-0x34180400
    if payload[:idle]!=tiny[:idle] or payload[idle+6:196]!=tiny[idle+6:]:
        p.error('Tiny marker path/data changed beyond the post-marker branch')
    if payload[196:]!=reference[256:]:
        p.error('Appended post-marker hook differs from revision 2 bytes')
    image=make_image(payload)
    if len(image)>65536: p.error('Image exceeds sector 0')
    program=image+saved[len(image):]
    (out/'first_gpio_tiny_debug_boot.bin').write_bytes(image)
    (out/'first_gpio_tiny_debug_sector_0.bin').write_bytes(program)
    (out/'restore_original_sector_0.bin').write_bytes(saved)
    assert (out/'first_gpio_tiny_debug_sector_0.bin').read_bytes()==program
    assert program[len(image):]==saved[len(image):]
    assert (out/'restore_original_sector_0.bin').read_bytes()==saved
    m={**inspect_image(image),'experiment':'tiny markers plus identical revision 2 awake hook',
       'no_hardware_access':True,'hardware_status':'untested',
       'tiny_reference_bytes':196,'tiny_reference_sha256':TINY_HASH,
       'awake_reference_sha256':AWAKE_HASH,'raw_payload_bytes':len(payload),
       'raw_payload_sha256':sha(payload),'post_marker_hook_bytes':len(payload)-196,
       'post_marker_hook_sha256':sha(payload[196:]),'post_marker_hook_matches_revision_2':True,
       'changed_tiny_range':f'0x{idle:03x}..0x{idle+5:03x}',
       'pd0_store':f"0x{symbols['pd0_first_edge_store']:08x}",
       'pe0_store':f"0x{symbols['pe0_second_edge_store']:08x}",
       'debug_ready':f"0x{symbols['debug_ready']:08x}",
       'status_address':'0x34182000','status_magic':'0x44424732',
       'program_file':'first_gpio_tiny_debug_sector_0.bin','program_bytes':len(program),
       'program_sha256':sha(program),'snapshot_sha256':sha(saved),
       'snapshot_path':str(a.snapshot.resolve()),
       'restoration_file':'restore_original_sector_0.bin',
       'notes':['Pre-marker instruction changes are intentional; GPIO type/speed/pull rely on reset defaults.',
                'The entire post-marker hook matches revision 2, including debug clocks and awake loop.',
                'Raw payload is 60 bytes smaller; wrapped image is 64 bytes smaller than revision 2.',
                'Compare with matched revision 2, then restore the complete original saved sector.']}
    (out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
    print(json.dumps(m,indent=2))


if __name__=='__main__': main()
