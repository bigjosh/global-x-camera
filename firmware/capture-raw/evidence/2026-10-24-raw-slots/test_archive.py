"""Offline evidence identity/extraction regressions; never import bench code."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import archive
import materialize
import replay


class ArchiveTests(unittest.TestCase):
    def test_complete_replay_preserves_failure(self):
        result = replay.run()
        self.assertTrue(result['passed'])
        self.assertGreaterEqual(result['source_builds_verified'], 4)
        self.assertEqual(result['line_immediate_snapshot_bytes'], 10240)
        self.assertEqual(result['preserved_payload_failures'][0]['mismatched_bytes'], 1909600)
        self.assertEqual(result['full_format_slots'], 32834)

    def test_exact_bytes_dedup_tamper_and_length(self):
        old_archive, old_replay = archive.HERE, replay.HERE
        try:
            with tempfile.TemporaryDirectory() as temporary:
                archive.HERE = replay.HERE = Path(temporary)
                for raw in (b'a\r\nb\nc\r\n', b'\0'*100000, bytes(range(256))):
                    item = archive.put(raw)
                    self.assertEqual(archive.put(raw), item)
                    self.assertEqual(replay.read_object(item), raw)
                    wrong = dict(item, bytes=item['bytes']+1)
                    with self.assertRaises(ValueError):
                        replay.read_object(wrong)
                    path = archive.HERE / item['path']
                    original = path.read_bytes()
                    path.write_bytes(original + b'!')
                    with self.assertRaises(ValueError):
                        replay.read_object(item)
                    path.write_bytes(original)
        finally:
            archive.HERE, replay.HERE = old_archive, old_replay

    def test_extract_new_folder_only_and_path_bounds(self):
        with tempfile.TemporaryDirectory() as temporary:
            dest = Path(temporary)/'out'
            materialize.write_files(dest, {'nested/source.c':b'x\r\ny\n'})
            self.assertEqual((dest/'nested/source.c').read_bytes(), b'x\r\ny\n')
            with self.assertRaises(FileExistsError):
                materialize.write_files(dest, {'source.c':b'new'})
            for name in ('../escape', '/absolute', 'C:/absolute', 'folder\\escape'):
                with self.assertRaises(ValueError):
                    materialize.write_files(Path(temporary)/'bad', {name:b'bad'})
            self.assertFalse((Path(temporary)/'bad').exists())

    def test_non_pattern_selection_never_keeps_pixel_names(self):
        index = json.loads((HERE/'index.json').read_bytes())
        for record in index['records'].values():
            if record['pixels'] != 'pattern':
                for name,item in record['files'].items():
                    if archive.is_pixels(Path(name).name):
                        self.assertIn(name,record.get('metadata_sectors',[]))
                        self.assertTrue(archive.is_metadata_sector(replay.read_object(item)))

    def test_attachments_are_bounded_text_inside_repository(self):
        old_root, old_archive, old_replay = archive.ROOT, archive.HERE, replay.HERE
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive.ROOT = root
                archive.HERE = replay.HERE = root/'archive'
                folder = root/'record'
                folder.mkdir()
                source = root/'failure.log'
                source.write_bytes(b'Error\r\noriginal bytes\n')
                selected = dict(classification='failure', pixels='omit',
                                attachments={'failure.log':str(source)})
                result = archive.collect_record(folder, selected)
                self.assertEqual(replay.read_object(result['files']['attachments/failure.log']),
                                 source.read_bytes())
                for name in ('../escape', '/absolute', 'C:drive', 'folder\\escape'):
                    with self.assertRaises(ValueError):
                        archive.collect_record(folder, dict(selected, attachments={name:str(source)}))
                binary = root/'scene.bin'
                binary.write_bytes(b'pixels')
                with self.assertRaises(ValueError):
                    archive.collect_record(folder, dict(selected, attachments={'scene.bin':str(binary)}))
                source.write_bytes(b'x'*(4*1024*1024+1))
                with self.assertRaises(ValueError):
                    archive.collect_record(folder, selected)
                with self.assertRaises(ValueError):
                    archive.root_path(root.parent/'outside.log')
        finally:
            archive.ROOT, archive.HERE, replay.HERE = old_root, old_archive, old_replay


if __name__ == '__main__':
    unittest.main()
