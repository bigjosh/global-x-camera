"""Build packed RAW sector capture; offline only, no debugger/instrument calls."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import zlib
from producer_transform import transform as transform_producer
from phase_protocol import PHASE_PROTOCOL

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'firmware/capture-timing'))
from build_raw10 import compile_sources,replace,make_image,inspect_image,write_manifest,TC
from late_build import compile_with_late
sys.path.insert(0,str(ROOT/'firmware/capture-sd'))
_spec=importlib.util.spec_from_file_location('capture_sd_builder',ROOT/'firmware/capture-sd/build.py')
_sd_builder=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sd_builder)
check_recovery_identity=_sd_builder.check_recovery_identity
BASE=ROOT/'firmware/capture-sd/evidence/2026-10-24-normal-profile/build/v66c-normal-standby'
BASE_RECEIVER='20c5ddaef2e1bf6b78d272e3ee23f891ead2d41f88e922538962e218987f4e99'

def sha(data): return hashlib.sha256(data).hexdigest()

def relocate_prefix_crc(folder,prefix,compiled_crc,actual_crc):
    """Patch only two reviewed literal words, preserving compiler instruction layout.

    Arbitrary CRC constants can change GCC instruction selection and literal
    pool placement, including code before the conservative recovery boundary.
    Compile with v66c's pinned constant, then relocate its exact two data words.
    The generated ELF, raw image and disassembly remain mutually consistent.
    """
    offsets=(0xC9C,0x1354)
    old=struct.pack('<I',compiled_crc); new=struct.pack('<I',actual_crc)
    if compiled_crc!=0x3E97C7F7 or len(prefix)!=5140:
        raise ValueError('Unreviewed prefix CRC relocation geometry')
    if [i for i in range(len(prefix)) if prefix.startswith(old,i)]!=list(offsets):
        raise ValueError('Pinned CRC must occur only at its two reviewed literals')
    listing=(folder/'stage1.lst').read_text()
    elf_path=folder/'stage1.elf'; elf=bytearray(elf_path.read_bytes())
    if elf[:6]!=b'\x7fELF\x01\x01': raise ValueError('Expected little-endian ELF32')
    shoff=struct.unpack_from('<I',elf,32)[0]
    entsize,count=struct.unpack_from('<HH',elf,46)
    if entsize!=40 or shoff+entsize*count>len(elf): raise ValueError('Invalid ELF section table')
    result=bytearray(prefix)
    for offset in offsets:
        address=0x34180400+offset
        if not re.search(rf'^{address:x}:.*\s\.word\s+0x{compiled_crc:08x}\b',listing,re.M):
            raise ValueError('CRC relocation is not a disassembled data literal')
        matches=[]
        for i in range(count):
            section=struct.unpack_from('<10I',elf,shoff+i*entsize)
            _,kind,flags,base,at,length,*_=section
            if kind!=8 and flags&2 and base<=address and address+4<=base+length:
                matches.append(at+address-base)
        if len(matches)!=1 or elf[matches[0]:matches[0]+4]!=old:
            raise ValueError('CRC literal is not uniquely mapped in ELF')
        elf[matches[0]:matches[0]+4]=new
        result[offset:offset+4]=new
    (folder/'stage1-unrelocated.bin').write_bytes(prefix)
    (folder/'stage1-unrelocated.elf').write_bytes(elf_path.read_bytes())
    (folder/'stage1-unrelocated.lst').write_text(listing)
    elf_path.write_bytes(elf)
    subprocess.run([str(TC/'arm-none-eabi-objcopy.exe'),'-O','binary',str(elf_path),
                    str(folder/'stage1.bin')],check=True)
    if (folder/'stage1.bin').read_bytes()!=result:
        raise ValueError('Relocated ELF and raw prefix differ')
    listing=subprocess.check_output([str(TC/'arm-none-eabi-objdump.exe'),'-d',str(elf_path)],text=True)
    (folder/'stage1.lst').write_text(listing)
    return bytes(result),dict(schema=1,compiled_crc32=compiled_crc,actual_crc32=actual_crc,
        literal_offsets=list(offsets),unrelocated_sha256=sha(prefix),relocated_sha256=sha(result),
        instructions_unchanged=True)

def frozen_manifest(folder):
    """Use the archived bytes, not the old absolute/tmp provenance paths."""
    m=json.loads((folder/'manifest.json').read_text())
    names=set()
    for path,digest in m['sources'].items():
        name=Path(path).name
        if name in names: raise ValueError('Ambiguous archived source basename '+name)
        names.add(name)
        if sha((folder/name).read_bytes())!=digest:
            raise ValueError('Archived source hash differs: '+str(folder/name))
    return m

def transform_capture(text):
    text=replace(text,'#define BYTES (WIDTH * HEIGHT * 2U)',
        '#define BYTES (WIDTH * HEIGHT * 5U / 4U)\n#include "runtime.h"')
    text=replace(text,'DCMIPP_CSI_DT_BPP10)','DCMIPP_CSI_DT_BPP8)')
    text=replace(text,'.DataTypeIDA=DCMIPP_DT_RAW10','.DataTypeIDA=0x30U')
    text=replace(text,'if(raw_bits!=10U || raw_dt!=0x2BU)','if(raw_bits!=10U || raw_dt!=0x30U)')
    text=replace(text,'int main(void)\n{\n  fast_init();',
        'int main(void)\n{\n  raw_runtime_dispatch();\n  fast_init();')
    text=replace(text,'    frames++; event(30);','    frames++; raw_capture_frame_event(); event(30);')
    text=replace(text,'  arm_receiver();','  arm_receiver();\n  raw_capture_armed();')
    start=text.index('  uint32_t start=HAL_GetTick();\n  while (!frames)')
    body_start=text.index('  event(31);',start)
    body_end=text.index('  extern int photo_save_load(void);',body_start)
    body=text[body_start:body_end]
    body=replace(body,'  check(33, VD6G_Stop(&sensor));\n  CPROF[CP_SENSOR_STOP_DONE]=DWT->CYCCNT;\n  CPROF[CP_FLAGS]|=CP_F_SAFE_STOP;', '''#if RAW_ASYNC_STOP
  check(33,wr8(&sensor,0x0202,1U));
  capture_stop_started=DWT->CYCCNT; capture_stop_pending=1U;
#else
  check(33, VD6G_Stop(&sensor));
  CPROF[CP_SENSOR_STOP_DONE]=DWT->CYCCNT;
  CPROF[CP_FLAGS]|=CP_F_SAFE_STOP;
  capture_sensor_stopped=1U;
#endif''')
    body=replace(body,'  CPROF[CP_FLAGS]|=CP_F_RAW10;', '''  uint16_t exposure_coarse=0;
  check(0x8A,rd16(&sensor,0x0064,&exposure_coarse));
  /* Nominal sensor VT pixel clock from the frozen 160.8 MHz configuration;
   * retain the fractional line duration until the final integer-us rounding. */
  capture_exposure_us=((uint64_t)exposure_coarse*line_length*10000U+804000U)/1608000U;
  CPROF[CP_FLAGS]|=CP_F_RAW10;''')
    # Extract unchanged post-frame validation and the qualified STOP sequence.
    # It is called from the SD polling progress hook, never from an ISR.
    text=text[:start]+'  raw_storage_execute();\n}\n\n'+'''static uint32_t capture_finalizing,capture_ready,capture_sensor_stopped,capture_exposure_us,capture_async_error;
#if RAW_ASYNC_STOP
static uint32_t capture_stop_started,capture_stop_pending,capture_stop_poll;
#endif
uint32_t raw_capture_available(void) { return capture_ready?BYTES:0U; }
uint32_t raw_capture_fault(void) { return errors|hcam.ErrorCode|capture_async_error; }
uint32_t raw_capture_sensor_stopped(void) { return capture_sensor_stopped; }
uint32_t raw_capture_exposure_us(void) { return capture_exposure_us; }
void raw_capture_poll(void)
{
#if RAW_ASYNC_STOP
  if(capture_stop_pending) {
    uint32_t now=DWT->CYCCNT;
    if((uint32_t)(now-capture_stop_started)>400000000U) { capture_async_error=0x8BU; capture_stop_pending=0; return; }
    if((uint32_t)(now-capture_stop_poll)<400000U) return;
    capture_stop_poll=now;
    uint8_t ack=0xFF,state=0xFF;
    if(rd8(&sensor,0x0202,&ack)) { capture_async_error=0x8CU; capture_stop_pending=0; return; }
    if(ack) return;
    if(rd8(&sensor,0x0028,&state)) { capture_async_error=0x8DU; capture_stop_pending=0; return; }
    if(state!=2U) return;
    sensor.ctx.is_streaming=0; capture_stop_pending=0; capture_sensor_stopped=1;
    CPROF[CP_SENSOR_STOP_DONE]=DWT->CYCCNT; CPROF[CP_FLAGS]|=CP_F_SAFE_STOP;
    raw_capture_stopped(); return;
  }
#endif
  if(!frames || capture_finalizing || capture_ready) return;
  capture_finalizing=1U;
  volatile uint32_t *early_sensor=(volatile uint32_t *)0x343F4000U;
'''+body+'''  capture_ready=1U; __DSB();
  raw_capture_data_ready();
  if(capture_sensor_stopped) raw_capture_stopped();
  event(40);
}
'''
    return transform_producer(text)

def sensor_source(text):
    text=replace(text,'write_value(0x030F,0x2B,1)','write_value(0x030F,0x30,1)')
    return replace(text,'TRY(34,write_value(0x0400,0,2));', '''if(RAW_PATTERN) {
        TRY(38,write_value(0x0318,0,1)); TRY(39,write_value(0x0340,2,1));
    }
    TRY(34,write_value(0x0400,RAW_PATTERN?0x0121U:0U,2));''')

def shutdown_source(text):
    # Preserve the qualified peripheral teardown. Replace only its format-
    # specific admission checks, and use the new complete transaction record.
    text=replace(text,'#include "save_protocol.h"\n#include "save_module_config.h"\n#include "photo_fs.h"',
        '#include "runtime.h"')
    begin=text.index('#define SAVE_REPORT')
    end=text.index('#define DATA_OFF_REPORT',begin)
    text=text[:begin]+text[end:]
    begin=text.index('_Static_assert(sizeof(sd_card_t)')
    end=text.index('static int finish(',begin)
    text=text[:begin]+'''static int storage_complete(void)
{ return raw_storage_shutdown_ready()?CAMERA_PERIPHERAL_OK:CAMERA_PERIPHERAL_BAD_SAVE; }

'''+text[end:]
    text=text.replace('LOADER_REPORT[11]','((volatile const uint32_t *)RAW_PROOF_ADDRESS)[RP_END]')
    text=text.replace('SAVE_REPORT[P_TERMINAL]','((volatile const uint32_t *)RAW_PROOF_ADDRESS)[RP_TERMINAL]')
    text=text.replace('CARD_REPORT->media_idle','raw_card.media_idle')
    text=text.replace('FS_REPORT->completed','!raw_slots.active')
    return text

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--base',type=Path,default=BASE)
    p.add_argument('--pattern',choices=('scene','diagonal'),default='scene')
    p.add_argument('--transport',choices=('pio','idma'),default='idma')
    p.add_argument('--chunk-sectors',type=int,default=1024)
    p.add_argument('--flash',action='store_true')
    p.add_argument('--standby',action='store_true')
    p.add_argument('--async-stop',action='store_true')
    p.add_argument('--dma-sleep',action='store_true',help='Experimental shallow WFI during SD DMA, after sensor STOP')
    p.add_argument('--line-stream',action='store_true',help='Experimental conservative 64-line producer')
    p.add_argument('--preinit',action='store_true',help='RAM diagnostic: initialize SD before sensor start')
    p.add_argument('--snapshot',action='store_true',help='RAM diagnostic: copy the last 512 B at each published prefix')
    p.add_argument('--poison',action='store_true',help='RAM diagnostic: fill the frame with A5 before sensor start')
    a=p.parse_args()
    if a.standby and not a.flash: p.error('First qualify RAM awake; Standby currently flash-only')
    if a.flash and a.pattern!='scene':
        p.error('Flash builds preserve the exact scene prefix and recovery guard; use RAM for diagonal-pattern tests')
    if not 1<=a.chunk_sectors<=1024: p.error('chunk sectors must be1..1024')
    if a.async_stop and a.transport!='idma': p.error('Asynchronous I2C STOP polling requires IDMA transport')
    if a.dma_sleep and a.transport!='idma': p.error('DMA sleep requires IDMA transport')
    if (a.preinit or a.snapshot or a.poison) and (a.flash or not a.line_stream):
        p.error('Preinit/snapshot/poison require RAM LINEstreamdiagnostic mode')
    rbase=a.base/'receiver'; pbase=a.base/'staged'
    m=frozen_manifest(rbase); pm=frozen_manifest(pbase)
    if sha((rbase/'capture.bin').read_bytes())!=BASE_RECEIVER: raise ValueError('Frozen receiver mismatch')
    out=a.out.resolve(); out.mkdir(parents=True,exist_ok=False)
    compiled=[]
    excluded={'sleep.c','save_loader.c','module-save.bin','module-manifest.json','save_module_config.h','late_config.h'}
    for rel in m['sources']:
        src=rbase/Path(rel).name
        if src.name in excluded: continue
        dst=out/src.name
        data=src.read_bytes()
        if src.name=='capture.c': dst.write_text(transform_capture(data.decode().replace('\r\n','\n')),newline='\n')
        elif src.name=='phase_gpio.c':
            # RAW protocol v2: retain bounded GPIO writes but separate IDs by
            # 2 us, well above the measured ~0.24 us output/call overhead.
            phase=replace(data.decode().replace('\r\n','\n'),'event * 200U','event * 800U')
            phase=phase.replace('event * 200 nominal','event * 800 nominal')
            dst.write_text(phase,newline='\n')
        else: dst.write_bytes(data)
        if dst.suffix.lower() in ('.c','.s'): compiled.append(dst)
    # Keep driver headers relocatable when copied from their owning folder.
    for folder,names in [('capture-raw',('runtime.c','runtime.h','producer.c','producer.h')),
            ('sd-storage',('sd_card.c','sd_card.h')),
            ('raw-slots',('raw_slots.c','raw_slots.h'))]:
        for name in names:
            dst=out/name
            text=(ROOT/'firmware'/folder/name).read_text().replace('../sd-storage/sd_card.h','sd_card.h')
            dst.write_text(text,newline='\n')
            if dst.suffix=='.c': compiled.append(dst)
    if not a.flash:
        (out/'stage1_sensor.c').write_text(sensor_source((pbase/'stage1_sensor.c').read_text()),newline='\n')
        compiled.append(out/'stage1_sensor.c')
    if a.standby:
        for name in ('completion.c','completion.h','peripherals.c','peripherals.h'):
            data=(ROOT/'firmware/capture-sd/low_power'/name).read_text()
            if name=='peripherals.c': data=shutdown_source(data)
            if name=='completion.c':
                data=replace(data,'#include "status_leds.h"','#include "status_leds.h"\n#include "phase_gpio.h"')
                data=replace(data,'    LP[LPC_ARM_CYCLES]=DWT->CYCCNT;',
                    '    (void)phase_gpio_emit(10U);\n    LP[LPC_ARM_CYCLES]=DWT->CYCCNT;')
            (out/name).write_text(data,newline='\n')
            if name.endswith('.c'): compiled.append(out/name)
    flags=[f for f in m['compile_flags'] if f!='-I'+str(rbase)]
    flags.insert(0,'-I'+str(out))
    flags += [f'-DRAW_PATTERN={int(a.pattern=="diagonal")}',f'-DRAW_FLASH={int(a.flash)}',
              f'-DRAW_STANDBY={int(a.standby)}',f'-DRAW_DMA={int(a.transport=="idma")}',
              f'-DRAW_ASYNC_STOP={int(a.async_stop)}',
              f'-DRAW_DMA_SLEEP={int(a.dma_sleep)}',
              f'-DRAW_LINE_STREAM={int(a.line_stream)}',f'-DRAW_PREINIT={int(a.preinit)}',
              f'-DRAW_LINE_SNAPSHOTS={int(a.snapshot)}',f'-DRAW_LINE_POISON={int(a.poison)}',
              f'-DRAW_CHUNK_SECTORS={a.chunk_sectors}U','-DSTAGE1_SENSOR_TRIM=1',
              '-DLOW_POWER_MODE=3','-DLOW_POWER_ENTRY_DELAY_US=0']
    compiler=compile_with_late if a.flash else compile_sources
    code,size=compiler(out,compiled,flags,out/'capture.ld','capture',libc=True)
    late_meta=json.loads((out/'raw-late.json').read_text()) if a.flash else None
    symbols=(out/'symbols.txt').read_text()
    def symbol(name,required=True):
        match=re.search(r'^([0-9a-f]+) [A-Za-z] '+re.escape(name)+'$',symbols,re.M)
        if not match and required: raise ValueError('Missing symbol '+name)
        return int(match[1],16) if match else None
    park=symbol('raw_terminal_park'); refused=symbol('raw_context_refused_park')
    assert code[park-0x34300000:park-0x34300000+2]==b'\xfe\xe7'
    assert code[refused-0x34300000:refused-0x34300000+2]==b'\xfe\xe7'
    sp,entry=struct.unpack_from('<II',code)
    assert sp==0x343B0000 and len(code)<0xE000
    manifest=dict(schema=1,kind='raw-slots',load=0x34300000,entry=entry,stack=sp,
        stack_floor=symbol('_sstack'),park=park,reject_park=refused,
        failure_park=park,failure_park_policy='Same terminal loop; nonzero result is failure, never idle permission',
        request=0x343FD000,request_words=16,
        proof=0x343FD100,proof_words=96,read_buffer=0x34200000,read_buffer_bytes=262144,
        abort_address=0x343FD300,abort_words=16,
        chunk_trace=0x343FE000,chunk_trace_capacity=128,chunk_trace_words=8,
        frame=0x34000000,frame_bytes=1909600,width=1120,height=1364,
        guard=0x34000000+1909600,guard_bytes=32,allocation_bytes=1909600,
        bss_start=symbol('_sbss'),bss_end=symbol('_ebss'),data_start=symbol('_sdata'),
        data_end=symbol('_edata'),immutable_bytes=symbol('_sdata')-0x34300000,
        system_core_clock=symbol('SystemCoreClock'),card=symbol('raw_card'),slots=symbol('raw_slots'),
        pattern=int(a.pattern=='diagonal'),transport=a.transport,chunk_sectors=a.chunk_sectors,
        flash=a.flash,standby=a.standby,async_stop=a.async_stop,line_stream=a.line_stream,
        dma_sleep=a.dma_sleep,dma_wait=symbol('raw_dma_wait',a.dma_sleep),dma_wait_bytes=24,
        dma_wait_clock=(symbol('HAL_GetTick')|1) if a.dma_sleep else None,
        dma_sleep_clocks=symbol('raw_dma_sleep_clocks',a.dma_sleep),dma_sleep_clocks_words=14,
        preinit=a.preinit,line_snapshots=a.snapshot,line_poison=a.poison,
        producer=symbol('raw_producer',False),producer_bytes=416,
        snapshot_address=0x343D0000,snapshot_capacity=20,snapshot_bytes=512,
        expected_flags=int(a.async_stop)|(int(a.line_stream)<<1)|(int(a.preinit)<<2)|
            (int(a.snapshot)<<3)|(int(a.poison)<<4)|(int(a.dma_sleep)<<5),
        phase_markers=PHASE_PROTOCOL,
        binary_bytes=len(code),binary_sha256=sha(code),
        base_receiver_sha256=BASE_RECEIVER,base_prefix_sha256=pm['stage1_raw_sha256'],
        flags=flags,size=size,capture_available_boundary=('experimental 64-line holdback, complete FRAME for tail'
            if a.line_stream else 'hardware-tested complete-frame boundary'),
        storage_overlap='SD init overlaps camera capture and guarded STOP',hardware_status='untested',
        source_hashes={f.name:sha(f.read_bytes()) for f in out.iterdir() if f.suffix.lower() in ('.c','.h','.s','.ld')})
    if late_meta:
        manifest['late_load']=late_meta
        manifest['immutable_ranges']=late_meta['immutable_ranges']
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    if a.flash:
        pd=out/'staged'; pd.mkdir(); sources=[]
        for rel in pm['sources']:
            src=pbase/Path(rel).name; dst=pd/src.name
            if src.name=='stage1_sensor.c': dst.write_text(sensor_source(src.read_text()),newline='\n')
            else: dst.write_bytes(src.read_bytes())
            sources.append(dst)
        pf=[f for f in pm['compile_flags'] if not f.startswith(('-DSTAGE2_BYTES=','-DSTAGE2_EXPECTED_CRC32='))]
        pf.insert(0,'-I'+str(pd))
        early_code=code[:late_meta['early_bytes']]
        if len(early_code)!=15804: raise ValueError('Prefix layout requires fixed v66c early load size')
        pf += [f'-DSTAGE2_BYTES={len(early_code)}U','-DSTAGE2_EXPECTED_CRC32=0x3e97c7f7U',
               f'-DRAW_PATTERN={int(a.pattern=="diagonal")}']
        prefix,psize=compile_sources(pd,[s for s in sources if s.suffix.lower() in ('.c','.s')],pf,pd/'stage1.ld','stage1')
        prefix,crc_relocation=relocate_prefix_crc(pd,prefix,0x3E97C7F7,zlib.crc32(early_code))
        original=(pbase/'stage1.bin').read_bytes()
        literals=check_recovery_identity(pd,prefix,original,len(early_code))
        boot=make_image(prefix); assert len(boot)<=0x2000
        sector=bytearray(b'\xff'*65536); sector[:len(boot)]=boot; sector[0x2000:0x2000+len(code)]=code
        (pd/'stage1_boot.bin').write_bytes(boot); (pd/'stage2.bin').write_bytes(early_code)
        (pd/'stage2-full.bin').write_bytes(code)
        (pd/'capture_sector_0.bin').write_bytes(sector)
        pmanifest=copy.deepcopy(pm)
        for obsolete in ('capture_sd','low_power','status_leds','receiver_proof',
                         'receiver_byte_identical_to_v44','receiver_byte_identical_to_v45b'):
            pmanifest.pop(obsolete,None)
        pmanifest.update(stage1=inspect_image(boot),stage1_raw_bytes=len(prefix),stage1_raw_sha256=sha(prefix),
            stage2_bytes=len(early_code),stage2_crc32=hex(zlib.crc32(early_code)),stage2_sha256=sha(early_code),
            stage2_full_bytes=len(code),stage2_full_sha256=sha(code),late_load=late_meta,
            prefix_crc_relocation=crc_relocation,
            stage2_build_manifest=str(out/'manifest.json'),
            stage2_manifest_sha256=sha((out/'manifest.json').read_bytes()),program_sha256=sha(sector),
            completion_policy='Standby after complete RAW slot' if a.standby else 'Awake RAW terminal park',
            frame_bytes=1909600,pixel_format='mipi_raw10_packed',bytes_per_pixel=1.25,
            sample_alignment='four MSB bytes plus packed low-two-bit byte',
            compile_flags=pf,size=psize,raw_slots=manifest,checked_recovery_literal_offsets=literals,
            hardware_status='untested')
        pmanifest['recovery_gpio']['receiver_unchanged']=False
        pmanifest['recovery_gpio']['receiver_comparison']='RAW integration; exact early recovery bytes preserved'
        write_manifest(pd,pmanifest,sources)
    print(json.dumps(manifest,indent=2))

if __name__=='__main__': main()
