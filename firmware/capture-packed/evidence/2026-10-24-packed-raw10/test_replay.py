"""Offline archive-integrity and evidence-replay checks."""
import copy
import json
import unittest
from pathlib import Path

import replay


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = json.loads((Path(__file__).parent / 'index.json').read_bytes())

    def test_complete_archive(self):
        result = replay.run()
        self.assertTrue(result['passed'])
        self.assertEqual(result['scalar_test_vectors'], 4096)
        self.assertEqual(len(result['successful_trials']), 4)
        self.assertIn('native-pattern01', result['preserved_failed_trials'])

    def test_object_hash_mismatch(self):
        record = dict(self.index['tools']['analyze_raw.py'])
        record['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            replay.read_object(record)

    def test_object_length_mismatch(self):
        record = dict(self.index['tools']['analyze_raw.py'])
        record['bytes'] += 1
        with self.assertRaises(ValueError):
            replay.read_object(record)

    def test_path_escape(self):
        record = dict(self.index['tools']['analyze_raw.py'])
        record['path'] = '../outside.py'
        with self.assertRaises(ValueError):
            replay.read_object(record)

    def test_record_inventory_mismatch(self):
        record = copy.deepcopy(self.index['records']['packed-pattern01'])
        record['entries'].pop(next(iter(record['entries'])))
        with self.assertRaises(ValueError):
            replay.record_files(record)

    def test_record_member_hash_mismatch(self):
        record = copy.deepcopy(self.index['records']['packed-pattern01'])
        record['entries']['proof.json']['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            replay.record_files(record)

    def test_decompressed_hash_mismatch(self):
        record = copy.deepcopy(self.index['pattern_payloads']['packed-pattern01'])
        record['raw_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            replay.decompress_record(record)

    def test_decompressed_length_mismatch(self):
        record = copy.deepcopy(self.index['pattern_payloads']['packed-pattern01'])
        record['raw_bytes'] += 1
        with self.assertRaises(ValueError):
            replay.decompress_record(record)


if __name__ == '__main__':
    unittest.main()
