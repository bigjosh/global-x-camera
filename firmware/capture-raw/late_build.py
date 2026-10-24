"""Two-range cold image link: early camera first, storage loaded after arm.

Only generated build files are changed. No hardware access. Caller packages the
whole returned binary in NOR, but stage-one loads/CRCs only early_bytes from the
emitted raw-late.json. Runtime loader checks the independently computed late CRC.
"""
import json
from pathlib import Path
import re
import struct
import subprocess
import zlib

from build_raw10 import TC, replace

HERE=Path(__file__).resolve().parent
COLD_OBJECTS=('sd_card','raw_slots','magic_slots','completion','peripherals')
COLD_LIBGCC=('_aeabi_uldivmod.o','_udivmoddi4.o','_dvmd_tls.o')
COLD_RUNTIME=('sd_progress','configure_sd_master','complete_storage','init_card',
              'raw_storage_execute','raw_storage_shutdown_ready','payload_transport',
              'raw_capture_data_ready','raw_capture_stopped')


def audit_layout(code,symbols,listing,begin,end):
    """Reject early direct calls into unloaded code, with two reviewed exits.

    This is a layout regression guard, not a substitute for hardware timing.
    Sensor callbacks and IRQ code are retained early; the source transform puts
    the sole storage entry after the checked loader. A successful terminal may
    enter late Standby only after storage, and is separately guarded at runtime.
    """
    parsed={m[2]:int(m[1],16) for m in re.finditer(
        r'^([0-9a-f]+) [A-Za-z] (\S+)$',symbols,re.M)}
    for name in ('raw_late_load','DCMIPP_IRQHandler','CSI_IRQHandler',
                 'EXTI0_IRQHandler','SysTick_Handler','terminal','main','raw_capture_fail'):
        if not 0x34300000<=parsed[name]<begin:
            raise ValueError('Early function outside early range: '+name)
    for name in (*COLD_RUNTIME,'raw_capture_poll'):
        # Dead functions may be removed by the linker, e.g. Standby's guard in
        # an awake build; retained functions must obey their declared section.
        if name in parsed and not begin<=parsed[name]<end:
            raise ValueError('Late function outside late range: '+name)
    # The vector table ends at the first code address, which can precede Reset.
    first_code=min(int(m[1],16) for m in re.finditer(
        r'^([0-9a-f]+) [Tt] \S+$',symbols,re.M))
    vector_bytes=first_code-0x34300000
    for offset in range(4,vector_bytes,4):
        entry=struct.unpack_from('<I',code,offset)[0]
        if entry and not (entry&1 and 0x34300000<=(entry&~1)<begin):
            raise ValueError('Vector enters outside early range')
    for name,address in parsed.items():
        if (('Callback' in name and name.startswith(('HAL_DCMIPP','HAL_CSI'))) or
            name.startswith(('raw_line_snapshot','raw_capture_frame_event',
                             'raw_producer_line','raw_producer_frame'))):
            if not 0x34300000<=address<begin:
                raise ValueError('Indirect camera callback outside early range: '+name)
    cross=[]; loader_calls=[]; owner=''
    for line in listing.splitlines():
        label=re.match(r'[0-9a-f]+ <([^>]+)>:',line)
        if label: owner=label[1]
        m=re.match(r'\s*([0-9a-f]+):.*?\b(b(?:l|\.w|l\.w|x)?|b[a-z]{2}(?:\.w)?)\s+'
                   r'([0-9a-f]+)\s+<([^>]+)>',line)
        if not m: continue
        address,target=int(m[1],16),int(m[3],16)
        if m[4]=='raw_late_load': loader_calls.append(address)
        if address<begin and begin<=target<end:
            allowed=m[4] in ('raw_storage_execute','status_led_complete_sleep')
            if m[4]=='complete_storage' and owner=='raw_capture_fail': allowed=True
            if not allowed:
                raise ValueError('Unreviewed early-to-late branch: '+line.strip())
            cross.append(dict(address=address,target=target,name=m[4],owner=owner))
    storage=[v['address'] for v in cross if v['name']=='raw_storage_execute']
    if len(loader_calls)!=1 or len(storage)!=1 or storage[0]<=loader_calls[0]:
        raise ValueError('Storage entry must follow the sole checked late load')
    return dict(vectors_early=True,early_irq_symbols=True,direct_crossings=cross,
                loader_call=loader_calls[0],storage_call=storage[0])


