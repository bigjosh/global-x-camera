"""Opt-in error signaling integration; preserve the existing recovery path."""
import hashlib
import re
import struct

ENTRY = 0x34181840
BRIDGE = 0x34181820
PREFIX_BYTES = 5140
FAIL_OFFSET = 0xE6
RUNTIME_ENTRY = 0x343C8000
COPY_BYTES = 1536
COPY_PROOF = 0x343FD380
POST_FRAME_PROOF = 0x343FD3C0


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Error integration anchor mismatch: ' + old[:70])
    return text.replace(old, new)


def runtime_source(text):
    text = once(text, '#include "runtime.h"', '#include "runtime.h"\n#include "error_codes.h"\n#include "error_signal.h"')
    text = once(text, 'void raw_runtime_dispatch(void)\n{', '''void raw_runtime_dispatch(void)
{
#if RAW_ERROR_PREFIX
    /* Fresh copy before ANY terminal/camera path. Never trust retained SRAM
     * after a warm reset, and never return to the prefix after DMA is armed. */
    volatile uint32_t *proof=(volatile uint32_t *)ERROR_SIGNAL_COPY_PROOF;
    proof[0]=0U;
    if(SCB->CCR & SCB_CCR_DC_Msk) {
        ((void (*)(uint32_t))(ERROR_SIGNAL_PREFIX_ADDRESS|1U))(8U);
        __builtin_unreachable();
    }
    volatile uint32_t *dst=(volatile uint32_t *)ERROR_SIGNAL_RUNTIME_ADDRESS;
    volatile const uint32_t *src=(volatile const uint32_t *)ERROR_SIGNAL_PREFIX_ADDRESS;
    for(unsigned i=0;i<ERROR_SIGNAL_COPY_BYTES/4U;i++) dst[i]=src[i];
    __DSB();
    for(unsigned i=0;i<ERROR_SIGNAL_COPY_BYTES/4U;i++)
        if(dst[i]!=src[i]) {
            ((void (*)(uint32_t))(ERROR_SIGNAL_PREFIX_ADDRESS|1U))(8U);
            __builtin_unreachable();
        }
    SCB_InvalidateICache(); __DSB(); __ISB();
    proof[1]=ERROR_SIGNAL_RUNTIME_ADDRESS;
    proof[2]=ERROR_SIGNAL_COPY_BYTES;
    proof[0]=0x45435031U; /* ECP1: checked THIS boot, not SD-idle permission. */
    __DSB();
#endif''')
    # The top-level owner has completed its bounded SD cleanup before terminal.
    # Early receiver failures use the verified high-SRAM copy, not late code.
    text = once(text, '    status_led_set(result?STATUS_LED_ERROR:STATUS_LED_OFF);', '''    status_led_set(result?STATUS_LED_ERROR:STATUS_LED_OFF);
    if(result && operation==RAW_OP_CAPTURE) {
        uint32_t code=raw_error_blink_code(result,ABORT[4],raw_capture_fault(),
            raw_card.error,raw_magic_slots.error,P[RP_ARM]!=0U);
        P[RP_STATE]=15U; /* Failure remains failure; never publish idle success. */
        __DSB();
        error_signal_shutdown(code);
    }''')
    return text


