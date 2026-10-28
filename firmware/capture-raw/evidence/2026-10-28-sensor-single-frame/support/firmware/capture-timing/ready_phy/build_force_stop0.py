"""Offline both-lane ForceRx zero-dwell discriminator; no hardware access.

Keep frozen v39 mode5 sequencing, but permit no extra stable-STOP dwell.
Both STOP flags and their continued presence at release remain mandatory.
"""
import argparse
import copy
import json
from pathlib import Path
import re
import struct
import sys
import zlib

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from build_raw10 import (ROOT,FLASH_OFFSET,checked_manifest,compile_sources,
                        make_image,inspect_image,replace,sha,write_manifest)
sys.path.insert(0,str(HERE))
import force_rx

RECEIVER_SHA='011c78f17017b7bbea632d40402bf232349c0a099408e63f5ae466f8416a5fb9'
BASES={
    '40743205503bdb465d0549b7764f1590c48b7aaac621bf096aa4b9618957c1bd':1428,
    '7c99395b5a23e063e3c6e7b6ce06b9abf041f3736a004dcd4fc6bf275dcccc6b':5,
}


def transform_capture(text,dwell_us,readiness='streaming'):
    if dwell_us not in (0,10,100):raise ValueError('Reviewed STOP dwell choices are0,10,100us')
    if readiness!='force_stop' or dwell_us not in (0,100):
        raise ValueError('This discriminator only supports mode5 STOP0 or its100us control')
    begin=text.index('static void fast_qualify_stop(void)')
    end=text.index('\n#if FAST_SHUTDOWN_DATA_OFF',begin)
    original=text[begin:end]
    changed=replace(original,'(uint32_t)(DWT->CYCCNT-stable)>=40000U',
                    f'(uint32_t)(DWT->CYCCNT-stable)>={dwell_us*400}U')
    if 'if((sr&stop_data)==stop_data)' not in changed:raise ValueError('Both data STOP flags must gate readiness')
    text=text[:begin]+changed+text[end:]
    if readiness=='ack':
        text=replace(text,'FAST[6]=FAST_DATA_STREAMING; FAST[8]=1U;',
                     'FAST[6]=READY_GATE; FAST[8]=1U;')
        verify='''  do { check(0x76,rd8(&sensor,0x0028,&state)); if(HAL_GetTick()-ack_started>500U) fail(0x76,-100); } while(state!=3U);
  sensor.ctx.is_streaming=1;
  TRACE[28]=TRACE[35]; TRACE[29]=HAL_GPIO_ReadPin(GPIOA,GPIO_PIN_0);
  FAST[10]=DWT->CYCCNT; event(26); fast_snapshot(426);
'''
        text=replace(text,verify,'')
        text=replace(text,'  arm_receiver();\n  uint32_t start=HAL_GetTick();',
                     '  arm_receiver();\n'+verify+'  uint32_t start=HAL_GetTick();')
    text=force_rx.capture(text)
    if dwell_us==0:text=replace(text,'FORCE[28]=40000U;','FORCE[28]=0U;')
    return text


def symbol(folder,name):
    match=re.search(r'^([0-9a-fA-F]+) [Tt] '+re.escape(name)+r'$',(folder/'symbols.txt').read_text(),re.M)
    if not match:raise ValueError(f'Missing executable symbol{name}')
    return int(match[1],16)


