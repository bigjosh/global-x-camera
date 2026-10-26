"""Offline adversarial checks for the evidence summarizer; no bench operations."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / 'firmware/capture-raw/evidence/2026-10-26-sd25-twenty/archive.py'
spec = importlib.util.spec_from_file_location('twenty_archiver_test', PATH)
archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)
SOURCE = Path(__file__).resolve().parent


class EvidenceChecks(unittest.TestCase):
    def test_real_proof_and_rejected_faults(self):
        m = archive.check_build(SOURCE / 'ram25-scene', 'ram25-scene')
        proof = archive.read(SOURCE / 'cycle01/capture/verified.json')
        archive.check_proof(proof, m, 1)
        for section, field, value in [
            ('proof', 'nonce', 1), ('proof', 'result', 14), ('proof', 'clock_hz', 12500000),
            ('proof', 'controller_owned', 1), ('proof', 'last_ready', 0xE00),
            ('proof', 'written_sectors', 3729), ('proof', 'dma_bytes', 1909599),
            ('card', 'clock_hz', 12500000), ('card', 'error', 8),
            ('card', 'cleanup_error', 17), ('card', 'timer_owned', 1),
        ]:
            altered = copy.deepcopy(proof)
            altered[section][field] = value
            with self.subTest(section=section, field=field), self.assertRaises(ValueError):
                archive.check_proof(altered, m, 1)
        altered = copy.deepcopy(proof)
        altered['card']['bus_width_proof']['configured_clkcr'] = 0x34006
        with self.assertRaises(ValueError):
            archive.check_proof(altered, m, 1)

    def test_incomplete_and_cleanup_records_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            f = root / 'cycle99/capture/incomplete.json'
            f.parent.mkdir(parents=True)
            f.write_text(json.dumps(dict(result=14, sd_error=14, cleanup_error=17)))
            attempts, failures, recovery = archive.observed_attempts(root)
            self.assertEqual(len(attempts), 1)
            self.assertFalse(attempts[0]['verified'])
            self.assertEqual(attempts[0]['result'], 14)
            self.assertEqual(attempts[0]['cleanup_error'], 17)
            self.assertEqual(failures, [])
            self.assertEqual(recovery, [])

    def test_frozen_manifest_detects_changes_and_unlisted_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'proof.json').write_bytes(b'{}\n')
            archive.write(root / 'SHA256SUMS.json', dict(schema=1, files=[dict(
                path='proof.json', bytes=3, sha256=archive.digest(b'{}\n'))]))
            self.assertTrue(archive.verify_bundle(root)['passed'])
            (root / 'proof.json').write_bytes(b'[]\n')
            with self.assertRaises(ValueError): archive.verify_bundle(root)
            (root / 'proof.json').write_bytes(b'{}\n')
            (root / 'unlisted.txt').write_bytes(b'x')
            with self.assertRaises(ValueError): archive.verify_bundle(root)


if __name__ == '__main__':
    unittest.main()