def prefix_sources(folder, here):
    """Replace the failure loop/padding; append a fixed-address handler."""
    src = folder / 'stage1.c'
    text = src.read_text()
    text = once(text, '    for (;;) __NOP(); /* No WFI, BKPT, reset, retry or NOR abort. */',
        '    for (;;) __asm volatile("b.w error_stage1_bridge");')
    src.write_text(text, newline='\n')
    linker = folder / 'stage1.ld'
    text = linker.read_text()
    text = once(text, '    .data :', '''    .error_bridge 0x34181820 : { KEEP(*(.error_bridge)) } > PREFIX
    .error_text 0x34181840 : {
        _error_engine_start = .; KEEP(*(.error_text)) _error_engine_end = .;
        . = _error_engine_start + 1536; _error_copy_end = .;
    } > PREFIX
    ASSERT(SIZEOF(.error_bridge) <= 32, "Error bridge overflow")
    ASSERT(_error_engine_end <= _error_copy_end, "Error handler overflow")
    ASSERT(ADDR(.error_text) + SIZEOF(.error_text) <= 0x34182000, "Error handler overflow")
    .data :''')
    linker.write_text(text, newline='\n')
    bridge = folder / 'error_bridge.c'
    bridge.write_text('''#include "error_signal.h"
__attribute__((section(".error_bridge"),noreturn,noinline,used))
void error_stage1_bridge(void) {
    unsigned result=*(volatile unsigned *)0x343F3004U;
    error_signal_shutdown(result==17U?2U:8U);
}
''', newline='\n')
    paths = [bridge]
    for name in ('error_signal.c', 'error_signal.h'):
        p = folder / name
        p.write_bytes((here / name).read_bytes())
        paths.append(p)
    return paths


def inject_error(text, code):
    """RAM-only diagnostics: route real terminal categories, with no SD writes."""
    branches = {
        2: 'terminal(0x101U);',
        3: 'terminal(0x501U);',
        4: 'terminal(0x200U|SD_ERR_COMMAND_TIMEOUT);',
        5: 'terminal(0x330U|MAGIC_SLOTS_ERR_IO);',
        7: 'raw_magic_slots.error=MAGIC_SLOTS_ERR_FULL; terminal(0x320U|MAGIC_SLOTS_ERR_FULL);',
        8: 'terminal(0xF003U);',
    }
    if code==9:
        action='switch(Q[6]) {\n'+''.join(f'    case {n}: {branches.get(n, f"error_signal_shutdown({n}U);")}\n' for n in range(1,9))+'    default: break;\n    }'
    else:
        action='if(Q[6]==0x45525231U) { '+branches.get(code, f'error_signal_shutdown({code}U);')+' }'
    return once(text, '    status_led_boot_begin(); status_led_proof_init();',
        '    status_led_boot_begin(); status_led_proof_init();\n    '+action)


def inject_after_frame(text):
    """Explicit flash-only regression: real full camera DMA, no SD commands.

    This is a diagnostic profile, never selected by the normal build. It uses
    the ordinary failure terminal/renderer, after the production FRAME/STOP
    validation has proved the DMA destination is no longer being written.
    The retained record is observation only; it is not an idle/recovery gate.
    """
    return once(text, 'void raw_storage_execute(void)\n{', '''/* Volatile retains the ordinary storage graph for comparable flash layout;
 * this dedicated diagnostic image initializes it to one. */
__attribute__((used)) const volatile uint32_t raw_error_after_frame_enable=1U;
void raw_storage_execute(void)
{
    if(raw_error_after_frame_enable) {
    volatile uint32_t *test=(volatile uint32_t *)0x343FD3C0U;
    for(unsigned i=0;i<16U;i++) test[i]=0U;
    test[0]=0x45504631U; test[1]=1U; test[2]=DWT->CYCCNT;
    uint32_t started=HAL_GetTick();
    while(!raw_capture_frame_validated() || !raw_capture_sensor_stopped()) {
        raw_capture_poll();
        if(raw_capture_fault() || HAL_GetTick()-started>3000U) terminal(0x501U);
    }
    test[3]=DWT->CYCCNT;
    test[4]=raw_capture_frame_validated(); test[5]=raw_capture_sensor_stopped();
    test[6]=raw_capture_available(); test[7]=P[RP_DMA_BYTES];
    test[8]=P[RP_FRAMES]; test[9]=P[RP_CANARY];
    test[10]=*(volatile const uint32_t *)ERROR_SIGNAL_PREFIX_ADDRESS;
    test[11]=*(volatile const uint32_t *)ERROR_SIGNAL_RUNTIME_ADDRESS;
    test[12]=raw_card.initialized; test[13]=raw_card.controller_owned;
    test[14]=4U; test[15]=0x4550444EU; /* EPDN: complete frame before dispatch. */
    __DSB(); terminal(0x200U|SD_ERR_DATA);
    }
''')


