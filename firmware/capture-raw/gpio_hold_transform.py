"""Opt-in PA2/A3 HOLD release at the last possible Standby instruction boundary.

No hardware access. The earlier prefix establishes HOLD; ordinary work and
UART park do not release it. Every new instruction in the copied error engine
is position independent, with no absolute code/data pointer or helper call.
"""
from pathlib import Path
import hashlib
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Reviewed Thumb-2 group shared by both linked sites. Pinning the encoding as
# well as objdump's text prevents a modified listing from vouching for changed
# machine code. The only 16-bit instruction is WFI at byte 40.
LEGACY_STANDBY_OPCODES = bytes.fromhex(
    '40f60040c5f20260d0f80c1021f44041c0f80c10d0f8001021f44041c0f80010'
    'bff34f8fbff36f8f30bf4ff08001c0f81810d0f8001021f4404141f48041'
    'c0f80010bff34f8f')


# PA2 keeps the same 70-byte release group and fixed WFI offset as legacy PD7.
STANDBY_OPCODES = bytes.fromhex(
    '40f20000c5f20260d0f80c1021f03001c0f80c10d0f8001021f03001c0f80010'
    'bff34f8fbff36f8f30bf4ff00401c0f81810d0f8001021f0300141f01001'
    'c0f80010bff34f8f')


def pin_source(text, pin):
    """Preserve exact historical PD7 source; only PA2 is emitted by new builds."""
    if pin == 'PD7':
        return text
    if pin != 'PA2':
        raise ValueError('Unknown GPIO HOLD pin profile')
    for old, new in (('GPIOD', 'GPIOA'), ('PD7', 'PA2'), ('0x56020C00', '0x56020000'),
                     ('0x0c00', '0x0000'), ('0xc000', '0x0030'),
                     ('0x4000', '0x0010'), ('0x80', '0x04')):
        text = text.replace(old, new)
    return text


def contract_pin(value, standby):
    validate_contract(value, standby)
    return 'PA2' if value['schema'] == 3 else 'PD7'


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('GPIO HOLD anchor mismatch: ' + old[:70])
    return text.replace(old, new)


def contract(standby, *, schema=3):
    """Describe policy separately from the unchanged release instructions.

    Schemas 1 and 2 retain the exact historical PD7 packages.
    Schema 3 moves the pin to PA2/A3; no other release policy changes.
    Schema 1 was used by the frozen November 7 packages.
    Schema 2 records the user's subsequent no-extra-off-delay prototype choice;
    accepting that choice does not qualify AUX-before-main rail sequencing.
    """
    if type(standby) is not bool:
        raise ValueError('GPIO HOLD standby selector must be boolean')
    if type(schema) is not int or schema not in (1, 2, 3):
        raise ValueError('Unknown GPIO HOLD contract schema')
    result = dict(schema=schema, port='GPIOD', pin=7, header='Arduino D9 / CN14.2',
                active='push_pull_high',
                release='input_no_pull_immediately_before_standby_wfi',
                success_release=standby, error_release=True,
                awake_completion='hold_high', shallow_fallback='hold_high',
                unexpected_wfi_return='reassert_high',
                external_off_delay_required=(schema == 1))
    if schema >= 2:
        result.update(external_off_delay='omitted_user_accepted_prototype',
                      aux_before_main_shutdown_qualified=False)
    if schema == 3:
        result.update(port='GPIOA', pin=2, header='Arduino A3 / CN4.4')
    return result


def validate_contract(value, standby):
    """Accept an exact known policy, never infer physical latch qualification."""
    if (type(value) is not dict or type(value.get('schema')) is not int or
            value.get('schema') not in (1, 2, 3)):
        raise ValueError('GPIO HOLD contract differs from the selected completion profile')
    expected = contract(standby, schema=value.get('schema'))
    if (value != expected or any(type(value[k]) is not type(v) for k, v in expected.items())):
        raise ValueError('GPIO HOLD contract differs from the selected completion profile')


# Explicit instruction group: no callback, interrupt, compiler-generated call,
# status logging or wait can separate floating HOLD from the WFI instruction.
# Only this pin's two-bit fields change. ODR remains HIGH through release.
# IRQs are disabled by both established callers; an unexpected WFI return
# immediately reasserts HIGH before the caller records/reports its failure.
def standby_asm(kind, *, pin="PA2"):
    if kind not in ('success', 'error'):
        raise ValueError('Unknown GPIO HOLD site')
    wfi_label = 'status_led_sleep_idle' if kind == 'success' else 'gpio_hold_error_wfi'
    lines = [
        f'.global gpio_hold_{kind}_release', f'gpio_hold_{kind}_release:',
        'movw r0, #0x0c00', 'movt r0, #0x5602',
        'ldr.w r1, [r0, #12]', 'bic.w r1, r1, #0xc000',
        'str.w r1, [r0, #12]',
        'ldr.w r1, [r0]', 'bic.w r1, r1, #0xc000', 'str.w r1, [r0]',
        'dsb sy', 'isb sy', f'.global {wfi_label}', f'{wfi_label}:', 'wfi',
        f'.global gpio_hold_{kind}_reassert', f'gpio_hold_{kind}_reassert:',
        'mov.w r1, #0x80', 'str.w r1, [r0, #24]',
        'ldr.w r1, [r0]', 'bic.w r1, r1, #0xc000',
        'orr.w r1, r1, #0x4000', 'str.w r1, [r0]', 'dsb sy',
        f'.global gpio_hold_{kind}_end', f'gpio_hold_{kind}_end:',
    ]
    return pin_source(('    __asm volatile(\n' + ''.join('        "' + line + '\\n"\n' for line in lines)
            + '        ::: "r0", "r1", "memory");'), pin)