def validate_base(base,rm,pm,original,receiver):
    digest=sha(original)
    if len(original)!=65536 or digest not in BASES or pm['program_sha256']!=digest:
        raise ValueError('Only reviewed exact v36 default/5-line sectors are supported')
    if sha(receiver)!=RECEIVER_SHA or rm['raw_sha256']!=RECEIVER_SHA or pm['stage2_sha256']!=RECEIVER_SHA:
        raise ValueError('Receiver does not match reviewed v36 bytes')
    if original[FLASH_OFFSET:FLASH_OFFSET+len(receiver)]!=receiver:
        raise ValueError('Receiver is not exact sector content')
    if not rm['shutdown_data_off'] or rm['data_enable']!='streaming' or rm['coarse_lines']!=BASES[digest]:
        raise ValueError('Unexpected v36 receiver configuration')
    if (rm.get('fast_phy_status_address')!='0x343f8000' or rm.get('fast_phy_status_words')!=544 or
        rm.get('shutdown_proof_address')!='0x343f8900' or rm.get('shutdown_proof_words')!=16):
        raise ValueError('Unexpected fixed diagnostic layout')
    if pm['recovery_gpio']['park_address']!='0x3418078c':raise ValueError('Unexpected recovery guard')
    return digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--stop-dwell-us',type=int,choices=(0,100),default=0)
    parser.add_argument('--readiness',choices=('force_stop',),default='force_stop')
    args=parser.parse_args();base,out=args.base.resolve(),args.output.resolve()
    force_pair=args.readiness in ('early_stop','force_stop')
    gate={'streaming':1,'ack':2,'early_stop':4,'force_stop':5}[args.readiness]
    readiness={'streaming':'start_ack_and_streaming','ack':'start_ack',
               'early_stop':'early_data_both_stop_stable100us',
               'force_stop':'force_rx_both_stop_stable100us'}[args.readiness]
    rm,pm=(checked_manifest(base/name) for name in ('receiver','staged'))
    original=(base/'staged/capture_sector_0.bin').read_bytes()
    old_receiver=(base/'receiver/capture.bin').read_bytes()
    base_sha=validate_base(base,rm,pm,original,old_receiver)
    out.mkdir(parents=True,exist_ok=False)
    rdir,pdir=out/'receiver',out/'staged';rdir.mkdir();pdir.mkdir()
    sources=[]
    for path in rm['sources']:
        source=ROOT/path;target=rdir/source.name
        if source.name=='capture.c':target.write_text(transform_capture(source.read_text(),args.stop_dwell_us,args.readiness),encoding='utf-8',newline='\n')
        elif source.name=='hal_dcmipp.c' and force_pair:
            target.write_text(force_rx.hal(source.read_text(),args.readiness=='force_stop'),encoding='utf-8',newline='\n')
        else:target.write_bytes(source.read_bytes())
        sources.append(target)
    flags=list(rm['compile_flags'])
    if args.readiness=='ack':flags+=['-DREADY_GATE=2']
    if force_pair:
        flags=[f for f in flags if not f.startswith('-DFAST_DATA_STREAMING=')]
        flags+=['-DFAST_DATA_STREAMING=0',f'-DREADY_GATE={gate}']
    raw,size=compile_sources(rdir,[p for p in sources if p.suffix!='.ld'],flags,rdir/'capture.ld','capture',libc=True)
    sp,entry=struct.unpack_from('<II',raw);vectors=struct.unpack_from('<198I',raw)
    if sp!=0x343B0000 or not all(v==0 or (v&1 and 0x34300000<=v-1<0x34300000+len(raw)) for v in vectors[1:]):
        raise ValueError('Receiver vector validation failed')
    if len(raw)>=65536-FLASH_OFFSET:raise ValueError('Receiver exceeds first sector')
    failure=symbol(rdir,'fast_failure_idle')
    if raw[failure-0x34300000:failure-0x34300000+2]!=bytes.fromhex('fee7'):raise ValueError('Failure park changed')
    control=args.stop_dwell_us==100 and args.readiness=='streaming'
    if control and raw!=old_receiver:raise ValueError('Matched100us receiver must be byte-identical to v36')
    manifest=copy.deepcopy(rm)
    manifest.update(hardware_status='untested',raw_bytes=len(raw),raw_sha256=sha(raw),size=size,
        entry_point=hex(entry),compile_flags=flags,failure_park_address=hex(failure),
        stop_dwell_us=args.stop_dwell_us,stop_dwell_cycles=args.stop_dwell_us*400,
        data_stop_state_required=True,data_enable=args.readiness,
        readiness_gate=gate,data_enable_readiness=readiness,
        frozen_receiver_manifest_sha256=sha((base/'receiver/manifest.json').read_bytes()),
        generator_inputs={str(Path(__file__).relative_to(ROOT)):sha(Path(__file__).read_bytes())})
    manifest['parameters'].update(ready_phy_experiment=True,stop_dwell_us=args.stop_dwell_us,
        data_lane_enable=args.readiness,
        data_stop_state_required=True,first_frame_qualification='pending hardware qualification of this exact variant')
    if force_pair:
        manifest.update(force_rx_proof_address='0x343f8940',force_rx_proof_words=32,
            force_rx_proof_schema=1,force_rx_retained=args.readiness=='force_stop',
            physical_data_enable='before_pen',data_check_events_are_lane_enable=False,
            force_rx_proof_initialization='receiver_entry_after_stage1_sensor_start_before_phy_configuration')
        manifest['generator_inputs'][str((HERE/'force_rx.py').relative_to(ROOT))]=sha((HERE/'force_rx.py').read_bytes())
    write_manifest(rdir,manifest,sources)
    psources=[]
    for path in pm['sources']:
        source=ROOT/path;target=pdir/source.name
        target.write_bytes(source.read_bytes());psources.append(target)
    crc=zlib.crc32(raw)&0xFFFFFFFF
    pflags=[f for f in pm['compile_flags'] if not f.startswith(('-DSTAGE2_BYTES=','-DSTAGE2_EXPECTED_CRC32='))]
    pflags += [f'-DSTAGE2_BYTES={len(raw)}U',f'-DSTAGE2_EXPECTED_CRC32=0x{crc:08X}U']
    prefix,psize=compile_sources(pdir,[p for p in psources if p.suffix in ('.c','.S')],pflags,pdir/'stage1.ld','stage1')
    old_prefix=(base/'staged/stage1.bin').read_bytes()
    guard_bytes=0x830 if args.readiness=='streaming' else 0x658
    if prefix[:guard_bytes]!=old_prefix[:guard_bytes]:raise ValueError('Reviewed recovery code/literal slice changed')
    park=symbol(pdir,'recovery_gpio_park')
    if park!=0x3418078C or prefix[park-0x34180400:park-0x34180400+2]!=bytes.fromhex('fee7'):
        raise ValueError('Qualified recovery park changed')
    boot=make_image(prefix)
    if len(boot)>FLASH_OFFSET:raise ValueError('Prefix exceeds reserved NOR region')
    combined=bytearray(original);combined[:len(boot)]=boot;combined[FLASH_OFFSET:FLASH_OFFSET+len(raw)]=raw
    if combined[len(boot):FLASH_OFFSET]!=original[len(boot):FLASH_OFFSET] or combined[FLASH_OFFSET+len(raw):]!=original[FLASH_OFFSET+len(raw):]:
        raise ValueError('Changed NOR beyond prefix and receiver')
    if control and (prefix!=old_prefix or combined!=original):
        raise ValueError('Matched100us control must be the byte-identical v36 sector')
    (pdir/'stage1_boot.bin').write_bytes(boot);(pdir/'stage2.bin').write_bytes(raw)
    (pdir/'capture_sector_0.bin').write_bytes(combined)
    manifest=copy.deepcopy(pm)
    manifest.pop('prefix_byte_differences_vs_v34c',None)
    manifest.pop('prefix_same_size_as_v34c',None)
    manifest.update(hardware_status='untested',stage1=inspect_image(boot),stage1_raw_bytes=len(prefix),
        stage1_raw_sha256=sha(prefix),stage2_bytes=len(raw),stage2_crc32=f'0x{crc:08x}',stage2_sha256=sha(raw),
        stage2_build_manifest=str(rdir/'manifest.json'),stage2_manifest_sha256=sha((rdir/'manifest.json').read_bytes()),
        program_sha256=sha(combined),size=psize,compile_flags=pflags,
        stop_dwell_us=args.stop_dwell_us,stop_dwell_cycles=args.stop_dwell_us*400,
        data_stop_state_required=True,data_enable=args.readiness,
        readiness_gate=gate,data_enable_readiness=readiness,
        frozen_program_sha256=base_sha,frozen_prefix_manifest_sha256=sha((base/'staged/manifest.json').read_bytes()),
        prefix_first_bytes_identical_to_v36=guard_bytes,guard_sources_byte_identical_to_v36=True,
        prefix_same_size_as_v36=len(prefix)==len(old_prefix),
        prefix_byte_differences_vs_v36=[i for i,(a,b) in enumerate(zip(prefix,old_prefix)) if a!=b],
        generator_inputs={str(Path(__file__).relative_to(ROOT)):sha(Path(__file__).read_bytes())})
    write_manifest(pdir,manifest,psources)
    print(json.dumps(dict(staged=str(pdir),receiver=str(rdir),stop_dwell_us=args.stop_dwell_us,readiness=args.readiness,
        coarse_lines=BASES[base_sha],receiver_bytes=len(raw),receiver_sha256=sha(raw),
        prefix_raw_bytes=len(prefix),prefix_boot_bytes=len(boot),prefix_raw_sha256=sha(prefix),
        program_sha256=sha(combined),recovery_park_address=hex(park),failure_park_address=hex(failure),
        prefix_unchanged_bytes=guard_bytes,
        matched_control_byte_identical=control,status='built; hardware untested')))


if __name__=='__main__':main()