def reserve_runtime(linker):
    text=linker.read_text()
    text=once(text, '  AXI_SRAM_UNCACHED (xrw)',
        '  ERROR_RUNTIME (rx)       : ORIGIN = 0x343C8000, LENGTH = 1536\n  AXI_SRAM_UNCACHED (xrw)')
    text=once(text, '  /* Uncached AXI SRAM */', '''  /* Persistent executable error copy; populated/verified before DMA. */
  .error_runtime (NOLOAD) : {
    _error_runtime_start = .; . += 1536; _error_runtime_end = .;
  } >ERROR_RUNTIME
  ASSERT(_error_runtime_start >= _estack, "Error copy overlaps receiver/stack")
  ASSERT(_error_runtime_start >= 0x343C2000, "Error copy overlaps low-power helper")
  ASSERT(_error_runtime_end <= 0x343D0000, "Error copy overlaps LINE snapshots")

  /* Uncached AXI SRAM */''')
    linker.write_text(text,newline='\n')


def audit_engine(folder):
    """Prove the complete linked source engine can be copied without fixups.

    All control flow and PC-relative accesses remain inside its one section;
    no indirect branch, PC write, memory code pointer or external call is
    permitted. Literal words may name fixed peripherals, never SRAM/code.
    Section padding is copied too, so its fixed-size source is ROM-loaded.
    """
    listing=(folder/'stage1.lst').read_text()
    engine=listing.split('34181840 <error_signal_shutdown>:',1)[1]
    # The PA2/PE9/PD12 boot hooks live in reserved copy padding. Exclude them
    # from engine decoding, but prohibit every engine branch/literal from
    # reaching it. Its bytes and reset-only entry are separately authenticated
    # by gpio_hold_prefix.check(). Legacy engines retain their exact audit.
    engine_end=ENTRY+COPY_BYTES
    if re.search(r'^34181df0 <gpio_hold_boot>:', listing, re.M):
        symbols=(folder/'symbols.txt').read_text()
        matches=re.findall(r'^([0-9a-fA-F]+) [A-Za-z] _error_engine_end$',symbols,re.M)
        if len(matches)!=1:
            raise ValueError('Missing actual error-engine end for embedded HOLD hook')
        engine_end=int(matches[0],16)
        if engine_end!=0x34181DC8:
            raise ValueError('Error engine boundary differs from reviewed embedded HOLD layout')
        image=(folder/'stage1.bin').read_bytes()
        hook=image[0x19F0:0x1A3C]
        # Only these exact reviewed boot-only byte sequences may occupy it.
        from gpio_hold_prefix import PA2_HOOK_SHA256, PE9_HOOK_SHA256, HOOK_SHA256
        if (any(image[engine_end-0x34180400:0x19F0]) or any(image[0x1A3C:0x1A40]) or
            hashlib.sha256(hook).hexdigest() not in (PA2_HOOK_SHA256, PE9_HOOK_SHA256, HOOK_SHA256)):
            raise ValueError('Unreviewed executable in reserved error-copy padding')

    instructions=0; literals=0; branches=0; pc_loads=0
    for line in engine.splitlines():
        m=re.match(r'^([0-9a-f]+):\s+((?:[0-9a-f]{4,8}\s+)+)\s*(.*)$',line)
        if not m: continue
        address=int(m[1],16)
        if not ENTRY<=address<engine_end: continue
        op=m[3].strip()
        if op.startswith('.word'):
            word=int(op.split()[1],16); literals+=1
            if 0x34000000<=word<0x34400000 or 0x70000000<=word<0xA0000000:
                raise ValueError('Copied error engine has an absolute memory/code pointer')
            continue
        if op.startswith(('.short','.byte','.inst')):
            raise ValueError('Unreviewed error engine data/instruction annotation')
        instructions+=1
        mnemonic=op.split()[0]
        branch=(mnemonic.split('.')[0] in ('b','bl','blx','bx','cbz','cbnz') or
                re.fullmatch(r'b(?:eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le)(?:\.\w+)?',mnemonic) or
                re.fullmatch(r'(?:wls|le|letp|wlstp)(?:\.[a-z0-9]+)*',mnemonic))
        if branch:
            target=re.search(r'\b([0-9a-f]{8})\s+<',op)
            if not target or not ENTRY<=int(target[1],16)<engine_end:
                raise ValueError('Copied error engine branches outside its section: '+line)
            branches+=1
        if re.search(r'\bpc\b',op):
            target=re.search(r'@\s*\(?([0-9a-f]{8})\s+<',op)
            if not mnemonic.startswith('ldr') or '[pc,' not in op or not target or not ENTRY<=int(target[1],16)<engine_end:
                raise ValueError('Unreviewed PC dependency in copied error engine: '+line)
            pc_loads+=1
        if mnemonic.startswith(('tbb','tbh','adr')) or re.match(r'\w+(?:\.\w+)?\s+(?:pc|r15)\b',op):
            raise ValueError('Copied error engine contains address-sensitive dispatch: '+line)
        if mnemonic.startswith('movt'):
            immediate=re.search(r'#(\d+)',op)
            if not immediate or 0x3400<=int(immediate[1])<0x3440:
                raise ValueError('Copied error engine contains an absolute RAM/code high half')
    if not instructions or not branches or not pc_loads:
        raise ValueError('Missing copied engine instruction coverage')
    blob=(folder/'stage1.bin').read_bytes()[ENTRY-0x34180400:ENTRY-0x34180400+COPY_BYTES]
    if len(blob)!=COPY_BYTES:
        raise ValueError('Complete error copy is not ROM-loaded')
    return dict(source=ENTRY,destination=RUNTIME_ENTRY,bytes=COPY_BYTES,
        copy_proof=COPY_PROOF,copy_proof_bytes=12,
        position_independent=True,branches=branches,pc_relative_loads=pc_loads,
        instructions=instructions,literal_words=literals)


