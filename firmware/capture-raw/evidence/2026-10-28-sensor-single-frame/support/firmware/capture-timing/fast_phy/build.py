"""Offline guarded-v34c freerun early/STREAMING data-lane experiment."""
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

BASE_SHA='14b6015e0c5705ce5bde655470977851e32cce01fa0164ccda163b892dca3222'
BASE_RECEIVER_SHA='85313ae05070d80717c29a8a546bf56976930ac1f47b92e4ae70576ae72c940f'


def coarse_lines(value):
    value=int(value)
    if not 5<=value<=65535:
        raise argparse.ArgumentTypeError('Coarse exposure must be5..65535 lines')
    return value


def transform_sensor(text,coarse):
    """Change only the two little-endian manual-coarse bytes, plus their comment."""
    coarse=coarse_lines(coarse)
    original='static const uint8_t manual[12]={2,0,0x94,5,0,1,0,1,0,1,0,1}; /* 1428 */'
    if text.count(original)!=1:raise ValueError('Frozen manual exposure array changed')
    if coarse==1428:return text
    replacement=(f'static const uint8_t manual[12]={{2,0,0x{coarse&255:02X},'
                 f'0x{coarse>>8:02X},0,1,0,1,0,1,0,1}}; /* {coarse} */')
    return replace(text,original,replacement)


def transform_capture(text):
    text=replace(text,'__attribute__((noreturn)) static void fail(uint32_t where, int32_t result)',
        (HERE/'receiver_helpers.inc').read_text()+'\n__attribute__((noreturn)) static void fail(uint32_t where, int32_t result)')
    text=replace(text,'  TRACE[3] = (uint32_t)result;',
        '  __disable_irq();\n  TRACE[3] = (uint32_t)result;')
    text=replace(text,'  event(0x80000000U | where);\n  for (;;) __NOP();',
        '  event(0x80000000U | where);\n  fast_failure_quiesce(where,result);')
    text=replace(text,'irq_ier1=CSI->IER1; HAL_DCMIPP_CSI_IRQHandler(&hcam);',
        'irq_ier1=CSI->IER1; fast_snapshot(420); HAL_DCMIPP_CSI_IRQHandler(&hcam);')
    text=replace(text,'if(pin==GPIO_PIN_0) event(50);','if(pin==GPIO_PIN_0) { fast_strobes++; event(50); }')
    text=replace(text,'{ frames++; event(30); }','{ frames++; event(30); if(frames==1U) FAST[31]=fast_strobes; fast_snapshot(430); }')
    text=replace(text,'{ vsyncs++; event(29); }','{ vsyncs++; event(29); if(vsyncs==1U) FAST[30]=fast_strobes; fast_snapshot(429); }')
    text=replace(text,'int main(void)\n{\n  event(2);','int main(void)\n{\n  fast_init();\n  event(2);')
    text=replace(text,'  event(21);\n  check(22, HAL_DCMIPP_CSI_PIPE_Start',
        '  event(21);\n}\n\nstatic void arm_receiver(void)\n{\n  check(22, HAL_DCMIPP_CSI_PIPE_Start')
    text=replace(text,'  event(22);','  event(22); fast_snapshot(422);')
    text=replace(text,'  if(TRACE[61]>=1800000U) {\n    (void)HAL_DCMIPP_CSI_PIPE_Stop(&hcam,DCMIPP_PIPE0,DCMIPP_VIRTUAL_CHANNEL0);',
        '  if(TRACE[61]>=1800000U) {\n    /* Configuration missed budget; VC capture has not been armed. */')
    text=replace(text,'  do { check(0x76,rd8(&sensor,0x0028,&state));',
        '  FAST[9]=DWT->CYCCNT; event(425); fast_snapshot(425);\n  do { check(0x76,rd8(&sensor,0x0028,&state));')
    text=replace(text,'  event(26);',
        '''  FAST[10]=DWT->CYCCNT; event(26); fast_snapshot(426);
  fast_streaming_data_enable();
  fast_qualify_stop();
  if(frames || vsyncs) fail(0xA4,-1);
  FAST[22]=DWT->CYCCNT; FAST[23]=fast_strobes; FAST[24]=GPIOA->IDR&1U;
  event(441); fast_snapshot(441);
  arm_receiver();''')
    text=replace(text,'  event(31);','  event(31); fast_snapshot(431);')
    text=replace(text,'  check(32, HAL_DCMIPP_CSI_PIPE_Stop',
        '  fast_snapshot(435);\n  check(32, HAL_DCMIPP_CSI_PIPE_Stop')
    text=replace(text,'  check(33, VD6G_Stop(&sensor));',
        '''  fast_snapshot(439);
#if FAST_SHUTDOWN_DATA_OFF
  fast_shutdown_data_off();
#endif
  check(33, VD6G_Stop(&sensor));
  fast_snapshot(436);''')
    text=replace(text,'  event(40);',
        '  fast_snapshot(440); if(FAST[3]) fail(0xA2,-1); FAST[1]=40;\n  event(40);')
    return text


