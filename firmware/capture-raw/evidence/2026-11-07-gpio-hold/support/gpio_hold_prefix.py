"""Opt-in PD7 boot hook, leaving the historical UART guard at exact addresses.

The reset vector alone redirects ROM entry to a stackless fixed-location hook.
It asserts HOLD then enters the original reset handler; original startup,
recovery instructions, literal pool and the sensor loader remain byte-identical.
This is an offline transform/audit, never a hardware recovery allowlist.
"""
import hashlib
from pathlib import Path
import re
import struct

HERE = Path(__file__).resolve().parent
REFERENCE = HERE / 'evidence/2026-10-28-sensor-single-frame/flash-standby-v1/staged/stage1.bin'
REFERENCE_SHA = '6378483a91b560ffc6b31d74a9dd1205996a14c8030447ffddf7deddc9d23874'
BASE = 0x34180400
ENTRY = 0x34181E40
OLD_ENTRY = 0x34180440
CRC_OFFSETS = (0xC9C, 0x1358)
ERROR_BEGIN, ERROR_END = 0x1440, 0x1A40
# Reviewed GNU Arm 12.3.Rel1 output; see evidence/2026-11-07-gpio-hold.
# These are offline package identities, not permission to operate hardware.
# Unknown output is refused rather than making structure an identity waiver.
HOOK_SHA256 = 'c3b7aeb3f1919b556441d6369fd8bb5bdabbe7ad85ec3b3927b3eda2259e34db'
ERROR_SHA256 = '7082e54d435a68288d44979abd40aa18668dc436395dfa9e00e43cf517b72d94'
HOOK_BYTES = 76
HOOK_HEX = ('72b60f48082101600e4801680e4880218161416821f080014160'
            '816821f440418160c16821f44041c160016821f4404141f48041'
            '0160bff34f8ffef7e1ba00005c8a02565c820256000c0256')

ASSEMBLY = r'''/* GPIO HOLD executes before the original stack/VTOR startup.
 * Only r0/r1 are scratch; no SRAM, stack, FPU, IRQ or peripheral reset used.
 * Addresses/masks correspond to stm32n657xx.h secure RCC/GPIOD aliases. */
.syntax unified
.thumb
.section .gpio_hold_boot,"ax",%progbits
.global gpio_hold_boot
.type gpio_hold_boot,%function
.thumb_func
gpio_hold_boot:
    cpsid i
    ldr r0, =0x56028A5C /* RCC AHB4ENSR: atomic GPIOD clock enable */
    movs r1, #8
    str r1, [r0]
    ldr r0, =0x5602825C /* RCC AHB4ENR readback before GPIO access */
    ldr r1, [r0]
    ldr r0, =0x56020C00 /* GPIOD */
    movs r1, #128
    str r1, [r0, #24] /* BSRR: preload PD7 HIGH before changing mode */
    ldr r1, [r0, #4]
    bic.w r1, r1, #128
    str r1, [r0, #4] /* PD7 push-pull */
    ldr r1, [r0, #8]
    bic.w r1, r1, #0xC000
    str r1, [r0, #8] /* PD7 low speed */
    ldr r1, [r0, #12]
    bic.w r1, r1, #0xC000
    str r1, [r0, #12] /* PD7 no pulls */
    ldr r1, [r0]
    bic.w r1, r1, #0xC000
    orr.w r1, r1, #0x4000
    str r1, [r0] /* PD7 output; other pins preserved */
    dsb
    b.w Stage1_Reset_Handler
.size gpio_hold_boot, .-gpio_hold_boot
.ltorg
'''

LINK_SECTION = '''    .gpio_hold_boot 0x34181E40 : {
        KEEP(*(.gpio_hold_boot))
    } > PREFIX
    ASSERT(ADDR(.gpio_hold_boot) + SIZEOF(.gpio_hold_boot) <= 0x34182000,
           "GPIO HOLD hook overlaps stage-two NOR offset")
'''


def _once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('GPIO HOLD prefix anchor mismatch: ' + old[:70])
    return text.replace(old, new)


