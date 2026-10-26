"""Opt-in error signaling integration; preserve the existing recovery path."""
import re
import struct

ENTRY = 0x34181840
BRIDGE = 0x34181820
PREFIX_BYTES = 5140
FAIL_OFFSET = 0xE6


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Error integration anchor mismatch: ' + old[:70])
    return text.replace(old, new)


def runtime_source(text):
    text = once(text, '#include "runtime.h"', '#include "runtime.h"\n#include "error_codes.h"\n#include "error_signal.h"')
    # The top-level owner has completed its bounded SD cleanup before terminal.
    # Early failures use the ROM-loaded handler and never enter unloaded code.
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
    .error_text 0x34181840 : { KEEP(*(.error_text)) } > PREFIX
    ASSERT(SIZEOF(.error_bridge) <= 32, "Error bridge overflow")
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
