"""Hardware-free checks that failed captures cannot bypass maintenance guards."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch

import bench
import prepare_maintenance as maintenance


def fixture():
    code = bytes(32) + b'\xfe\xe7'
    approved = dict(raw_bytes=len(code), park_address=0x34300020,
                    phy_release_mode='late', raw_sha256=bench.sha(code))
    manifest = dict(raw_sha256=bench.sha(code), raw_bytes=len(code),
        vector_address='0x34300000', trace_address='0x343f0000', phy_release_mode='late',
        failure_recovery_schema=1, failure_park_symbol='late_failure_idle',
        failure_park_address='0x34300020', late_phy_status_schema=1,
        late_phy_status_address='0x343f8000', late_phy_status_words=1568,
        late_phy_header_words=32, late_phy_record_words=12, late_phy_max_records=128,
        parameters=dict(late_phy_experiment=True))
    trace = [0] * 64
    trace[:4] = [0x43545031, 0x80000094, 42, 0xFFFFFF9C]
    status = [0] * bench.LATE_PHY_WORDS
    status[0:3] = [0x4C505231, 0xF0000094, 1]
    status[6] = 1
    status[16:20] = [0x94, 0xFFFFFF9C, 1, 0x51554945]
    status[28:30] = [0x10, 0x14]
    context = dict(PC=0x34300020, XPSR=0x01000000, CONTROL=0, PRIMASK=1, FAULTMASK=0)
    return code, approved, manifest, trace, status, context


def mutable_clock_fixture():
    code, approved, manifest, trace, status, context = fixture()
    code += bytes(2) + struct.pack('<I', 64_000_000)
    approved.update(raw_bytes=len(code), raw_sha256=bench.sha(code),
                    system_core_clock_offset=len(code) - 4)
    manifest.update(raw_bytes=len(code), raw_sha256=bench.sha(code))
    return code, approved, manifest, trace, status, context


class MaintenanceGuardsTest(unittest.TestCase):
    def test_default_path_still_rejects_failed_capture_before_halt(self):
        _, _, _, trace, _, _ = fixture()
        fake = Mock()
        fake.upload.return_value = struct.pack('<64I', *trace)
        with patch.object(maintenance, 'Bench', return_value=fake), patch('sys.argv',
                ['prepare_maintenance.py', '--out', 'unused', '--layout', 'raw10']):
            with self.assertRaisesRegex(ValueError, 'completed capture'):
                maintenance.main()
        fake.call.assert_not_called()
        self.assertEqual(fake.upload.call_count, 1)

    def test_self_consistent_unapproved_build_never_reaches_hardware(self):
        code, _, manifest, _, _, _ = fixture()
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            (build / 'manifest.json').write_text(json.dumps(manifest))
            (build / 'capture.bin').write_bytes(code)
            with patch.object(maintenance, 'Bench') as make_bench, patch('sys.argv',
                    ['prepare_maintenance.py', '--out', 'unused', '--layout', 'raw10',
                     '--failed-phy-build', directory]):
                with self.assertRaisesRegex(ValueError, 'allowlist'):
                    maintenance.main()
            make_bench.assert_not_called()

    def test_allowlisted_binary_still_requires_exact_manifest_and_terminal_instruction(self):
        code, approved, manifest, _, _, _ = fixture()
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            path = build / 'manifest.json'
            path.write_text(json.dumps(manifest))
            (build / 'capture.bin').write_bytes(code)
            with patch.dict(maintenance.APPROVED_FAILED_PHY_BUILDS, {bench.sha(code): approved}):
                self.assertEqual(maintenance.checked_failed_phy_build(build)[1], code)
                for key, wrong in [('failure_park_address', '0x34300022'),
                                   ('failure_recovery_schema', True),
                                   ('phy_release_mode', 'early'),
                                   ('trace_address', '0x341f0000')]:
                    altered = dict(manifest, **{key: wrong})
                    path.write_text(json.dumps(altered))
                    with self.subTest(key=key), self.assertRaises(ValueError):
                        maintenance.checked_failed_phy_build(build)
                path.write_text(json.dumps(manifest))
                # A changed binary does not inherit approval from its manifest.
                (build / 'capture.bin').write_bytes(code[:-2] + b'\x00\xbf')
                with self.assertRaisesRegex(ValueError, 'allowlist'):
                    maintenance.checked_failed_phy_build(build)

    def test_stale_or_nonquiescent_failure_proof_is_rejected(self):
        _, approved, _, trace, status, _ = fixture()
        maintenance.validate_failed_phy_evidence(trace, status, 0x14, approved)
        cases = [('trace', 1, 40), ('trace', 1, 0xE1000011),
                 ('trace', 1, 0xFFFFFFFF), ('trace', 3, 1),
                 ('status', 16, 0), ('status', 16, 0x99), ('status', 17, 0),
                 ('status', 18, 0), ('status', 19, 0), ('status', 29, 0x10),
                 ('status', 28, 0x30), ('status', 6, 0), ('status', 2, 129),
                 ('status', 2, 0)]
        for group, index, value in cases:
            t, s = trace.copy(), status.copy()
            (t if group == 'trace' else s)[index] = value
            with self.subTest(group=group, index=index, value=value), self.assertRaises(ValueError):
                maintenance.validate_failed_phy_evidence(t, s, 0x14, approved)
        with self.assertRaisesRegex(ValueError, 'no longer live'):
            maintenance.validate_failed_phy_evidence(trace, status, 0x10, approved)

    def test_failed_context_is_exact_pc_irq_masked_privileged_thread(self):
        _, approved, _, _, _, context = fixture()
        maintenance.validate_context(context, approved)
        for key, value in [('PC', context['PC'] + 2), ('PRIMASK', 0),
                           ('XPSR', 0x01000003), ('XPSR', 0), ('CONTROL', 1), ('CONTROL', 2),
                           ('FAULTMASK', 1)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                maintenance.validate_context(dict(context, **{key: value}), approved)
        # Existing completed-capture handling permits FP ownership bits only.
        maintenance.validate_context(dict(context, CONTROL=0xC, PRIMASK=0))

    def test_live_code_mismatch_is_detected_without_a_mutating_call(self):
        code, approved, manifest, trace, status, _ = fixture()
        fake = Mock()
        fake.upload.side_effect = [struct.pack(f'<{len(status)}I', *status),
                                   struct.pack('<I', 0x14), bytes(len(code))]
        with self.assertRaisesRegex(ValueError, 'Live receiver bytes'):
            maintenance.read_failed_phy_proof(fake, trace, manifest, code, approved)
        fake.call.assert_not_called()

    def test_reviewed_runtime_clock_word_is_accepted_but_not_reported_as_exact_binary(self):
        code, approved, manifest, trace, status, _ = mutable_clock_fixture()
        present = code[:-4] + struct.pack('<I', 400_000_000)
        fake = Mock()
        fake.upload.side_effect = [struct.pack(f'<{len(status)}I', *status),
                                   struct.pack('<I', 0x14), present]
        proof = maintenance.read_failed_phy_proof(fake, trace, manifest, code, approved)
        self.assertFalse(proof['live_code_matches'])
        self.assertTrue(proof['live_immutable_code_matches'])
        self.assertEqual(proof['immutable_bytes'], len(code) - 4)
        self.assertEqual(proof['system_core_clock']['runtime_hz'], 400_000_000)
        fake.call.assert_not_called()

    def test_clock_exception_does_not_allow_changed_instructions_or_other_runtime_values(self):
        code, approved, _, _, _, _ = mutable_clock_fixture()
        good = code[:-4] + struct.pack('<I', 400_000_000)
        for index in (0, 32, len(code) - 5):
            bad = bytearray(good)
            bad[index] ^= 1
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, 'Live receiver bytes'):
                maintenance.validate_live_receiver(code, bytes(bad), approved)
        for value in (0, 64_000_000, 399_999_999, 400_000_001, 0xFFFFFFFF):
            with self.subTest(clock=value), self.assertRaisesRegex(ValueError, '400 MHz'):
                maintenance.validate_live_receiver(code, code[:-4] + struct.pack('<I', value), approved)
        for bad in (good[:-1], good + b'\0'):
            with self.assertRaisesRegex(ValueError, 'Live receiver bytes'):
                maintenance.validate_live_receiver(code, bad, approved)

    def test_clock_exception_requires_reviewed_final_aligned_word_and_initializer(self):
        code, approved, _, _, _, _ = mutable_clock_fixture()
        for offset in (0, len(code) - 8, len(code) - 3, True):
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, 'layout or initializer'):
                maintenance.checked_clock_offset(code, dict(approved, system_core_clock_offset=offset))
        with self.assertRaisesRegex(ValueError, 'layout or initializer'):
            maintenance.checked_clock_offset(code[:-4] + bytes(4), approved)
        strict = dict(approved)
        del strict['system_core_clock_offset']
        with self.assertRaisesRegex(ValueError, 'Live receiver bytes'):
            maintenance.validate_live_receiver(code, code[:-4] + struct.pack('<I', 400_000_000), strict)

    def test_no_dma_proof_checked_before_attempting_live_code_read(self):
        code, approved, manifest, trace, status, _ = fixture()
        fake = Mock()
        fake.upload.side_effect = [struct.pack(f'<{len(status)}I', *status),
                                   struct.pack('<I', 0x10)]
        with self.assertRaisesRegex(ValueError, 'no longer live'):
            maintenance.read_failed_phy_proof(fake, trace, manifest, code, approved)
        self.assertEqual(fake.upload.call_count, 2)
        fake.call.assert_not_called()


class LatePhyReaderTest(unittest.TestCase):
    def test_only_exact_reviewed_region_is_readable(self):
        _, _, manifest, _, _, _ = fixture()
        self.assertEqual(bench.late_phy_region(manifest), (0x343F8000, 1568))
        for key, value in [('late_phy_status_address', '0x34300000'),
                           ('late_phy_status_words', 2048), ('late_phy_status_words', -1),
                           ('late_phy_status_schema', True), ('late_phy_record_words', 13),
                           ('late_phy_max_records', 129)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                bench.late_phy_region(dict(manifest, **{key: value}))

    def test_invalid_count_preserves_raw_evidence_without_inventing_records(self):
        _, _, _, _, status, _ = fixture()
        status[32:44] = list(range(12))
        result = bench.decode_late_phy(struct.pack(f'<{len(status)}I', *status))
        self.assertTrue(result['late_phy_header_valid'])
        self.assertEqual(result['late_phy_snapshots'][0]['apb5rstr'], 11)
        status[2] = 129
        result = bench.decode_late_phy(struct.pack(f'<{len(status)}I', *status))
        self.assertFalse(result['late_phy_header_valid'])
        self.assertEqual(result['late_phy_snapshots'], [])
        self.assertEqual(result['late_phy_status_words'], status)

    def test_untrusted_diagnostic_layout_rejected_before_any_instrument_call(self):
        _, _, manifest, _, _, _ = fixture()
        manifest['late_phy_status_address'] = '0x50000000'
        fake = Mock()
        with self.assertRaises(ValueError):
            bench.inspect(fake, manifest, 0)
        fake.upload.assert_not_called()


if __name__ == '__main__':
    unittest.main()
