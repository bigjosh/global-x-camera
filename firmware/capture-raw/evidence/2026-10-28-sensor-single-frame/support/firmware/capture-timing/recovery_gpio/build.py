"""Offline PE1 recovery-prefix candidate around the exact frozen v25 receiver.

No instrument, debugger, power control, or NOR write is performed by this tool.
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
                        make_image, inspect_image, replace, sha, write_manifest)

BASE_SHA256 = 'c43721b29f437546d3090632495f4527f4ba34d4af773a23214cdd86a0adb817'
STATUS_FIELDS = ('magic schema words state reason pin nominal_hz settle_cycles '
                 'begin_cycle sample_cycle elapsed_cycles polls idr moder pupdr '
                 'ahb4enr demcr dwt_ctrl control ipsr primask dbgcr ap_unlock reserved').split()


def transform_stage1(text):
    """Three ordered hooks; otherwise retain the exact frozen prefix source."""
    if 'recovery_gpio_' in text:
        raise ValueError('Recovery guard must not be inserted twice')
    text = replace(text, '#include "stm32n657xx.h"',
                   '#include "stm32n657xx.h"\n#include "recovery_gpio.h"')
    text = replace(text, '__attribute__((noreturn)) void stage1_main(void)\n{',
                   '__attribute__((noreturn)) void stage1_main(void)\n{\n    recovery_gpio_begin();')
    text = replace(text, '    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;',
                   '    recovery_gpio_check();\n    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;')
    text = replace(text, '    raw10_memory_init();',
                   '    raw10_memory_init();\n    recovery_gpio_publish();')
    if not (text.index('    recovery_gpio_begin();') < text.index('    BSEC->DBGCR') <
            text.index('    recovery_gpio_check();') < text.index('    raw10_memory_init();') <
            text.index('    recovery_gpio_publish();') < text.index('int sensor_result =')):
        raise ValueError('Recovery hooks must precede memory/sensor/NOR setup')
    return text


def find_symbol(symbols, name):
    match = re.search(r'^([0-9a-fA-F]+) [Tt] ' + re.escape(name) + r'$', symbols, re.M)
    if not match:
        raise ValueError(f'Missing required executable symbol {name}')
    return int(match.group(1), 16)


def validate_base(original, receiver, pm, rm):
    if len(original)!=65536 or sha(original)!=BASE_SHA256 or pm['program_sha256']!=BASE_SHA256:
        raise ValueError('Only the exact known v25 sector is supported')
    if sha(receiver)!=rm['raw_sha256'] or sha(receiver)!=pm['stage2_sha256']:
        raise ValueError('Frozen receiver hash mismatch')
    if original[FLASH_OFFSET:FLASH_OFFSET+len(receiver)]!=receiver:
        raise ValueError('Receiver differs from the exact installed image')


def compose_sector(original, boot):
    if len(original)!=65536 or len(boot)>FLASH_OFFSET:
        raise ValueError('Prefix exceeds reserved NOR space or sector size is wrong')
    combined=bytearray(original)
    combined[:len(boot)]=boot
    if combined[len(boot):]!=original[len(boot):]:
        raise ValueError('Only bytes occupied by the new prefix may change')
    return bytes(combined)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base, out = args.base.resolve(), args.output.resolve()
    rm, pm = (checked_manifest(base/name) for name in ('receiver', 'staged'))
    original = (base/'staged/capture_sector_0.bin').read_bytes()
    receiver = (base/'receiver/capture.bin').read_bytes()
    validate_base(original, receiver, pm, rm)
    out.mkdir(parents=True, exist_ok=False)
    rdir, pdir = out/'receiver', out/'staged'
    shutil.copytree(base/'receiver', rdir)  # Byte-identical receiver, no recompile.
    pdir.mkdir()
    sources=[]
    for path in pm['sources']:
        source=ROOT/path
        target=pdir/source.name
        if source.name=='stage1.c':
            target.write_text(transform_stage1(source.read_text()), encoding='utf-8', newline='\n')
        else:
            target.write_bytes(source.read_bytes())
        sources.append(target)
    for name in ('recovery_gpio.c', 'recovery_gpio.h'):
        target=pdir/name
        target.write_bytes((HERE/name).read_bytes())
        sources.append(target)
    flags=list(pm['compile_flags'])+[f'-I{pdir}']
    raw, size=compile_sources(pdir,[p for p in sources if p.suffix in ('.c','.S')],
                             flags,pdir/'stage1.ld','stage1')
    park=find_symbol((pdir/'symbols.txt').read_text(),'recovery_gpio_park')
    park_offset=park-0x34180400
    if park&1 or raw[park_offset:park_offset+2]!=bytes.fromhex('fee7'):
        raise ValueError('Recovery park must be the exact named branch-to-self instruction')
    boot=make_image(raw)
    combined=compose_sector(original,boot)
    (pdir/'stage1_boot.bin').write_bytes(boot)
    (pdir/'stage2.bin').write_bytes(receiver)
    (pdir/'capture_sector_0.bin').write_bytes(combined)
    manifest=copy.deepcopy(pm)
    manifest.update(hardware_status='untested',stage1=inspect_image(boot),
                    stage1_raw_bytes=len(raw),stage1_raw_sha256=sha(raw),
                    stage2_build_manifest=str(rdir/'manifest.json'),
                    stage2_manifest_sha256=sha((rdir/'manifest.json').read_bytes()),
                    program_sha256=sha(combined),size=size,compile_flags=flags,
                    recovery_gpio={
                        'schema':1,'pin':'PE1','header':'CN15.24','active_low':True,
                        'internal_pull':'up','status_address':'0x341f7000',
                        'published_status_address':'0x343f7000','status_words':len(STATUS_FIELDS),
                        'status_fields':STATUS_FIELDS,'settle_cycles':40000,
                        'nominal_clock_hz':400000000,'max_polls':100000,
                        'park_symbol':'recovery_gpio_park','park_address':hex(park),'park_bytes':'fee7',
                        'clock_qualification':'100 nominal us; hardware qualification pending',
                        'external_drive':'open-drain sink only; hardware connection pending',
                        'receiver_unchanged':True},
                    frozen_prefix_manifest_sha256=sha((base/'staged/manifest.json').read_bytes()),
                    frozen_program_sha256=BASE_SHA256,
                    generator_inputs={str(p.relative_to(ROOT)):sha(p.read_bytes())
                                      for p in (Path(__file__),HERE/'recovery_gpio.c',HERE/'recovery_gpio.h')})
    write_manifest(pdir,manifest,sources)
    print(json.dumps(dict(staged=str(pdir),receiver=str(rdir),
                         prefix_raw_bytes=len(raw),prefix_boot_bytes=len(boot),
                         prefix_raw_sha256=sha(raw),program_sha256=sha(combined),
                         recovery_park_address=hex(park),status='built; untested')))


if __name__=='__main__':
    main()
