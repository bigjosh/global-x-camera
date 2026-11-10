"""Offline checks for the pin-only HOLD release and its linked-byte audit."""
from pathlib import Path
import os
import random
import re
import tempfile
import unittest

import gpio_hold_transform as hold


# Independent, reviewed disassembly fixture from the first offline candidate.
# Addresses are deliberately relocatable, as the error engine is copied to RAM.
OPS = [
    ('f640 4000', 'movw r0, #3072'),
    ('f2c5 6002', 'movt r0, #22018'),
    ('f8d0 100c', 'ldr.w r1, [r0, #12]'),
    ('f421 4140', 'bic.w r1, r1, #49152'),
    ('f8c0 100c', 'str.w r1, [r0, #12]'),
    ('f8d0 1000', 'ldr.w r1, [r0]'),
    ('f421 4140', 'bic.w r1, r1, #49152'),
    ('f8c0 1000', 'str.w r1, [r0]'),
    ('f3bf 8f4f', 'dsb sy'),
    ('f3bf 8f6f', 'isb sy'),
    ('bf30', 'wfi'),
    ('f04f 0180', 'mov.w r1, #128'),
    ('f8c0 1018', 'str.w r1, [r0, #24]'),
    ('f8d0 1000', 'ldr.w r1, [r0]'),
    ('f421 4140', 'bic.w r1, r1, #49152'),
    ('f441 4180', 'orr.w r1, r1, #16384'),
    ('f8c0 1000', 'str.w r1, [r0]'),
    ('f3bf 8f4f', 'dsb sy'),
]


def binary_fixture(kind, base=0x34180400):
    prefix = b'\x00' * 16
    address = base + len(prefix)
    lines = [f'{address:08x} <gpio_hold_{kind}_release>:']
    blob = bytearray(prefix)
    for index, (encoding, op) in enumerate(OPS):
        if index == 10:
            label = 'status_led_sleep_idle' if kind == 'success' else 'gpio_hold_error_wfi'
            lines.append(f'{address:08x} <{label}>:')
        if index == 11:
            lines.append(f'{address:08x} <gpio_hold_{kind}_reassert>:')
        lines.append(f'{address:08x}: {encoding:<10} {op}')
        encoded = b''.join(int(word, 16).to_bytes(2, 'little') for word in encoding.split())
        blob.extend(encoded)
        address += len(encoded)
    lines.append(f'{address:08x} <gpio_hold_{kind}_end>:')
    return '\n'.join(lines), bytes(blob)


