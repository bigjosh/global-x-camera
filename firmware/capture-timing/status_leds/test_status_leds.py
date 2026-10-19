"""Meaningful negative tests for phase evidence and startup invariants."""
import copy
import importlib.util
from pathlib import Path
import struct
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build import PROOF_FIELDS, led_manifest, transform_capture, transform_prefix
spec = importlib.util.spec_from_file_location('led_inspect', HERE/'inspect.py')
inspection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspection)


class ProofTests(unittest.TestCase):
    def setUp(self):
        self.manifest = dict(status_leds=led_manifest(), stage2_sha256='test-receiver')
        self.words = dict.fromkeys(PROOF_FIELDS, 0)
        self.words.update(magic=0x4C454431, schema=1, words=32, phase=0, sleep_state=1,
                          moder=0x110001, ahb4enr=64, primask=1)
        for phase, cycles, level in [('red', 1, 0x101), ('blue', 11, 0x401),
                                      ('off', 31, 0x501), ('sleep', 51, 0x501)]:
            self.words[f'{phase}_cycle'] = cycles
            self.words[f'{phase}_odr'] = level | (1 << 15)  # Other GPIO bits ignored.
            self.words[f'{phase}_idr'] = level
        self.capture = dict(build_sha256='test-receiver', completed=True, image_integrity_matches=True,
            errors=0, camera_error=0,
            events=[dict(id=i, cycles=t) for i, t in [(22, 5), (50, 10), (51, 20),
                                                      (30, 30), (31, 40), (40, 50)]])

    def raw(self):
        return struct.pack('<32I', *(self.words[k] for k in PROOF_FIELDS))

    def test_good_sequence_does_not_claim_physical_sleep(self):
        result = inspection.decode(self.raw(), self.manifest, self.capture)
        self.assertTrue(result['valid'])
        self.assertTrue(result['first_exposure_capture_checked'])
        self.assertFalse(result['cpu_sleep_observed'])

    def test_active_green_or_wrong_pin_level_rejected(self):
        self.words['blue_idr'] &= ~1
        with self.assertRaisesRegex(ValueError, 'blue IDR'):
            inspection.decode(self.raw(), self.manifest)

    def test_later_exposure_cannot_masquerade_as_first(self):
        self.capture['events'].insert(3, dict(id=50, cycles=25))
        with self.assertRaisesRegex(ValueError, 'first recorded STROBE'):
            inspection.decode(self.raw(), self.manifest, self.capture)

    def test_timestamp_from_wrong_callback_rejected(self):
        self.words['blue_cycle'] = 21
        with self.assertRaisesRegex(ValueError, 'first exposure marker'):
            inspection.decode(self.raw(), self.manifest, self.capture)

    def test_wrong_capture_identity_rejected(self):
        self.capture['build_sha256'] = 'old-image'
        with self.assertRaisesRegex(ValueError, 'another receiver'):
            inspection.decode(self.raw(), self.manifest, self.capture)

    def test_irq_sleep_or_error_regressions_rejected(self):
        for field, value in [('systick_ctrl', 1), ('nvic_pending_or', 1),
                             ('nvic_enable_or', 1), ('primask', 0), ('scr', 4),
                             ('icsr', 1 << 28), ('error_cycle', 100)]:
            with self.subTest(field=field):
                old = self.words[field]
                self.words[field] = value
                with self.assertRaises(ValueError):
                    inspection.decode(self.raw(), self.manifest)
                self.words[field] = old


class FrozenHooks(unittest.TestCase):
    def test_missing_hook_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'pattern mismatch'):
            transform_capture('#include <stdarg.h>\nvoid changed_api(void) {}')

    def test_early_hook_never_precedes_memory_with_proof(self):
        text = ('#include "recovery_gpio.h"\nvoid stage1_main(void)\n{\n'
                '    recovery_gpio_begin();\n    raw10_memory_init();\n'
                '    recovery_gpio_publish();\n}')
        transformed = transform_prefix(text)
        self.assertLess(transformed.index('status_led_boot_begin();'),
                        transformed.index('recovery_gpio_begin();'))
        self.assertGreater(transformed.index('status_led_proof_init();'),
                           transformed.index('raw10_memory_init();'))


if __name__ == '__main__':
    unittest.main()
