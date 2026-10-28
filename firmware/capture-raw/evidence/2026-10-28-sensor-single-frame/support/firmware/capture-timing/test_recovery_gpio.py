"""Offline regression checks for the guarded prefix's safety boundaries."""
import importlib.util
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('recovery_gpio_build',HERE/'recovery_gpio/build.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class RecoveryGpioBuildTests(unittest.TestCase):
    def setUp(self):
        # The shared source is used only as a representative complete prefix;
        # the builder itself requires the exact hash-pinned frozen v25 input.
        self.source=(HERE/'stage1.c').read_text()
        self.source=self.source.replace('    for (uint32_t i=0; i<64U; ++i) TRACE[i]=0;',
                                        '    raw10_memory_init();\n    for (uint32_t i=0; i<64U; ++i) TRACE[i]=0;')

    def test_guard_runs_before_expanded_sram_sensor_and_nor(self):
        transformed=builder.transform_stage1(self.source)
        positions=[transformed.index(marker) for marker in (
            '    recovery_gpio_begin();','    BSEC->DBGCR =',
            '    recovery_gpio_check();','    DWT->CYCCNT = 0;',
            '    raw10_memory_init();','    recovery_gpio_publish();',
            'int sensor_result =','x->AR=STAGE2_FLASH_OFFSET;')]
        self.assertEqual(positions,sorted(positions))
        self.assertIn('stage1_main(void)\n{\n    recovery_gpio_begin();',transformed)

    def test_transform_fails_closed_if_memory_hook_is_absent(self):
        with self.assertRaisesRegex(ValueError,'Frozen-source pattern mismatch'):
            builder.transform_stage1(self.source.replace('    raw10_memory_init();',''))

    def test_transform_fails_closed_if_debug_timer_anchor_is_ambiguous(self):
        with self.assertRaisesRegex(ValueError,'Frozen-source pattern mismatch'):
            builder.transform_stage1(self.source+'\n    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;')

    def test_transform_is_not_silently_reapplied(self):
        with self.assertRaises(ValueError):
            builder.transform_stage1(builder.transform_stage1(self.source))

    def test_composition_preserves_receiver_and_every_unoccupied_byte(self):
        original=bytes(range(256))*256
        boot=b'\x55'*5440
        combined=builder.compose_sector(original,boot)
        self.assertEqual(len(combined),65536)
        self.assertEqual(combined[:len(boot)],boot)
        self.assertEqual(combined[len(boot):],original[len(boot):])
        self.assertEqual(combined[0x2000:],original[0x2000:])

    def test_oversized_prefix_is_rejected(self):
        with self.assertRaises(ValueError):
            builder.compose_sector(bytes(65536),bytes(0x2001))

    def test_truncated_sector_is_rejected(self):
        with self.assertRaises(ValueError):
            builder.compose_sector(bytes(65535),bytes(5440))

    def test_unrecognized_base_cannot_be_relabeled_by_manifest(self):
        with self.assertRaisesRegex(ValueError,'exact known v25'):
            builder.validate_base(bytes(65536),bytes(32),
                                  {'program_sha256':builder.BASE_SHA256},{})

    def test_park_symbol_must_be_executable(self):
        with self.assertRaises(ValueError):
            builder.find_symbol('3418078c D recovery_gpio_park\n','recovery_gpio_park')
        self.assertEqual(builder.find_symbol('3418078c T recovery_gpio_park\n',
                                            'recovery_gpio_park'),0x3418078c)


if __name__=='__main__':
    unittest.main()
