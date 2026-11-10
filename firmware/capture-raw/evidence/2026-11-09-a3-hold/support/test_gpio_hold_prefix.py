"""Offline adversarial checks for the opt-in HOLD prefix boundary.

The baseline error-engine hash is temporarily used only in this synthetic unit
fixture to test prefix isolation without recompiling the separate shutdown
engine. Production builds authenticate the newly pinned error engine instead.
"""
import hashlib
import os
import re
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import gpio_hold_prefix as hold


class GpioHoldPrefixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.reference = hold.REFERENCE.read_bytes()
        original_folder = hold.REFERENCE.parent
        for name in ('stage1.S', 'stage1.ld', 'stage1.lst'):
            (self.folder/name).write_text((original_folder/name).read_text())

    def tearDown(self):
        self.temp.cleanup()

    def prepared(self):
        before = (self.folder/'stage1.S').read_text()
        sources = hold.prepare(self.folder)
        self.assertEqual(sources, [self.folder/'gpio_hold_boot.S'])
        self.assertEqual((self.folder/'stage1.S').read_text().replace(
            '    .word gpio_hold_boot\n', '    .word Stage1_Reset_Handler\n'), before)
        return sources

    def fixture(self):
        self.prepared()
        blob = bytearray(self.reference)
        blob[hold.ENTRY-hold.BASE:hold.ENTRY-hold.BASE+hold.HOOK_BYTES] = bytes.fromhex(hold.HOOK_HEX)
        self.fixture_engine_hash = hashlib.sha256(blob[hold.ERROR_BEGIN:hold.ERROR_END]).hexdigest()
        struct.pack_into('<I',blob,4,hold.ENTRY|1)
        listing = self.folder/'stage1.lst'
        listing.write_text(listing.read_text()+f'\n{hold.ENTRY:08x} <gpio_hold_boot>:\n')
        return blob

    def checked(self, blob):
        with patch.object(hold,'ERROR_SHA256',self.fixture_engine_hash):
            return hold.check(self.folder,blob)

    def test_only_reset_vector_and_new_link_section_are_transformed(self):
        old_linker = (self.folder/'stage1.ld').read_text()
        self.prepared()
        self.assertEqual((self.folder/'stage1.ld').read_text().replace(hold.LINK_SECTION,''),old_linker)
        with self.assertRaisesRegex(ValueError,'anchor mismatch'):
            hold.prepare(self.folder)

    def test_first_entry_and_unchanged_recovery_boundary(self):
        result=self.checked(self.fixture())
        self.assertEqual(result['entry'],hold.ENTRY)
        self.assertEqual(result['resume_entry'],hold.OLD_ENTRY)
        self.assertTrue(result['assertion_before_stack_and_uart'])
        self.assertEqual(len(result['recovery_literal_offsets']),20)

    def test_every_critical_region_rejects_byte_corruption(self):
        blob=self.fixture()
        audit=self.checked(blob)
        offsets=[0,4,8,0x40,0x67A,0xA76,0xAFE,0x1390,0x1420,
                 hold.ERROR_BEGIN,hold.ERROR_END-1,hold.ENTRY-hold.BASE,len(blob)-1]
        offsets+=audit['recovery_literal_offsets']
        for offset in offsets:
            with self.subTest(offset=hex(offset)):
                changed=bytearray(blob);changed[offset]^=1
                with self.assertRaises(ValueError):self.checked(changed)

    def test_crc_relocation_changes_only_the_two_equal_literal_words(self):
        blob=self.fixture()
        for offset in hold.CRC_OFFSETS:struct.pack_into('<I',blob,offset,0x12345678)
        self.checked(blob)
        blob[hold.CRC_OFFSETS[1]]^=1
        with self.assertRaisesRegex(ValueError,'CRC copies differ'):self.checked(blob)

    def test_extra_unloaded_bytes_or_missing_hook_rejected(self):
        blob=self.fixture()
        for changed in (blob[:-1],blob+b'\x00'):
            with self.subTest(length=len(changed)):
                with self.assertRaisesRegex(ValueError,'geometry'):self.checked(changed)

    def test_modified_hook_source_rejected_even_with_unchanged_binary(self):
        blob=self.fixture()
        path=self.folder/'gpio_hold_boot.S'
        path.write_text(path.read_text().replace('movs r1, #4','movs r1, #64'))
        with self.assertRaisesRegex(ValueError,'assembly source changed'):self.checked(blob)


@unittest.skipUnless(os.environ.get('GPIO_HOLD_BUILD'), 'Linked PA2 candidate supplied by GPIO_HOLD_BUILD')
class EmbeddedHookIsolationTests(unittest.TestCase):
    def setUp(self):
        import error_build
        self.audit = error_build.audit_engine
        self.source = Path(os.environ['GPIO_HOLD_BUILD'])/'staged'
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        for name in ('stage1.lst', 'stage1.bin', 'symbols.txt'):
            (self.folder/name).write_bytes((self.source/name).read_bytes())

    def test_real_engine_remains_relocatable_and_cannot_enter_hook_padding(self):
        result = self.audit(self.folder)
        self.assertTrue(result['position_independent'])
        self.assertEqual(result['bytes'], 1536)
        path = self.folder/'stage1.lst'
        original = path.read_text()
        # Divert the first engine direct branch into the valid boot hook.
        before, engine = original.split('34181840 <error_signal_shutdown>:', 1)
        changed, count = re.subn(r'(\bb(?:\.[a-z]+)?\s+)[0-9a-f]{8}( <)',
                                r'\g<1>34181df0\2', engine, count=1)
        self.assertEqual(count, 1)
        path.write_text(before+'34181840 <error_signal_shutdown>:'+changed)
        with self.assertRaisesRegex(ValueError, 'branches outside'):
            self.audit(self.folder)

    def test_pc_relative_engine_reference_cannot_enter_hook(self):
        path=self.folder/'stage1.lst'
        original=path.read_text()
        before, engine=original.split('34181840 <error_signal_shutdown>:', 1)
        changed,count=re.subn(r'(@\s*\(?)[0-9a-f]{8}( <)',
                             r'\g<1>34181e30\2', engine, count=1)
        self.assertEqual(count, 1)
        path.write_text(before+'34181840 <error_signal_shutdown>:'+changed)
        with self.assertRaisesRegex(ValueError, 'PC dependency'):
            self.audit(self.folder)

    def test_fake_engine_end_and_changed_padding_or_hook_fail(self):
        path=self.folder/'symbols.txt'
        original=path.read_text()
        path.write_text(original.replace('34181dc8 T _error_engine_end',
                                         '34181df0 T _error_engine_end'))
        with self.assertRaisesRegex(ValueError, 'boundary differs'):
            self.audit(self.folder)
        path.write_text(original)
        binary=self.folder/'stage1.bin'; original=binary.read_bytes()
        for offset in (0x19D0, 0x19F0, 0x1A20):
            changed=bytearray(original);changed[offset]^=1;binary.write_bytes(changed)
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, 'padding'):
                self.audit(self.folder)


if __name__=='__main__':unittest.main()