ASSERTIONS = '''
#if !defined(RAW_GPIO_HOLD) || RAW_GPIO_HOLD != 1
#error GPIO HOLD source requires its explicit profile flag
#endif
_Static_assert(GPIOD_BASE == 0x56020C00UL, "HOLD assembly requires secure GPIOD");
_Static_assert(__builtin_offsetof(GPIO_TypeDef, MODER) == 0U, "HOLD MODER offset");
_Static_assert(__builtin_offsetof(GPIO_TypeDef, PUPDR) == 12U, "HOLD PUPDR offset");
_Static_assert(__builtin_offsetof(GPIO_TypeDef, BSRR) == 24U, "HOLD BSRR offset");
'''


SUCCESS_ANCHOR = '''    __asm volatile(".global status_led_sleep_idle\\n"
                   "status_led_sleep_idle:\\n"
                   "wfi\\n" ::: "memory");'''


def completion_source(text, *, pin="PA2"):
    """Call after the existing completion/error/phase source transforms."""
    text = once(text, '#include "phase_gpio.h"', '#include "phase_gpio.h"\n' + pin_source(ASSERTIONS, pin))
    text = once(text, '    RCC->AHB4ENSR=RCC_AHB4ENSR_PWRENS;',
                pin_source('    RCC->AHB4ENSR=RCC_AHB4ENSR_PWRENS | RCC_AHB4ENSR_GPIODENS;', pin))
    text = once(text, '        refused(LPC_ERROR_PWR_ACCESS);',
                pin_source('''        refused(LPC_ERROR_PWR_ACCESS);
    if (!(RCC->AHB4ENR & RCC_AHB4ENR_GPIODEN) ||
        (RCC->AHB4RSTR & RCC_AHB4RSTR_GPIODRST))
        refused(LPC_ERROR_PWR_ACCESS);''', pin))
    text = once(text, SUCCESS_ANCHOR,
                '#if LOW_POWER_MODE != 3\n#error GPIO HOLD completion requires Standby\n#endif\n'
                + standby_asm('success', pin=pin))
    return text


def error_source(text, *, pin="PA2"):
    """Call on generated staged/error_signal.c after prefix_sources()."""
    text = once(text, '#include "stm32n657xx.h"', '#include "stm32n657xx.h"\n' + pin_source(ASSERTIONS, pin))
    text = once(text, '    RCC->AHB4ENSR=RCC_AHB4ENSR_PWRENS;',
                pin_source('    RCC->AHB4ENSR=RCC_AHB4ENSR_PWRENS | RCC_AHB4ENSR_GPIODENS;', pin))
    text = once(text, '        !(RCC->AHB4ENR & RCC_AHB4ENR_PWREN) || (RCC->AHB4RSTR & RCC_AHB4RSTR_PWRRST) ||',
                pin_source('''        !(RCC->AHB4ENR & RCC_AHB4ENR_PWREN) || (RCC->AHB4RSTR & RCC_AHB4RSTR_PWRRST) ||
        !(RCC->AHB4ENR & RCC_AHB4ENR_GPIODEN) || (RCC->AHB4RSTR & RCC_AHB4RSTR_GPIODRST) ||''', pin))
    return once(text, '    __DSB(); __ISB(); __WFI();', standby_asm('error', pin=pin))


def canonical_completion():
    """Reconstruct only the existing normal FLASH Standby source profile."""
    text = (ROOT/'firmware/capture-sd/low_power/completion.c').read_text()
    text = once(text, '#include "completion.h"', '#include "completion.h"\n#include "error_signal.h"')
    text = once(text, '    publish(LPC_STATE_REFUSED);', '    publish(LPC_STATE_REFUSED);\n    error_signal_shutdown(8U);')
    text = once(text, '    publish(LPC_STATE_RETURNED);', '    publish(LPC_STATE_RETURNED);\n    error_signal_shutdown(8U);')
    text = once(text, '#include "status_leds.h"', '#include "status_leds.h"\n#include "phase_gpio.h"')
    return once(text, '    LP[LPC_ARM_CYCLES]=DWT->CYCCNT;',
                '    (void)phase_gpio_emit(10U);\n    LP[LPC_ARM_CYCLES]=DWT->CYCCNT;')


