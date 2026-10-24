"""Pure offline final-restoration proof rejection tests."""
import unittest
from archive_restore import ARCHIVE, V59_PREFIX, V60_PREFIX, load, verify_core, verify_park


class Tests(unittest.TestCase):
    def inputs(self):
        root = ARCHIVE/'final-restore'
        records = root/'records'
        return [
            (root/'inputs/v60-before.bin').read_bytes(),
            (root/'inputs/v59-original.bin').read_bytes(),
            (root/'inputs/following-before.bin').read_bytes(),
            (records/'restore-following/nor.bin').read_bytes(),
            (records/'restore-v59/readback.bin').read_bytes(),
            (records/'restore-read/nor.bin').read_bytes(),
            load(records/'restore-v59/request.json'), load(records/'restore-info/status.json'),
            load(records/'restore-v59/status.json'), load(records/'restore-v59/verified.json'),
            load(records/'restore-read/result.json'), load(records/'restore-following/result.json')]

    def test_real_exact_restore(self):
        verify_core(*self.inputs())

    def test_changed_code_or_following_bytes_refused(self):
        for index in range(6):
            args = self.inputs()
            args[index] = bytes([args[index][0] ^ 1])+args[index][1:]
            with self.subTest(input=index), self.assertRaises(ValueError): verify_core(*args)

    def test_failed_programming_or_crc_guard_refused(self):
        for index, field, value in ((7, 'result', 1), (8, 'result', 16),
                                   (8, 'cleanup_result', 1), (8, 'expected_current_crc', 0),
                                   (8, 'completed_mask', 0), (8, 'nor_status', 1)):
            args = self.inputs(); args[index][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): verify_core(*args)

    def test_wrong_current_desired_or_helper_refused(self):
        for field in ('helper_sha256', 'current_sha256', 'desired_sha256'):
            args = self.inputs(); args[6][field] = '0'*64
            with self.subTest(field=field), self.assertRaises(ValueError): verify_core(*args)

    def test_restored_recovery_is_exact(self):
        record = load(ARCHIVE/'final-restore/records/restored-park/result.json')
        verify_park(record, V59_PREFIX)
        with self.assertRaises(ValueError): verify_park(record, V60_PREFIX)
        record['context']['PC'] += 2
        with self.assertRaises(ValueError): verify_park(record, V59_PREFIX)


if __name__ == '__main__':
    unittest.main()