def transform_hal(text):
    text=replace(text,'extern void bench_delay_us(unsigned int us);',
        'extern void bench_delay_us(unsigned int us);\nextern void fast_phy_hook(unsigned int id);')
    return replace(text,'  SET_BIT(csi_instance->PRCR, CSI_PRCR_PEN);',
        '  fast_phy_hook(405);\n  SET_BIT(csi_instance->PRCR, CSI_PRCR_PEN);\n  fast_phy_hook(406);')


def symbol(folder,name):
    m=re.search(r'^([0-9a-fA-F]+) [Tt] '+re.escape(name)+r'$',(folder/'symbols.txt').read_text(),re.M)
    if not m: raise ValueError(f'Missing executable symbol {name}')
    return int(m[1],16)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--data-enable',choices=('early','streaming'),default='streaming')
    p.add_argument('--coarse-lines',type=coarse_lines,default=1428,
                   help='Manual coarse exposure5..65535; sensor constraints still apply (default1428)')
    p.add_argument('--shutdown-data-off',action='store_true',
                   help='After proved VC/pipe idle, disable data modules before sensor STOP')
    a=p.parse_args();base,out=a.base.resolve(),a.output.resolve()
    rm,pm=(checked_manifest(base/name) for name in ('receiver','staged'))
    original=(base/'staged/capture_sector_0.bin').read_bytes()
    frozen_receiver=(base/'receiver/capture.bin').read_bytes()
    if len(original)!=65536 or sha(original)!=BASE_SHA or pm['program_sha256']!=BASE_SHA:
        raise ValueError('Only exact guarded v34c sector is accepted')
    if sha(frozen_receiver)!=BASE_RECEIVER_SHA or rm['raw_sha256']!=BASE_RECEIVER_SHA or pm['stage2_sha256']!=BASE_RECEIVER_SHA:
        raise ValueError('Frozen v25 receiver mismatch')
    if original[FLASH_OFFSET:FLASH_OFFSET+len(frozen_receiver)]!=frozen_receiver:
        raise ValueError('Receiver is not exact sector content')
    if pm['recovery_gpio']['park_address']!='0x3418078c':
        raise ValueError('Unexpected v34c guard layout')
    out.mkdir(parents=True,exist_ok=False)
    rdir,pdir=out/'receiver',out/'staged';rdir.mkdir();pdir.mkdir()
    sources=[]
    for path in rm['sources']:
        source=ROOT/path;target=rdir/source.name
        if source.name=='capture.c':target.write_text(transform_capture(source.read_text()),encoding='utf-8',newline='\n')
        elif source.name=='hal_dcmipp.c':target.write_text(transform_hal(source.read_text()),encoding='utf-8',newline='\n')
        else:target.write_bytes(source.read_bytes())
        sources.append(target)
    flags=list(rm['compile_flags'])+[f'-DFAST_DATA_STREAMING={int(a.data_enable=="streaming")}',
                                  f'-DFAST_SHUTDOWN_DATA_OFF={int(a.shutdown_data_off)}']
    raw,size=compile_sources(rdir,[s for s in sources if s.suffix!='.ld'],flags,rdir/'capture.ld','capture',libc=True)
    sp,entry=struct.unpack_from('<II',raw);vectors=struct.unpack_from('<198I',raw)
    if sp!=0x343B0000 or not all(v==0 or (v&1 and 0x34300000<=v-1<0x34300000+len(raw)) for v in vectors[1:]):
        raise ValueError('Receiver vector validation failed')
    if len(raw)>=65536-FLASH_OFFSET:raise ValueError('Receiver exceeds first NOR sector')
    failure=symbol(rdir,'fast_failure_idle')
    if raw[failure-0x34300000:failure-0x34300000+2]!=bytes.fromhex('fee7'):
        raise ValueError('Failure park must be a branch-to-self')
    manifest=copy.deepcopy(rm)
    manifest.update(hardware_status='untested',raw_bytes=len(raw),raw_sha256=sha(raw),size=size,
        entry_point=hex(entry),compile_flags=flags,fast_phy_status_address='0x343f8000',
        fast_phy_status_words=544,fast_phy_status_schema=1,fast_phy_header_words=32,
        fast_phy_record_words=16,fast_phy_max_records=32,data_enable=a.data_enable,
        coarse_lines=a.coarse_lines,coarse_lines_source='prefix manual[2:4], little-endian',
        shutdown_data_off=a.shutdown_data_off,
        failure_park_address=hex(failure),failure_park_symbol='fast_failure_idle',failure_park_bytes='fee7',
        frozen_receiver_manifest_sha256=sha((base/'receiver/manifest.json').read_bytes()),
        generator_inputs={str(f.relative_to(ROOT)):sha(f.read_bytes()) for f in (Path(__file__),HERE/'receiver_helpers.inc')})
    manifest['parameters'].update(fast_phy_experiment=True,i2c_follower=False,coarse_lines=a.coarse_lines,
        data_lane_enable=a.data_enable,shutdown_data_off=a.shutdown_data_off,first_frame_latency_eligible=True,
        first_frame_qualification='pending; verify first-STROBE association at each exposure')
    if a.shutdown_data_off:
        manifest.update(shutdown_proof_address='0x343f8900',shutdown_proof_words=16,shutdown_proof_schema=1)
    write_manifest(rdir,manifest,sources)
    psources=[]
    for path in pm['sources']:
        source=ROOT/path;target=pdir/source.name
        if source.name=='stage1_sensor.c':
            target.write_text(transform_sensor(source.read_text(),a.coarse_lines),encoding='utf-8',newline='\n')
        else:target.write_bytes(source.read_bytes())
        psources.append(target)
    crc=zlib.crc32(raw)&0xFFFFFFFF
    pflags=[f for f in pm['compile_flags'] if not f.startswith(('-DSTAGE2_BYTES=','-DSTAGE2_EXPECTED_CRC32='))]
    pflags += [f'-DSTAGE2_BYTES={len(raw)}U',f'-DSTAGE2_EXPECTED_CRC32=0x{crc:08X}U']
    prefix,psize=compile_sources(pdir,[s for s in psources if s.suffix in ('.c','.S')],pflags,pdir/'stage1.ld','stage1')
    park=symbol(pdir,'recovery_gpio_park')
    if prefix[park-0x34180400:park-0x34180400+2]!=bytes.fromhex('fee7'):raise ValueError('Guard park changed')
    boot=make_image(prefix)
    if len(boot)>FLASH_OFFSET:raise ValueError('Prefix exceeds reserved NOR area')
    (pdir/'stage1_boot.bin').write_bytes(boot);(pdir/'stage2.bin').write_bytes(raw)
    combined=bytearray(original);combined[:len(boot)]=boot;combined[FLASH_OFFSET:FLASH_OFFSET+len(raw)]=raw
    if combined[len(boot):FLASH_OFFSET]!=original[len(boot):FLASH_OFFSET] or combined[FLASH_OFFSET+len(raw):]!=original[FLASH_OFFSET+len(raw):]:
        raise ValueError('Changed NOR outside prefix and receiver')
    (pdir/'capture_sector_0.bin').write_bytes(combined)
    old_prefix=(base/'staged/stage1.bin').read_bytes()
    if prefix[:0x658]!=old_prefix[:0x658]:raise ValueError('Qualified recovery code/literal pool changed')
    diffs=[i for i in range(min(len(prefix),len(old_prefix))) if prefix[i]!=old_prefix[i]]
    guard_source_names=('stage1.c','recovery_gpio.c','recovery_gpio.h','stage1.S')
    for name in guard_source_names:
        if (pdir/name).read_bytes()!=(base/'staged'/name).read_bytes():raise ValueError(f'Guard source changed: {name}')
    manifest=copy.deepcopy(pm)
    manifest.update(hardware_status='untested',stage1=inspect_image(boot),stage1_raw_bytes=len(prefix),
        stage1_raw_sha256=sha(prefix),stage2_bytes=len(raw),stage2_crc32=f'0x{crc:08x}',stage2_sha256=sha(raw),
        stage2_build_manifest=str(rdir/'manifest.json'),stage2_manifest_sha256=sha((rdir/'manifest.json').read_bytes()),
        program_sha256=sha(combined),size=psize,compile_flags=pflags,data_enable=a.data_enable,
        coarse_lines=a.coarse_lines,coarse_lines_source='prefix manual[2:4], little-endian',
        shutdown_data_off=a.shutdown_data_off,
        frozen_prefix_manifest_sha256=sha((base/'staged/manifest.json').read_bytes()),frozen_program_sha256=BASE_SHA,
        prefix_byte_differences_vs_v34c=diffs,prefix_same_size_as_v34c=len(prefix)==len(old_prefix),
        guard_sources_byte_identical_to_v34c=True,
        recovery_code_and_literals_bytes_identical=0x658,
        generator_inputs={str(f.relative_to(ROOT)):sha(f.read_bytes()) for f in (Path(__file__),HERE/'receiver_helpers.inc')})
    manifest['recovery_gpio'].update(park_address=hex(park),receiver_unchanged=False,
        clock_qualification='Inherited v34c guard; new prefix hardware qualification pending',
        external_drive='Qualified diode interface: JS110 bank3300mV, OUT0 high normal, low recovery')
    write_manifest(pdir,manifest,psources)
    print(json.dumps(dict(receiver=str(rdir),staged=str(pdir),receiver_bytes=len(raw),receiver_sha256=sha(raw),
        prefix_raw_bytes=len(prefix),prefix_boot_bytes=len(boot),program_sha256=sha(combined),
        prefix_raw_sha256=sha(prefix),recovery_park_address=hex(park),failure_park_address=hex(failure),
        prefix_byte_differences_vs_v34c=diffs,coarse_lines=a.coarse_lines,status='built; hardware untested')))


if __name__=='__main__':main()
