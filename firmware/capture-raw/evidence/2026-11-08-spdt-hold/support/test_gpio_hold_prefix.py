"""Offline adversarial checks for the opt-in HOLD prefix boundary.

The baseline error-engine hash is temporarily used only in this synthetic unit
fixture to test prefix isolation without recompiling the separate shutdown
engine. Production builds authenticate the newly pinned error engine instead.
"""
import hashlib
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
        blob = bytearray(self.reference + bytes.fromhex(hold.HOOK_HEX))
        struct.pack_into('<I',blob,4,hold.ENTRY|1)
        listing = self.folder/'stage1.lst'
        listing.write_text(listing.read_text()+'\n34181e40 <gpio_hold_boot>:\n')
        return blob

    def checked(self, blob):
        original_engine = self.reference[hold.ERROR_BEGIN:hold.ERROR_END]
        with patch.object(hold,'ERROR_SHA256',hashlib.sha256(original_engine).hexdigest()):
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
        for changed in (blob[:-1],blob+b'\x00',self.reference):
            with self.subTest(length=len(changed)):
                with self.assertRaisesRegex(ValueError,'geometry'):self.checked(changed)

    def test_modified_hook_source_rejected_even_with_unchanged_binary(self):
        blob=self.fixture()
        path=self.folder/'gpio_hold_boot.S'
        path.write_text(path.read_text().replace('movs r1, #128','movs r1, #64'))
        with self.assertRaisesRegex(ValueError,'assembly source changed'):self.checked(blob)


if __name__=='__main__':unittest.main()