def audit_sources(folder, standby, *, pin="PA2"):
    """Bind complete generated shutdown sources, not merely marker strings."""
    contract(standby)
    folder = Path(folder)
    expected = {'staged/error_signal.c': error_source((HERE/'error_signal.c').read_text(), pin=pin)}
    if standby:
        expected['completion.c'] = completion_source(canonical_completion(), pin=pin)
    result = {}
    for name, source in expected.items():
        path = folder/name
        if path.read_text() != source:
            raise ValueError('GPIO HOLD generated source differs: ' + name)
        result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not standby and (folder/'completion.c').exists():
        raise ValueError('Awake GPIO HOLD profile unexpectedly has completion source')
    return dict(schema=1, source_sha256=result,
                release_sites=['error', 'success'] if standby else ['error'])


def _sequence(listing, binary, base, kind, *, pin="PA2"):
    """Check the actual linked bytes against explicit instruction semantics."""
    opcodes = LEGACY_STANDBY_OPCODES if pin == "PD7" else STANDBY_OPCODES
    pin_source("", pin)
    entries = list(re.finditer(r'^([0-9a-f]+) <([^>]+)>:', listing, re.M))
    labels = {m[2]: int(m[1], 16) for m in entries}
    names = ['gpio_hold_' + kind + suffix for suffix in ('_release', '_reassert', '_end')]
    wfi = 'status_led_sleep_idle' if kind == 'success' else 'gpio_hold_error_wfi'
    if any(n not in labels for n in [*names, wfi]):
        raise ValueError('Missing GPIO HOLD binary labels: ' + kind)
    if any(sum(m[2] == name for m in entries) != 1 for name in [*names, wfi]):
        raise ValueError('Duplicate GPIO HOLD binary labels: ' + kind)
    begin, reassert, end = (labels[n] for n in names)
    if not 0 <= begin-base < end-base <= len(binary):
        raise ValueError('GPIO HOLD labels lie outside linked binary: ' + kind)
    if (end-begin != len(opcodes) or labels[wfi] != begin+40 or
            reassert != begin+42 or binary[begin-base:end-base] != opcodes):
        raise ValueError('GPIO HOLD linked opcode group differs: ' + kind)
    instructions = []
    next_address = begin
    for line in listing.splitlines():
        m = re.match(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{4}\s+){1,2})\s*(.*)$', line)
        if not m or not begin <= int(m[1], 16) < end:
            continue
        address = int(m[1], 16)
        op = m[3].split(';', 1)[0].split('@', 1)[0].strip()
        op = re.sub(r'\s+', ' ', op).replace(', ', ',')
        encoded = b''.join(int(w,16).to_bytes(2,'little') for w in m[2].split())
        if address != next_address or binary[address-base:address-base+len(encoded)] != encoded:
            raise ValueError('GPIO HOLD listing does not bind contiguous binary bytes')
        instructions.append(op)
        next_address += len(encoded)
    expected = [
        'movw r0,#3072', 'movt r0,#22018',
        'ldr.w r1,[r0,#12]', 'bic.w r1,r1,#49152', 'str.w r1,[r0,#12]',
        'ldr.w r1,[r0]', 'bic.w r1,r1,#49152', 'str.w r1,[r0]',
        'dsb sy', 'isb sy', 'wfi', 'mov.w r1,#128', 'str.w r1,[r0,#24]',
        'ldr.w r1,[r0]', 'bic.w r1,r1,#49152', 'orr.w r1,r1,#16384',
        'str.w r1,[r0]', 'dsb sy',
    ]
    if pin == 'PA2':
        expected = [op.replace('#3072', '#0').replace('#49152', '#48').replace('#128', '#4').replace('#16384', '#16') for op in expected]
    # objdump can spell zero-offset loads/stores with an explicit #0.
    instructions = [s.replace('[r0,#0]','[r0]') for s in instructions]
    if instructions != expected or next_address != end or reassert != labels[wfi] + 2:
        raise ValueError('GPIO HOLD release/WFI/reassert instruction sequence differs: ' + kind + ': ' + repr(instructions))
    return dict(release=begin, wfi=labels[wfi], reassert=reassert, end=end,
                bytes=end-begin, sha256=hashlib.sha256(binary[begin-base:end-base]).hexdigest())


def audit_binary(folder, standby, *, pin="PA2"):
    folder = Path(folder)
    result = {'error': _sequence((folder/'staged/stage1.lst').read_text(),
                                (folder/'staged/stage1.bin').read_bytes(), 0x34180400, 'error', pin=pin)}
    if standby:
        result['success'] = _sequence((folder/'capture.lst').read_text(),
                                      (folder/'capture.bin').read_bytes(), 0x34300000, 'success', pin=pin)
    else:
        if 'gpio_hold_success_release' in (folder/'capture.lst').read_text():
            raise ValueError('Awake completion unexpectedly releases GPIO HOLD')
    return dict(schema=1, sites=result)
