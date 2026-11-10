"""Offline launch contract checks; do not import a hardware client."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def pure_functions():
    tree = ast.parse((HERE / 'console.py').read_text())
    names = {'checked_package', 'checked_idle_clocks', 'checked_pa2_hold'}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    ns = dict(hashlib=hashlib, json=json, struct=struct)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'pure-launch-contract', 'exec'), ns)
    return ns


class PackageLaunchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.functions = pure_functions()
        cls.current = ROOT / 'firmware/usb-ptp/evidence/2026-11-09-a3-hold/package-pa2'
        cls.manifest = json.loads((cls.current / 'manifest.json').read_text())
        cls.approved = {cls.manifest['prefix_sha256']: dict(
            bytes=cls.manifest['prefix_bytes'], sector=cls.manifest['sector0_sha256'])}

    def test_current_frozen_pair_and_real_early_hold_vector(self):
        result = self.functions['checked_package'](self.current, self.approved)
        self.assertEqual(result['prefix_sha256'], self.manifest['prefix_sha256'])
        self.assertTrue(result['pa2_hold'])
        with self.assertRaises(ValueError):
            self.functions['checked_package'](self.current, {})

    def test_rejects_forged_manifest_or_recovery_copy(self):
        with tempfile.TemporaryDirectory(prefix='control-package-check-') as tmp:
            folder = Path(tmp)
            for name in ('stage1.bin', 'sector0.bin', 'manifest.json'):
                shutil.copyfile(self.current / name, folder / name)
            shutil.copytree(self.current / 'recovery', folder / 'recovery')
            for relative in ('stage1.bin', 'sector0.bin', 'recovery/stage1.bin',
                             'recovery/capture_sector_0.bin'):
                target = folder / relative
                before = target.read_bytes(); bad = bytearray(before); bad[-1] ^= 1
                target.write_bytes(bad)
                with self.subTest(relative=relative), self.assertRaises(ValueError):
                    self.functions['checked_package'](folder, self.approved)
                target.write_bytes(before)
            for name, key in (('manifest.json', 'prefix_bytes'),
                              ('recovery/manifest.json', 'program_bytes')):
                target = folder / name; before = target.read_text(); m = json.loads(before)
                m[key] += 4; target.write_text(json.dumps(m))
                with self.subTest(manifest=name), self.assertRaises(ValueError):
                    self.functions['checked_package'](folder, self.approved)
                target.write_text(before)

    def test_idle_clock_guard_blocks_every_adc_usb_sd_camera_clock(self):
        base = [0] * 12
        base[4] = 0x2020  # early recovery owns NOR/XSPIM, not a card/client
        self.functions['checked_idle_clocks'](struct.pack('<12I', *base))
        for index, mask in ((0, 0x20), (4, 0x80), (4, 0x100), (4, 1 << 26),
                            (4, 1 << 27), (4, 1 << 28), (4, 1 << 29),
                            (11, 4), (11, 0x40)):
            values = base.copy(); values[index] |= mask
            with self.subTest(index=index, mask=mask), self.assertRaises(ValueError):
                self.functions['checked_idle_clocks'](struct.pack('<12I', *values))
        with self.assertRaises(ValueError):
            self.functions['checked_idle_clocks'](bytes(44))

    def test_hold_guard_requires_output_high_and_no_pull(self):
        good = [0x10, 0, 0, 0, 4, 4]
        self.functions['checked_pa2_hold'](struct.pack('<6I', *good))
        for index, value in ((0, 0), (0, 0x20), (0, 0x30), (1, 4),
                             (3, 0x10), (3, 0x20), (4, 0), (5, 0)):
            bad = good.copy(); bad[index] = value
            with self.subTest(index=index, value=value), self.assertRaises(ValueError):
                self.functions['checked_pa2_hold'](struct.pack('<6I', *bad))
        with self.assertRaises(ValueError):
            self.functions['checked_pa2_hold'](bytes(20))

    def test_prepare_keeps_guard_and_clock_checks_before_bridge_writes(self):
        source = (HERE / 'console.py').read_text()
        tree = ast.parse(source)
        prepare = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'prepare')
        text = ast.unparse(prepare)
        self.assertLess(text.index('early_guard(args, bridge)'), text.index("b.call('-halt', '-w'"))
        self.assertLess(text.index('checked_idle_clocks('), text.index("b.call('-halt', '-w'"))
        self.assertLess(text.index('checked_pa2_hold('), text.index("b.call('-halt', '-w'"))
        self.assertNotIn('APPROVED[', source)
        self.assertNotIn('APPROVED.update', source)


if __name__ == '__main__':
    unittest.main(verbosity=2)