class HoldSourceTests(unittest.TestCase):
    def setUp(self):
        self.error = (hold.HERE/'error_signal.c').read_text()
        self.completion = hold.canonical_completion()

    def test_contract_distinguishes_awake_success_from_error_standby(self):
        self.assertFalse(hold.contract(False)['success_release'])
        self.assertTrue(hold.contract(False)['error_release'])
        self.assertTrue(hold.contract(True)['success_release'])
        self.assertEqual(hold.contract(True)['shallow_fallback'], 'hold_high')
        self.assertTrue(hold.contract(True)['external_off_delay_required'])
        for invalid in (0, 1, None, 'true'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                hold.contract(invalid)

    def test_success_release_follows_proofs_and_precedes_return_handling(self):
        changed = hold.completion_source(self.completion)
        release = changed.index('"gpio_hold_success_release:')
        reassert = changed.index('"gpio_hold_success_reassert:')
        self.assertLess(changed.index('phase_gpio_emit(10U)'), release)
        self.assertLess(changed.index('publish(LPC_STATE_ARMED)'), release)
        self.assertLess(reassert, changed.index('publish(LPC_STATE_RETURNED)'))
        self.assertIn('RCC_AHB4ENSR_PWRENS | RCC_AHB4ENSR_GPIODENS', changed)
        self.assertIn('RCC->AHB4RSTR & RCC_AHB4RSTR_GPIODRST', changed)
        self.assertIn('#if LOW_POWER_MODE != 3', changed)
        self.assertNotIn(hold.SUCCESS_ANCHOR, changed)

    def test_error_refusals_skip_release_and_unexpected_return_reasserts(self):
        changed = hold.error_source(self.error)
        release = changed.index('"gpio_hold_error_release:')
        reassert = changed.index('"gpio_hold_error_reassert:')
        shallow = changed.index('\nshallow:')
        self.assertLess(changed.rindex('goto shallow;'), release)
        self.assertLess(changed.index('SCB->SCR |= SCB_SCR_SLEEPDEEP_Msk;'), release)
        self.assertLess(release, reassert)
        self.assertLess(reassert, shallow)
        self.assertIn('RCC->AHB4RSTR & RCC_AHB4RSTR_GPIODRST', changed)
        # Retain the exact fallback loop: it does not deliberately cut power
        # when the established AUX/Standby checks refuse the transition.
        self.assertIn('for (;;) { __DSB(); __WFI(); }', changed[shallow:])

    def test_transforms_fail_closed_on_changed_or_duplicate_anchors(self):
        for transform, text, anchor in (
            (hold.completion_source, self.completion, '#include "phase_gpio.h"'),
            (hold.error_source, self.error, '    __DSB(); __ISB(); __WFI();'),
        ):
            for invalid in (text.replace(anchor, ''), text+anchor, transform(text)):
                with self.subTest(transform=transform.__name__), self.assertRaises(ValueError):
                    transform(invalid)

    def test_generated_source_audit_checks_complete_files(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder/'staged').mkdir()
            error = folder/'staged/error_signal.c'
            error.write_text(hold.error_source(self.error))
            self.assertEqual(hold.audit_sources(folder, False)['release_sites'], ['error'])
            completion = folder/'completion.c'
            completion.write_text(hold.completion_source(self.completion))
            self.assertEqual(hold.audit_sources(folder, True)['release_sites'], ['error', 'success'])
            with self.assertRaisesRegex(ValueError, 'Awake'):
                hold.audit_sources(folder, False)
            # A harmless-looking extra statement anywhere must not be accepted
            # just because the release symbols still exist.
            completion.write_text(completion.read_text()+'\n/* edited */\n')
            with self.assertRaisesRegex(ValueError, 'completion.c'):
                hold.audit_sources(folder, True)

    def test_source_constants_match_the_reviewed_thumb_fixture(self):
        _, binary = binary_fixture('error')
        self.assertEqual(binary[16:], hold.STANDBY_OPCODES)
        for kind in ('error', 'success'):
            assembly = hold.standby_asm(kind)
            self.assertIn('"movw r0, #0x0c00', assembly)
            self.assertIn('"movt r0, #0x5602', assembly)
            self.assertNotIn('bl ', assembly)
            self.assertNotIn('=0x', assembly)
            self.assertEqual(assembly.count('"wfi\\n"'), 1)
        with self.assertRaises(ValueError):
            hold.standby_asm('other')

    def test_release_preserves_other_pins_and_return_restores_high(self):
        # Execute the emitted MMIO instruction subset, checking the pin contract
        # at WFI and after return for different surrounding GPIO configurations.
        assembly = hold.standby_asm('success')
        instructions = re.findall(r'^\s*"([^"\\]+)\\n"', assembly, re.M)
        randomizer = random.Random(0xD7)
        mask = 3 << 14
        for _ in range(64):
            original_mode = (randomizer.getrandbits(32) & ~mask) | (1 << 14)
            original_pull = randomizer.getrandbits(32)
            original_odr = randomizer.getrandbits(16) | 0x80
            memory = {0: original_mode, 12: original_pull, 20: original_odr}
            registers = {'r0': 0, 'r1': 0}
            states = []
            for instruction in instructions:
                if instruction.startswith('.') or instruction.endswith(':'):
                    continue
                if instruction == 'wfi':
                    states.append(dict(memory))
                    continue
                if instruction.startswith(('dsb ', 'isb ')):
                    continue
                move = re.fullmatch(r'(movw|movt|mov.w) (r[01]), #(0x[0-9a-f]+)', instruction)
                if move:
                    value = int(move[3], 16)
                    registers[move[2]] = ((registers[move[2]] & 0xFFFF) | (value << 16)
                                             if move[1] == 'movt' else value)
                    continue
                access = re.fullmatch(r'(ldr.w|str.w) r1, \[r0(?:, #(\d+))?\]', instruction)
                if access:
                    self.assertEqual(registers['r0'], 0x56020C00)
                    offset = int(access[2] or 0)
                    if access[1] == 'ldr.w':
                        registers['r1'] = memory[offset]
                    elif offset == 24:
                        memory[20] = (memory[20] | (registers['r1'] & 0xFFFF)) & ~(registers['r1'] >> 16)
                    else:
                        memory[offset] = registers['r1']
                    continue
                bitop = re.fullmatch(r'(bic.w|orr.w) r1, r1, #(0x[0-9a-f]+)', instruction)
                self.assertIsNotNone(bitop, instruction)
                value = int(bitop[2], 16)
                registers['r1'] = (registers['r1'] & ~value if bitop[1] == 'bic.w'
                                   else registers['r1'] | value)
            self.assertEqual(len(states), 1)
            self.assertEqual(states[0], {0: original_mode & ~mask,
                                         12: original_pull & ~mask, 20: original_odr})
            self.assertEqual(memory, {0: original_mode,
                                      12: original_pull & ~mask, 20: original_odr})


class HoldBinaryAuditTests(unittest.TestCase):
    def test_both_sites_are_position_independent(self):
        for kind in ('success', 'error'):
            for base in (0x34180400, 0x343C8000, 0x34300000):
                with self.subTest(kind=kind, base=base):
                    listing, binary = binary_fixture(kind, base)
                    result = hold._sequence(listing, binary, base, kind)
                    self.assertEqual(result['bytes'], 70)
                    self.assertEqual(result['reassert'], result['wfi']+2)

    def test_each_opcode_byte_is_bound_even_if_listing_is_spoofed(self):
        listing, binary = binary_fixture('error')
        for offset in range(16, len(binary)):
            bad = bytearray(binary)
            bad[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                hold._sequence(listing, bad, 0x34180400, 'error')

    def test_moved_wfi_or_reassert_label_is_rejected(self):
        listing, binary = binary_fixture('error')
        for label in ('gpio_hold_error_wfi', 'gpio_hold_error_reassert'):
            altered = re.sub(r'^[0-9a-f]+ <'+label+'>:', f'34180410 <{label}>:', listing, flags=re.M)
            with self.subTest(label=label), self.assertRaises(ValueError):
                hold._sequence(altered, binary, 0x34180400, 'error')

    def test_duplicate_missing_and_out_of_binary_labels_are_rejected(self):
        listing, binary = binary_fixture('error')
        for altered, base in (
            (listing+'\n34180410 <gpio_hold_error_release>:', 0x34180400),
            (listing.replace(' <gpio_hold_error_release>:', ' <missing>:'), 0x34180400),
            (listing, 0x34180420),
        ):
            with self.subTest(base=base), self.assertRaises(ValueError):
                hold._sequence(altered, binary, base, 'error')

    def test_wrong_mnemonic_or_noncontiguous_listing_is_rejected(self):
        listing, binary = binary_fixture('error')
        for altered in (listing.replace('wfi\n', 'nop\n'),
                        listing.replace('34180414:', '34180416:')):
            with self.assertRaises(ValueError):
                hold._sequence(altered, binary, 0x34180400, 'error')

    def test_full_binary_audit_awake_and_standby(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder/'staged').mkdir()
            listing, binary = binary_fixture('error')
            (folder/'staged/stage1.lst').write_text(listing)
            (folder/'staged/stage1.bin').write_bytes(binary)
            (folder/'capture.lst').write_text('')
            self.assertEqual(set(hold.audit_binary(folder, False)['sites']), {'error'})
            listing, binary = binary_fixture('success', 0x34300000)
            (folder/'capture.lst').write_text(listing)
            (folder/'capture.bin').write_bytes(binary)
            self.assertEqual(set(hold.audit_binary(folder, True)['sites']), {'error', 'success'})
            with self.assertRaisesRegex(ValueError, 'Awake'):
                hold.audit_binary(folder, False)

    @unittest.skipUnless(os.environ.get('GPIO_HOLD_BUILD'), 'Optional real build supplied by GPIO_HOLD_BUILD')
    def test_qualified_build_when_requested(self):
        folder = Path(os.environ['GPIO_HOLD_BUILD'])
        standby = (folder/'completion.c').exists()
        hold.audit_sources(folder, standby)
        hold.audit_binary(folder, standby)


if __name__ == '__main__':
    unittest.main()
