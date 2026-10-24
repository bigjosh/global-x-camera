"""Offline layout, content, ownership and post-cleanup instruction checks."""
import hashlib
import json
from pathlib import Path
import re
import struct
import unittest

HERE=Path(__file__).resolve().parent
BUILDS=['native10-diagonal-v4','opaque8-diagonal-v4','opaque8-scene-v4']


class Artifacts(unittest.TestCase):
    def test_frozen_sources_and_layout(self):
        for name in BUILDS:
            with self.subTest(build=name):
                folder=HERE/name
                m=json.loads((folder/'manifest.json').read_text())
                raw=(folder/'capture.bin').read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(),m['binary_sha256'])
                self.assertEqual(len(raw),m['binary_bytes'])
                for f,digest in m['source_hashes'].items():
                    self.assertEqual(hashlib.sha256((folder/f).read_bytes()).hexdigest(),digest)
                self.assertEqual(struct.unpack_from('<II',raw),(m['stack'],m['entry']))
                self.assertEqual(m['data_start'],m['system_core_clock'])
                self.assertEqual(m['data_end']-m['data_start'],4)
                self.assertEqual(m['immutable_bytes'],m['data_start']-m['load'])
                self.assertEqual(m['data_end'],m['load']+len(raw))
                self.assertLessEqual(m['bss_end'],m['stack_floor'])
                self.assertLess(m['frame']+m['allocation_bytes']+32,m['load'])
                self.assertLess(m['stack'],m['request'])
                self.assertLess(m['request']+16,m['proof'])
                self.assertLess(m['proof']+160,0x34400000)
                for key in ['park','reject_park','failure_park']:
                    offset=m[key]-m['load']
                    self.assertEqual(raw[offset:offset+2],b'\xfe\xe7')

    def test_no_storage_executables(self):
        for name in BUILDS:
            symbols=(HERE/name/'symbols.txt').read_text()
            self.assertIsNone(re.search(r' [Tt] (photo_save_load|module_run|SDMMC2_IRQHandler|HAL_SD_\w+|BSP_XSPI_NOR_\w+)\b',symbols))

    def test_cleanup_has_no_fp_or_calls_after_control_clear(self):
        for name in BUILDS:
            listing=(HERE/name/'capture.lst').read_text()
            begin=listing.index('<raw_experiment_complete>:')
            end=listing.index('<raw_experiment_park>:',begin)
            part=listing[begin:end]
            clear=part.index('msr\tCONTROL, r0')
            tail=part[clear:]
            # A function call or FP instruction after owned FP state is cleared
            # would make the published integer-context proof insufficient.
            for line in tail.splitlines():
                instruction=re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f ]+\s+([a-z][a-z0-9.]*)\s',line)
                if instruction:
                    op=instruction[1]
                    self.assertFalse(op.startswith('v'),line)
                    self.assertNotIn(op,('bl','blx'),line)
            self.assertIn('isb',tail)
            self.assertIn('dsb',tail)


if __name__=='__main__':unittest.main()