def check_prefix(folder, prefix, original, early_bytes, checker):
    """All historical guard bytes/literals stay exact, except unreachable fail loop."""
    if not PREFIX_BYTES < len(prefix) <= 0x1C00:
        raise ValueError('Invalid extended prefix size')
    listing = (folder / 'stage1.lst').read_text()
    if not re.search(r'341804e6:.*\bb\.w\s+34181820 <error_stage1_bridge>', listing):
        raise ValueError('Failure loop must branch only to the fixed bridge')
    if not re.search(r'^34181840 <error_signal_shutdown>:', listing, re.M):
        raise ValueError('Failure engine entry moved')
    allowed = set(range(FAIL_OFFSET, FAIL_OFFSET + 6))
    allowed.update(range(0xC9C, 0xCA0))
    allowed.update(range(0x1354, 0x1358))
    # Existing packed-RAW sensor change versus the archived pre-RAW base.
    # This MOV-immediate is after the recovery guard and is not a new change.
    expected=bytearray(original)
    if expected[0x101A] != 0x2B or prefix[0x101A] != 0x30:
        raise ValueError('Unexpected sensor datatype literal')
    expected[0x101A]=0x30
    if any(a != b and i not in allowed for i, (a, b) in enumerate(zip(prefix[:PREFIX_BYTES], expected))):
        raise ValueError('Prefix changed outside failure branch and checked CRC literals')
    normal = bytearray(prefix[:PREFIX_BYTES])
    normal[FAIL_OFFSET:FAIL_OFFSET+6] = original[FAIL_OFFSET:FAIL_OFFSET+6]
    return checker(folder, bytes(normal), original, early_bytes)