def compile_with_late(out,sources,flags,linker,name,libc=True):
    out=Path(out); sources=list(sources); linker=Path(linker)
    capture=out/'capture.c'
    text=capture.read_text()
    text=replace(text,'  raw_capture_armed();',
                 '  raw_capture_armed();\n  extern int raw_late_load(void);\n  check(0xAF,raw_late_load());')
    # Full-frame validation and sensor STOP are serviced only by the storage
    # coordinator after this load. IRQ callbacks remain in the early range.
    text=replace(text,'void raw_capture_poll(void)\n{',
                 '__attribute__((section(".raw_late_text"),noinline,noclone))\n'
                 'void raw_capture_poll(void)\n{')
    capture.write_text(text,newline='\n')
    runtime=out/'runtime.c'
    text=runtime.read_text()
    fail_gate='''    if(*(volatile const uint32_t *)0x343F9E3CU!=0x524C4F4BU) {
        if(raw_card.initialized || raw_card.controller_owned || storage_call_depth)
            terminal(0xF003U); /* unexpected ownership stays visible/untouched */
        terminal(0x600U|(where&255U));
    }
#endif
    complete_storage(0x600U|(where&255U));'''
    if text.count(fail_gate)!=1:
        raise ValueError('Early capture failure must gate late cleanup on RLOK proof')
    text=replace(text,'void raw_capture_fail(uint32_t where,int32_t result)\n{',
                 '__attribute__((noinline,noclone,used))\n'
                 'void raw_capture_fail(uint32_t where,int32_t result)\n{')
    # A mutable operation variable is deliberately retained for RAM maintenance,
    # but volatile proof/IRQ accesses can prevent LTO from proving it constant.
    # Flash can only capture: compile away the maintenance dispatch so no early
    # failure/boot path can call the as-yet unloaded SD code.
    text=replace(text,'    if(operation==RAW_OP_CAPTURE) {',
                 '    if(1) { /* flash build: capture is the only operation */')
    text=replace(text,'    if(!result && operation==RAW_OP_CAPTURE) status_led_complete_sleep();',
                 '    if(!result && operation==RAW_OP_CAPTURE &&\n'
                 '       *(volatile uint32_t *)0x343F9E3CU==0x524C4F4BU)\n'
                 '        status_led_complete_sleep();')
    for function in COLD_RUNTIME:
        pattern=r'^(?=(?:static )?(?:void|int) '+re.escape(function)+r'\([^\n;]*\)(?:\n)? *\{)'
        text,n=re.subn(pattern,'__attribute__((section(".raw_late_text"),noinline,noclone))\n',text,flags=re.M)
        if n!=1: raise ValueError('Late runtime function mismatch: '+function)
    runtime.write_text(text,newline='\n')
    loader=out/'late_loader.c'; loader.write_bytes((HERE/'late_loader.c').read_bytes())
    sources.append(loader)
    exclusions=' '.join(['*_'+stem+'.o' for stem in COLD_OBJECTS]+
                        ['*libgcc.a:'+name for name in COLD_LIBGCC])
    text=linker.read_text()
    text=replace(text,'*(.text)',f'*(EXCLUDE_FILE ({exclusions}) .text)')
    text=replace(text,'*(.text*)',f'*(EXCLUDE_FILE ({exclusions}) .text*)')
    text=replace(text,'*(.rodata)',f'*(EXCLUDE_FILE ({exclusions}) .rodata)')
    text=replace(text,'*(.rodata*)',f'*(EXCLUDE_FILE ({exclusions}) .rodata*)')
    late='''  /* Appended load range: no early instruction or ISR may enter it. */
  /* Fixed old receiver length also preserves stage-one code generation and
   * its byte-identical recovery prefix; any spare early bytes are padding. */
  .raw_late 0x34303DBC :
  {
    . = ALIGN(4); _raw_late_start = .;
    *(.raw_late_text)
'''+''.join(f'    *_{stem}.o(.text .text.* .rodata .rodata.*)\n' for stem in COLD_OBJECTS)+''.join(
        f'    *libgcc.a:{name}(.text .text.* .rodata .rodata.*)\n' for name in COLD_LIBGCC)+'''
    . = ALIGN(4); _raw_late_end = .;
  } >AXISRAM2_P2_S

'''
    text=replace(text,'  /* Uninitialized data section into "RAM" Ram type memory */',
                 late+'  /* Uninitialized data section into "RAM" Ram type memory */')
    linker.write_text(text,newline='\n')
    # The CRC is a volatile const word, so changing it cannot constant-fold code
    # or shift the linked layout. The second pass must prove this invariant.
    crc_header=out/'raw_late_crc.h'
    expected=0x13579BDF
    first=None
    for iteration in range(2):
        crc_header.write_text(f'#define RAW_LATE_CRC32 0x{expected:08X}U\n',newline='\n')
        objects=[]
        for i,source in enumerate(sources):
            source=Path(source); obj=out/f'{i:02d}_{source.stem}.o'
            per_flags=list(flags)
            if source.stem in COLD_OBJECTS: per_flags+=['-fno-lto']
            subprocess.run([str(TC/'arm-none-eabi-gcc.exe'),*per_flags,'-c',str(source),'-o',str(obj)],check=True)
            objects.append(obj)
        elf=out/(name+'.elf')
        runtime_flags=['-nostartfiles','--specs=nano.specs','--specs=nosys.specs'] if libc else ['-nostdlib']
        libraries=['-lc','-lm','-lnosys'] if libc else []
        subprocess.run([str(TC/'arm-none-eabi-gcc.exe'),*flags,*runtime_flags,'-T',str(linker),
            *map(str,objects),'-Wl,--gc-sections,--build-id=none,--no-warn-rwx-segments',
            f'-Wl,-Map={out/(name+".map")}',*libraries,'-o',str(elf)],check=True)
        binary=out/(name+'.bin')
        subprocess.run([str(TC/'arm-none-eabi-objcopy.exe'),'-O','binary',str(elf),str(binary)],check=True)
        code=binary.read_bytes()
        symbols=subprocess.check_output([str(TC/'arm-none-eabi-nm.exe'),'--numeric-sort',str(elf)],text=True)
        def symbol(s):
            match=re.search(r'^([0-9a-f]+) [A-Za-z] '+re.escape(s)+'$',symbols,re.M)
            if not match: raise ValueError('Missing symbol '+s)
            return int(match[1],16)
        begin,end=symbol('_raw_late_start'),symbol('_raw_late_end')
        early=begin-0x34300000
        late_bytes=code[early:end-0x34300000]
        assert len(late_bytes)==end-begin and (early|len(late_bytes))&3==0
        calculated=zlib.crc32(late_bytes)
        if first is None:
            first=(early,end,late_bytes); expected=calculated
        elif first!=(early,end,late_bytes) or calculated!=expected:
            raise ValueError('CRC relink changed late code/layout')
    (out/'symbols.txt').write_text(symbols)
    listing=subprocess.check_output([str(TC/'arm-none-eabi-objdump.exe'),'-d',str(elf)],text=True)
    (out/(name+'.lst')).write_text(listing)
    layout=audit_layout(code,symbols,listing,begin,end)
    if early>15804:
        raise ValueError('Early load exceeds qualified v66c receiver size (15804 bytes)')
    late_meta=dict(schema=1,early_bytes=early,late_address=begin,late_bytes=end-begin,
        late_flash_offset=0x2000+early,late_crc32=expected,proof=0x343F9E00,
        immutable_ranges=[[0x34300000,symbol('_sdata')],[begin,end]],
        loader=symbol('raw_late_load'),after_arm=True,interrupts_enabled=True,
        changed_objects=list(COLD_OBJECTS),late_libgcc=list(COLD_LIBGCC),
        late_runtime_functions=list(COLD_RUNTIME),layout_audit=layout)
    (out/'raw-late.json').write_text(json.dumps(late_meta,indent=2)+'\n')
    size=subprocess.check_output([str(TC/'arm-none-eabi-size.exe'),str(elf)],text=True)
    return code,size
