"""HOLD artifact binding tests; semantic auditors have their own binary tests.

These synthetic packages exercise detached/partial manifests and changed
artifacts without instruments, compiler execution, or writable bench state.
"""
import copy
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

from test_gpio_hold_bench import NORMAL
from gpio_hold_transform import contract
from test_inspect_flash import f


class GPIOHoldPackageBinding(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name);(self.folder/'staged').mkdir()
        spec=importlib.util.spec_from_file_location('hold_test_header',
            f.ROOT/'firmware/boot-timing/add_boot_header.py')
        self.header=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.header)
        self.code=bytes(16000)
        self.prefix=bytearray(0x1400)
        struct.pack_into('<II',self.prefix,0,0x34188000,0x34180441)
        self.crc_offsets=(0xC9C,0x1358)
        for offset in self.crc_offsets:struct.pack_into('<I',self.prefix,offset,zlib.crc32(self.code[:15804]))
        (self.folder/'completion.c').write_text('canonical completion\n')
        (self.folder/'staged/error_signal.c').write_text('canonical error\n')
        completion=f.sha((self.folder/'completion.c').read_bytes())
        error=f.sha((self.folder/'staged/error_signal.c').read_bytes())
        self.m=json.loads(NORMAL.read_text())
        self.m.update(gpio_hold=True,gpio_hold_contract=contract(True),
            binary_sha256=f.sha(self.code),binary_bytes=len(self.code),
            source_hashes={'completion.c':completion})
        self.m['flags'].append('-DRAW_GPIO_HOLD=1')
        self.source_audit=dict(schema=1,source_sha256={'completion.c':completion,
            'staged/error_signal.c':error},release_sites=['error','success'])
        self.binary_audit=dict(schema=1,sites={'error':{'bytes':70},'success':{'bytes':70}})
        self.prefix_audit=dict(schema=1,assertion_before_stack_and_uart=True)
        self.p=dict(compile_flags=['-DRAW_GPIO_HOLD=1'],sources={'staged/error_signal.c':error},
            gpio_hold_source_audit=copy.deepcopy(self.source_audit),
            gpio_hold_binary_audit=copy.deepcopy(self.binary_audit),
            gpio_hold_prefix_audit=copy.deepcopy(self.prefix_audit))
        self.transform=SimpleNamespace(contract=contract,audit_sources=lambda folder,standby:self.source_audit,
            audit_binary=lambda folder,standby:self.binary_audit)
        self.prefix_checker=SimpleNamespace(CRC_OFFSETS=self.crc_offsets,
            check=lambda folder,prefix:self.prefix_audit)
        self.addCleanup(patch.stopall)
        patch.object(f,'_gpio_hold_auditor',side_effect=lambda name:
            self.transform if name=='gpio_hold_transform' else self.prefix_checker).start()
        self.seal()

    def seal(self):
        """Rebind hashes after a deliberate fixture change, not after corruption."""
        (self.folder/'capture.bin').write_bytes(self.code)
        (self.folder/'manifest.json').write_text(json.dumps(self.m))
        boot=self.header.make_image(self.prefix)
        sector=bytearray(b'\xff'*65536)
        sector[:len(boot)]=boot;sector[0x2000:0x2000+len(self.code)]=self.code
        (self.folder/'staged/stage1.bin').write_bytes(self.prefix)
        (self.folder/'staged/stage1_boot.bin').write_bytes(boot)
        (self.folder/'staged/capture_sector_0.bin').write_bytes(sector)
        self.p.update(raw_slots=copy.deepcopy(self.m),stage1_raw_sha256=f.sha(self.prefix),
            stage1_raw_bytes=len(self.prefix),stage2_full_sha256=f.sha(self.code),
            stage2_full_bytes=len(self.code),program_sha256=f.sha(sector),
            stage2_manifest_sha256=f.sha((self.folder/'manifest.json').read_bytes()))

    def audit(self):return f.gpio_hold_artifacts(self.folder,self.m,self.p,self.code)

    def test_complete_package_recomputes_all_three_audits(self):
        result=self.audit()
        self.assertEqual(result['runtime'],self.source_audit)
        self.assertEqual(result['binary'],self.binary_audit)
        self.assertEqual(result['prefix'],self.prefix_audit)
        self.assertIn('no live GPIO',result['scope'])

    def test_absent_or_detached_audit_is_rejected(self):
        for field in ('gpio_hold_source_audit','gpio_hold_binary_audit','gpio_hold_prefix_audit'):
            original=self.p[field]
            for value in (None,{'schema':99}):
                self.p[field]=value
                with self.subTest(field=field,value=value),self.assertRaises(ValueError):self.audit()
            self.p[field]=original

    def test_prefix_and_receiver_cannot_select_different_hold_profiles(self):
        for change in ({'compile_flags':[]},{'compile_flags':['-DRAW_GPIO_HOLD=1']*2},
                {'raw_slots':dict(self.m,gpio_hold=False)}):
            before=copy.deepcopy(self.p);self.p.update(change)
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'selections differ'):self.audit()
            self.p=before

    def test_changed_frozen_source_fails_even_when_semantic_auditor_is_still_valid(self):
        path=self.folder/'completion.c';old=path.read_bytes();path.write_bytes(old+b'changed')
        with self.assertRaisesRegex(ValueError,'frozen receiver source changed'):self.audit()
        path.write_bytes(old)
        path=self.folder/'staged/error_signal.c';path.write_bytes(path.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'frozen prefix source changed'):self.audit()

    def test_canonical_sources_must_also_be_bound_in_compile_manifests(self):
        del self.m['source_hashes']['completion.c'];self.seal()
        with self.assertRaisesRegex(ValueError,'completion source is not bound'):self.audit()
        self.m['source_hashes']['completion.c']=self.source_audit['source_sha256']['completion.c']
        self.p['sources']={};self.seal()
        with self.assertRaisesRegex(ValueError,'shutdown source is not bound'):self.audit()

    def test_changed_receiver_or_manifest_cannot_use_old_binding(self):
        path=self.folder/'capture.bin';path.write_bytes(b'\x01'+self.code[1:])
        with self.assertRaisesRegex(ValueError,'receiver identity differs'):self.audit()
        self.seal()
        (self.folder/'manifest.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'packaged prefix/receiver binding differs'):self.audit()

    def test_two_equal_crc_words_still_must_identify_actual_early_receiver(self):
        for offset in self.crc_offsets:struct.pack_into('<I',self.prefix,offset,0x12345678)
        self.seal()
        with self.assertRaisesRegex(ValueError,'CRC literals'):self.audit()

    def test_boot_image_cannot_be_detached_from_audited_raw_prefix(self):
        boot=bytearray((self.folder/'staged/stage1_boot.bin').read_bytes());boot[-1]^=1
        (self.folder/'staged/stage1_boot.bin').write_bytes(boot)
        sector=bytearray((self.folder/'staged/capture_sector_0.bin').read_bytes());sector[:len(boot)]=boot
        (self.folder/'staged/capture_sector_0.bin').write_bytes(sector)
        self.p['program_sha256']=f.sha(sector)
        with self.assertRaisesRegex(ValueError,'packaged prefix/receiver binding differs'):self.audit()

    def test_legacy_package_needs_no_hold_auditor_but_rejects_stray_audit(self):
        with patch.object(f,'_gpio_hold_auditor',side_effect=AssertionError('unnecessary HOLD import')):
            self.assertIsNone(f.gpio_hold_artifacts(self.folder,{},{}))
            for key in ('gpio_hold_source_audit','gpio_hold_binary_audit','gpio_hold_prefix_audit'):
                with self.subTest(key=key),self.assertRaisesRegex(ValueError,'Unexpected GPIO HOLD'):
                    f.gpio_hold_artifacts(self.folder,{},{key:{}})


if __name__=='__main__':unittest.main()
