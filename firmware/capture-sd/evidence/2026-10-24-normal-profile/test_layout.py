"""Offline regression checks against actual archived proof headers."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('frozen_profile',
    ROOT / 'support/firmware/capture-sd/receiver_profile.py')
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


class LayoutTests(unittest.TestCase):
    def test_both_actual_builds(self):
        for variant in ('v64-normal-awake', 'v65-normal-standby'):
            with self.subTest(variant=variant):
                directory = ROOT / 'build' / variant / 'receiver'
                regions = profile.check_regions(directory / 'status_leds.h',
                                                directory / 'capture_profile.h')
                self.assertEqual(len(regions), 22)
                self.assertEqual(regions['LED'],
                    {'start': '0x343f89c0', 'end_exclusive': '0x343f8a40'})
                self.assertEqual(regions['RCP2'],
                    {'start': '0x343f8a80', 'end_exclusive': '0x343f8b00'})
                manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
                # Exactly the compiled header bounds, not an unrelated map.
                self.assertEqual(manifest['receiver_proof']['disjoint_proof_regions'], regions)

    def test_old_address_is_rejected(self):
        directory = ROOT / 'build/v64-normal-awake/receiver'
        with tempfile.TemporaryDirectory(prefix='old-rcp2-') as temp:
            path = Path(temp) / 'capture_profile.h'
            text = (directory / 'capture_profile.h').read_text(encoding='utf-8')
            path.write_text(text.replace('0x343F8A80U', '0x343F8A00U'), encoding='utf-8')
            with self.assertRaises(AssertionError):
                profile.check_regions(directory / 'status_leds.h', path)

    def test_expanded_led_header_is_rejected(self):
        directory = ROOT / 'build/v64-normal-awake/receiver'
        with tempfile.TemporaryDirectory(prefix='expanded-led-') as temp:
            path = Path(temp) / 'status_leds.h'
            text = (directory / 'status_leds.h').read_text(encoding='utf-8')
            path.write_text(text.replace('STATUS_LED_PROOF_WORDS 32U',
                                         'STATUS_LED_PROOF_WORDS 64U'), encoding='utf-8')
            with self.assertRaises(AssertionError):
                profile.check_regions(path, directory / 'capture_profile.h')

    def test_early_lifetimes_and_prefix_stack(self):
        regions = profile.check_early_regions()
        self.assertEqual(len(regions), 12)
        self.assertEqual(regions['PREFIX_STACK_RESERVED'],
                         {'start': '0x34182000', 'end_exclusive': '0x34188000'})
        self.assertTrue(any('never concurrent' in x['aliases'] for x in profile.LIFETIME_ALIASES))


if __name__ == '__main__': unittest.main()
