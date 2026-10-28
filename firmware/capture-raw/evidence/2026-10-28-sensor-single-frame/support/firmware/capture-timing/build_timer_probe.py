"""Build an isolated native-v25 TIM5 input-capture diagnostic; no hardware."""
import argparse
import copy
import json
from pathlib import Path
import struct
import zlib
from build_raw10 import (ROOT, HERE, FLASH_OFFSET, checked_manifest, compile_sources,
                        make_image, inspect_image, replace, sha, write_manifest)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',type=Path,required=True)
    p.add_argument('--snapshot',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    base,out=a.base.resolve(),a.output.resolve()
    rm,pm=(checked_manifest(base/name) for name in ('receiver','staged'))
    assert rm['parameters']['raw10_relocated'] and pm['trim_sensor']
    assert rm['raw_sha256']==pm['stage2_sha256']
    assert sha((base/'receiver/capture.bin').read_bytes())==rm['raw_sha256']
    saved=a.snapshot.read_bytes()
    assert len(saved)==65536 and sha(saved)==pm['snapshot_sha256']
    out.mkdir(parents=True,exist_ok=False)
    rdir,pdir=out/'receiver',out/'staged'
    rdir.mkdir();pdir.mkdir()
    sources=[]
    for path in rm['sources']:
        source=ROOT/path
        target=rdir/source.name
        if source.name=='capture.c':
            text=source.read_text()
            text=replace(text,'void EXTI0_IRQHandler(void)',
                         'extern int timer_probe_init(void);\n'
                         'extern void timer_probe_record(uint32_t,uint32_t);\n'
                         'extern void timer_probe_finish(void);\n'
                         'void EXTI0_IRQHandler(void)')
            for edge,event in (('Rising',50),('Falling',51)):
                text=replace(text,
                    f'void HAL_GPIO_EXTI_{edge}_Callback(uint16_t pin) {{ if(pin==GPIO_PIN_0) event({event}); }}',
                    f'void HAL_GPIO_EXTI_{edge}_Callback(uint16_t pin) {{ if(pin==GPIO_PIN_0) {{ '
                    f'uint32_t before=TIM5->CNT; event({event}); timer_probe_record({event},before); }} }}')
            text=replace(text,'  HAL_NVIC_SetPriority(EXTI0_IRQn,3,0); HAL_NVIC_EnableIRQ(EXTI0_IRQn);',
                         '  check(0x90,timer_probe_init());\n'
                         '  HAL_NVIC_SetPriority(EXTI0_IRQn,3,0); HAL_NVIC_EnableIRQ(EXTI0_IRQn);')
            text=replace(text,'  event(40);','  timer_probe_finish();\n  event(40);')
            target.write_text(text,encoding='utf-8',newline='\n')
        else:target.write_bytes(source.read_bytes())
        sources.append(target)
    timer=rdir/'timer_probe.c'
    timer.write_bytes((HERE/'timer_probe.c').read_bytes());sources.append(timer)
    flags=rm['compile_flags']
    raw,size=compile_sources(rdir,[s for s in sources if s.suffix!='.ld'],flags,
                             rdir/'capture.ld','capture',libc=True)
    sp,entry=struct.unpack_from('<II',raw)
    vectors=struct.unpack_from('<198I',raw)
    assert sp==0x343B0000
    assert all(v==0 or (v&1 and 0x34300000<=v-1<0x34300000+len(raw)) for v in vectors[1:])
    assert len(raw)<65536-FLASH_OFFSET
    manifest=copy.deepcopy(rm)
    manifest.update(hardware_status='untested',raw_bytes=len(raw),raw_sha256=sha(raw),
                    size=size,entry_point=hex(entry),compile_flags=flags,
                    timer_status_address='0x343f7000',timer_status_words=224,
                    timer_header_words=32,timer_record_words=12,timer_max_records=16,
                    timer_nominal_hz=300000000,timer_instance='TIM5',timer_gpio_af=2,
                    frozen_receiver_manifest_sha256=sha((base/'receiver/manifest.json').read_bytes()),
                    generator_sha256=sha(Path(__file__).read_bytes()))
    manifest['parameters']['timer_probe']=True
    write_manifest(rdir,manifest,sources)
    psources=[]
    for path in pm['sources']:
        source=ROOT/path;target=pdir/source.name
        target.write_bytes(source.read_bytes());psources.append(target)
    crc=zlib.crc32(raw)&0xFFFFFFFF
    pflags=[f for f in pm['compile_flags']
            if not f.startswith(('-DSTAGE2_BYTES=','-DSTAGE2_EXPECTED_CRC32='))]
    pflags += [f'-DSTAGE2_BYTES={len(raw)}U',f'-DSTAGE2_EXPECTED_CRC32=0x{crc:08X}U']
    prefix,size=compile_sources(pdir,[s for s in psources if s.suffix!='.ld'],pflags,
                                pdir/'stage1.ld','stage1')
    boot=make_image(prefix)
    assert len(boot)<=FLASH_OFFSET
    (pdir/'stage1_boot.bin').write_bytes(boot);(pdir/'stage2.bin').write_bytes(raw)
    combined=bytearray(saved)
    combined[:len(boot)]=boot;combined[FLASH_OFFSET:FLASH_OFFSET+len(raw)]=raw
    assert combined[len(boot):FLASH_OFFSET]==saved[len(boot):FLASH_OFFSET]
    assert combined[FLASH_OFFSET+len(raw):]==saved[FLASH_OFFSET+len(raw):]
    (pdir/'capture_sector_0.bin').write_bytes(combined)
    manifest=copy.deepcopy(pm)
    manifest.update(hardware_status='untested',stage1=inspect_image(boot),
                    stage1_raw_bytes=len(prefix),stage1_raw_sha256=sha(prefix),
                    stage2_bytes=len(raw),stage2_crc32=f'0x{crc:08x}',stage2_sha256=sha(raw),
                    stage2_build_manifest=str(rdir/'manifest.json'),
                    stage2_manifest_sha256=sha((rdir/'manifest.json').read_bytes()),
                    program_sha256=sha(combined),size=size,compile_flags=pflags,
                    timer_status_address='0x343f7000',timer_status_words=224,
                    frozen_prefix_manifest_sha256=sha((base/'staged/manifest.json').read_bytes()))
    write_manifest(pdir,manifest,psources)
    print(json.dumps(dict(receiver=str(rdir),staged=str(pdir),receiver_bytes=len(raw),
                          receiver_sha256=sha(raw),prefix_boot_bytes=len(boot),
                          program_sha256=sha(combined),status='built; untested')))


if __name__=='__main__':main()