def prepare(folder):
    """Apply after the fixed error engine integration; return new source paths."""
    folder = Path(folder)
    assembly = folder / 'stage1.S'
    assembly.write_text(_once(assembly.read_text(),
        '    .word Stage1_Reset_Handler\n', '    .word gpio_hold_boot\n'), newline='\n')
    linker = folder / 'stage1.ld'
    text = linker.read_text()
    if '.error_text 0x34181840' not in text:
        raise ValueError('GPIO HOLD requires the reviewed fixed error-engine layout')
    linker.write_text(_once(text, '    .data :', LINK_SECTION + '    .data :'), newline='\n')
    path = folder / 'gpio_hold_boot.S'
    path.write_text(ASSEMBLY, newline='\n')
    return [path]


def check(folder, prefix):
    """Authenticate the exact hook/engine and every preserved prefix byte.

    Both unrelocated and relocated CRC words are admitted only if the two
    copies agree. The caller additionally binds their value to receiver CRC.
    """
    folder = Path(folder)
    reference = REFERENCE.read_bytes()
    if hashlib.sha256(reference).hexdigest() != REFERENCE_SHA:
        raise ValueError('GPIO HOLD prefix reference changed')
    if len(prefix) != ENTRY - BASE + HOOK_BYTES or not HOOK_BYTES:
        raise ValueError('Unreviewed GPIO HOLD prefix geometry')
    if (folder / 'gpio_hold_boot.S').read_text() != ASSEMBLY:
        raise ValueError('GPIO HOLD assembly source changed')
    if struct.unpack_from('<I', prefix, 4)[0] != ENTRY | 1:
        raise ValueError('GPIO HOLD is not the first ROM entry')
    if hashlib.sha256(prefix[ENTRY-BASE:]).hexdigest() != HOOK_SHA256:
        raise ValueError('Unreviewed GPIO HOLD boot instructions')
    if hashlib.sha256(prefix[ERROR_BEGIN:ERROR_END]).hexdigest() != ERROR_SHA256:
        raise ValueError('Unreviewed GPIO HOLD error-shutdown engine')
    if prefix[CRC_OFFSETS[0]:CRC_OFFSETS[0]+4] != prefix[CRC_OFFSETS[1]:CRC_OFFSETS[1]+4]:
        raise ValueError('GPIO HOLD receiver CRC copies differ')
    normalized = bytearray(prefix[:ERROR_BEGIN])
    normalized[4:8] = reference[4:8]
    for at in CRC_OFFSETS:
        normalized[at:at+4] = reference[at:at+4]
    if normalized != reference[:ERROR_BEGIN]:
        raise ValueError('GPIO HOLD changed existing startup/recovery/loader/bridge bytes')
    listing = (folder / 'stage1.lst').read_text()
    if not re.search(r'34180a76:.*\bbl\s+3418078c <recovery_gpio_park>', listing):
        raise ValueError('GPIO HOLD UART recovery branch changed')
    if not re.search(r'^34181e40 <gpio_hold_boot>:', listing, re.M):
        raise ValueError('GPIO HOLD entry symbol moved')
    literals = set()
    for line in listing.splitlines():
        m = re.match(r'([0-9a-f]+):.*\[pc,.*@\s*\(?([0-9a-f]+)', line)
        if m and 0x34180790 <= int(m[1],16) <= 0x34180A76:
            at = int(m[2],16) - BASE
            if not 0 <= at <= ERROR_BEGIN-4 or prefix[at:at+4] != reference[at:at+4]:
                raise ValueError('GPIO HOLD recovery literal changed')
            literals.add(at)
    if len(literals) != 20:
        raise ValueError('GPIO HOLD recovery literal set changed')
    return dict(schema=1, reference_sha256=REFERENCE_SHA, reset_vector_offset=4,
        entry=ENTRY, resume_entry=OLD_ENTRY, boot_bytes=HOOK_BYTES,
        boot_sha256=HOOK_SHA256, error_engine_sha256=ERROR_SHA256,
        startup_recovery_loader_bridge_equal=True,
        recovery_literal_offsets=sorted(literals),
        crc_literal_offsets=list(CRC_OFFSETS), early_load_bytes=15804,
        assertion_before_stack_and_uart=True, pin='PD7', header='Arduino D9 / CN14.2',
        mode='push-pull output', speed='low', pulls='none')
