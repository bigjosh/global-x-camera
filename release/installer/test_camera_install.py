"""Offline installation orchestration tests. All device clients are mocked."""
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import camera_install as install
import camera_nor
import camera_recovery


OLD0, OLD1, NEIGHBOR = b'A' * 65536, b'B' * 65536, b'N' * 4096
NEW0, NEW1 = b'C' * 65536, b'D' * 65536


def profile_for_fake_flash():
    # Exact prefix identity is separately tested by test_camera_recovery.
    # This fixture gives the orchestrator distinct old/new sectors without
    # depending on historical files outside the portable bundle.
    return dict(id='test-old', prefix_sha256='test-prefix',
                sector0_sha256=install.sha(OLD0), sector1_sha256=install.sha(OLD1))


class FakeConsole:
    def __init__(self):
        self.messages = []

    def progress(self, percent, message):
        self.messages.append((percent, message))


class FakeLock:
    def __init__(self):
        self.phases = []

    def phase(self, phase):
        self.phases.append(phase)


class FakeNor:
    def __init__(self):
        self.memory = {0: OLD0, 65536: OLD1, 131072: NEIGHBOR}
        self.events = []
        self.read_count = {}
        self.fail = None
        self.corrupt_read = None
        self.before_write = None

    def read(self, offset):
        count = self.read_count.get(offset, 0) + 1
        self.read_count[offset] = count
        event = ('read', offset, count)
        self.events.append(event)
        if self.fail == event:
            raise camera_nor.NorError('simulated uncertain read')
        data = self.memory[offset]
        if self.corrupt_read == event:
            data = b'!' + data[1:]
        return data

    def write(self, offset, current, desired):
        event = ('write', offset)
        self.events.append(event)
        if self.before_write:
            self.before_write()
        if self.memory[offset] != current:
            raise AssertionError('Orchestrator supplied a stale current buffer')
        if self.fail == event:
            # The host must not assume whether a failing operation changed NOR.
            self.memory[offset] = desired[:256] + self.memory[offset][256:]
            raise camera_nor.NorError('simulated uncertain write')
        self.memory[offset] = desired


class ProgramTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)
        self.nor, self.console, self.lock = FakeNor(), FakeConsole(), FakeLock()

    def run_program(self):
        install.program_and_verify(None, self.nor, profile_for_fake_flash(),
                                   [NEW0, NEW1], self.out, self.console, self.lock)

    def test_all_backups_and_identity_saved_before_secondary_first_write(self):
        def check_durable_files():
            self.assertEqual((self.out / 'backup/sector0.bin').read_bytes(), OLD0)
            self.assertEqual((self.out / 'backup/sector1.bin').read_bytes(), OLD1)
            self.assertEqual((self.out / 'backup/following-4096.bin').read_bytes(), NEIGHBOR)
            metadata = json.loads((self.out / 'backup/identity.json').read_text())
            self.assertEqual(metadata['following_sha256'], install.sha(NEIGHBOR))
        self.nor.before_write = check_durable_files
        self.run_program()
        self.assertEqual(self.nor.events, [
            ('read', 0, 1), ('read', 65536, 1), ('read', 131072, 1),
            ('write', 65536), ('write', 0),
            ('read', 0, 2), ('read', 65536, 2), ('read', 131072, 2),
        ])
        self.assertEqual((self.out / 'verified-sector0.bin').read_bytes(), NEW0)
        self.assertEqual((self.out / 'verified-sector1.bin').read_bytes(), NEW1)
        self.assertEqual(self.lock.phases[-1], 'flash_verified')

    def test_wrong_existing_pair_never_writes_and_preserves_all_read_backups(self):
        self.nor.memory[0] = b'X' * 65536
        with self.assertRaisesRegex(ValueError, 'recognized firmware pair'):
            self.run_program()
        self.assertFalse(any(e[0] == 'write' for e in self.nor.events))
        self.assertEqual((self.out / 'backup/sector0.bin').read_bytes(), b'X' * 65536)
        self.assertEqual((self.out / 'backup/sector1.bin').read_bytes(), OLD1)
        self.assertEqual((self.out / 'backup/following-4096.bin').read_bytes(), NEIGHBOR)

    def test_secondary_failure_never_starts_primary_or_readback(self):
        self.nor.fail = ('write', 65536)
        with self.assertRaises(camera_nor.NorError):
            self.run_program()
        self.assertEqual(self.nor.events[-1], ('write', 65536))
        self.assertNotIn(('write', 0), self.nor.events)
        self.assertEqual(self.lock.phases[-1], 'writing_sector1')

    def test_primary_failure_never_replaces_running_helper_with_reader(self):
        self.nor.fail = ('write', 0)
        with self.assertRaises(camera_nor.NorError):
            self.run_program()
        self.assertEqual(self.nor.events[-1], ('write', 0))
        self.assertEqual(self.lock.phases[-1], 'writing_sector0')

    def test_first_backup_failure_never_reads_or_writes_again(self):
        self.nor.fail = ('read', 0, 1)
        with self.assertRaises(camera_nor.NorError):
            self.run_program()
        self.assertEqual(self.nor.events, [('read', 0, 1)])

    def test_independent_readback_mismatch_never_marks_flash_verified(self):
        self.nor.corrupt_read = ('read', 0, 2)
        with self.assertRaisesRegex(RuntimeError, 'independent verification failed'):
            self.run_program()
        self.assertEqual(self.nor.events[-1], ('read', 0, 2))
        self.assertNotIn('flash_verified', self.lock.phases)

    def test_neighbor_mismatch_never_marks_flash_verified(self):
        self.nor.corrupt_read = ('read', 131072, 2)
        with self.assertRaisesRegex(RuntimeError, 'following the firmware changed'):
            self.run_program()
        self.assertEqual(self.nor.events[-1], ('read', 131072, 2))
        self.assertNotIn('flash_verified', self.lock.phases)


class FakeTransport:
    def __init__(self, *args, **kwargs):
        self.halt_requests = 0
        self.default_timeout = 20
        self.events = []

    def log(self, event, **fields):
        self.events.append((event, fields))


class FakeStream:
    def __init__(self, port, log, max_duration):
        self.active = False
        self.closed = False
        self.checks = 0
        self.error = None

    def __enter__(self):
        self.active = True
        return self

    def __exit__(self, *args):
        self.active, self.closed = False, True

    def check(self):
        self.checks += 1
        if self.error:
            raise self.error


class FakeClock:
    def __init__(self):
        self.value = 0

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class RecoveryWaitTests(unittest.TestCase):
    def setUp(self):
        self.transport, self.console = FakeTransport(), FakeConsole()
        self.stream = FakeStream('port', None, 120)
        self.clock = FakeClock()

    def wait(self, verifier, seconds=2):
        with patch.object(camera_recovery, 'RecoveryStream', return_value=self.stream), \
                patch.object(camera_recovery, 'verify_park', side_effect=verifier), \
                patch.object(install.time, 'monotonic', self.clock.monotonic), \
                patch.object(install.time, 'sleep', self.clock.sleep), redirect_stdout(io.StringIO()):
            return install.wait_for_recovery(self.transport, 'port', install.ASSETS,
                                             self.console, seconds)

    def test_pre_halt_wait_is_retried_while_uart_active_then_stopped(self):
        calls = []
        def verify(transport, profiles):
            self.assertTrue(self.stream.active)
            self.assertEqual(transport.default_timeout, 5)
            calls.append('verify')
            if len(calls) == 1:
                raise ValueError('not yet powered')
            transport.halt_requests += 1
            return {'id': 'r2-knobs'}
        self.assertEqual(self.wait(verify), {'id': 'r2-knobs'})
        self.assertEqual(len(calls), 2)
        self.assertTrue(self.stream.closed)
        self.assertEqual(self.transport.default_timeout, 20)

    def test_post_halt_context_failure_is_not_retried(self):
        verifier = Mock()
        def fail(transport, profiles):
            transport.halt_requests += 1
            raise ValueError('wrong core context')
        verifier.side_effect = fail
        with self.assertRaisesRegex(ValueError, 'wrong core context'):
            self.wait(verifier)
        self.assertEqual(verifier.call_count, 1)
        self.assertTrue(self.stream.closed)
        self.assertEqual(self.transport.default_timeout, 20)

    def test_power_wait_times_out_without_reset(self):
        verifier = Mock(side_effect=RuntimeError('no target'))
        with patch.object(camera_recovery, 'request_recovery') as reset:
            with self.assertRaisesRegex(RuntimeError, 'No verified recovery'):
                self.wait(verifier, seconds=1)
        reset.assert_not_called()
        self.assertEqual(self.transport.halt_requests, 0)
        self.assertTrue(self.stream.closed)
        self.assertEqual(self.transport.default_timeout, 20)

    def test_stream_failure_stops_before_debugger_poll(self):
        self.stream.error = RuntimeError('serial disconnected')
        verifier = Mock()
        with self.assertRaisesRegex(RuntimeError, 'serial disconnected'):
            self.wait(verifier)
        verifier.assert_not_called()
        self.assertTrue(self.stream.closed)

    def test_restart_option_is_one_request_then_exact_verification(self):
        with patch.object(camera_recovery, 'request_recovery') as request, \
                patch.object(camera_recovery, 'verify_park', return_value={'id': 'd8-fixed'}) as verify:
            result = install.wait_for_recovery(self.transport, 'port', install.ASSETS,
                                               self.console, reset=True)
        request.assert_called_once_with('port', self.transport.log)
        verify.assert_called_once_with(self.transport, install.ASSETS / 'profiles')
        self.assertEqual(result['id'], 'd8-fixed')


class MainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / 'run'
        self.lock_dir = self.root / 'locks'
        self.transport, self.nor = FakeTransport(), FakeNor()
        self.profile = profile_for_fake_flash()
        self.post_profile = {'id': 'r2-knobs', 'prefix_sha256':
            'b866589cf472cac9820d961f3243cb8280759614826083757fae374ccee7e242'}
        self.request, self.reset = Mock(), Mock()
        self.wait_failure = None
        self.post_failure = None

    def run_main(self, extra_args=()):
        real_lock = install.SessionLock
        def lock(serial, output):
            return real_lock(serial, output, root=self.lock_dir)
        def wait(*args):
            if self.wait_failure:
                if self.wait_failure == 'after-halt':
                    self.transport.halt_requests += 1
                raise ValueError('recovery failed')
            self.transport.halt_requests += 1
            return self.profile
        verifier = Mock(return_value=self.post_profile, side_effect=self.post_failure)
        with ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules, {'serial': SimpleNamespace()}))
            stack.enter_context(patch.object(install, 'validate_assets', return_value=[NEW0, NEW1]))
            stack.enter_context(patch.object(install, 'find_cube', return_value=Path('fake-cli')))
            stack.enter_context(patch.object(install, 'choose_probe', return_value=('ST123', 'PORT')))
            stack.enter_context(patch.object(install, 'Transport', return_value=self.transport))
            stack.enter_context(patch.object(install, 'SessionLock', side_effect=lock))
            stack.enter_context(patch.object(install, 'wait_for_recovery', side_effect=wait))
            stack.enter_context(patch.object(camera_nor, 'Nor', return_value=self.nor))
            stack.enter_context(patch.object(camera_recovery, 'request_recovery', self.request))
            stack.enter_context(patch.object(camera_recovery, 'normal_reset', self.reset))
            stack.enter_context(patch.object(camera_recovery, 'verify_park', verifier))
            stack.enter_context(redirect_stdout(io.StringIO()))
            stack.enter_context(redirect_stderr(io.StringIO()))
            return install.main(['--non-interactive', '--confirm-idle', '--output', str(self.output)]
                                + list(extra_args))

    def test_complete_install_verifies_recovers_then_resets_and_unlocks(self):
        self.assertEqual(self.run_main(), 0)
        self.request.assert_called_once()
        self.reset.assert_called_once()
        self.assertFalse((self.lock_dir / 'ST123.json').exists())
        complete = json.loads((self.output / 'complete.json').read_text())
        self.assertTrue(complete['independent_readbacks_match'])
        self.assertTrue(complete['following_4096_unchanged'])
        self.assertTrue(complete['post_install_uart_recovery'])
        self.assertFalse(complete['normal_usb_operation_tested'])

    def test_unknown_write_completion_keeps_lock_and_never_restarts(self):
        self.nor.fail = ('write', 65536)
        self.assertEqual(self.run_main(), 1)
        self.request.assert_not_called()
        self.reset.assert_not_called()
        state = json.loads((self.lock_dir / 'ST123.json').read_text())
        self.assertEqual(state['phase'], 'writing_sector1')
        self.assertEqual(self.nor.events[-1], ('write', 65536))
        self.assertFalse((self.output / 'complete.json').exists())

    def test_readback_failure_keeps_lock_and_never_restarts(self):
        self.nor.corrupt_read = ('read', 131072, 2)
        self.assertEqual(self.run_main(), 1)
        self.request.assert_not_called()
        self.reset.assert_not_called()
        self.assertTrue((self.lock_dir / 'ST123.json').exists())

    def test_post_install_recovery_failure_never_releases_normal_reset(self):
        self.post_failure = ValueError('no exact recovery')
        self.assertEqual(self.run_main(), 1)
        self.request.assert_called_once()
        self.reset.assert_not_called()
        self.assertTrue((self.lock_dir / 'ST123.json').exists())
        self.assertFalse((self.output / 'complete.json').exists())

    def test_post_install_wrong_identity_never_releases_normal_reset(self):
        self.post_profile['prefix_sha256'] = 'b1b032c7ae48e68a8942922b9a6a2d8e57983030a331b1d5b590c01ee3571c52'
        self.assertEqual(self.run_main(), 1)
        self.reset.assert_not_called()
        self.assertTrue((self.lock_dir / 'ST123.json').exists())

    def test_initial_wait_without_halt_releases_unused_lock(self):
        self.wait_failure = 'before-halt'
        self.assertEqual(self.run_main(), 1)
        self.request.assert_not_called()
        self.reset.assert_not_called()
        self.assertFalse((self.lock_dir / 'ST123.json').exists())
        self.assertFalse(self.nor.events)

    def test_initial_context_failure_after_halt_keeps_lock(self):
        self.wait_failure = 'after-halt'
        self.assertEqual(self.run_main(), 1)
        self.request.assert_not_called()
        self.reset.assert_not_called()
        self.assertTrue((self.lock_dir / 'ST123.json').exists())
        self.assertFalse(self.nor.events)

    def test_restart_request_failure_before_halt_keeps_lock(self):
        self.wait_failure = 'before-halt'
        self.assertEqual(self.run_main(['--restart']), 1)
        self.assertEqual(self.transport.halt_requests, 0)
        self.reset.assert_not_called()
        self.assertFalse(self.nor.events)
        state = json.loads((self.lock_dir / 'ST123.json').read_text())
        self.assertEqual(state['phase'], 'recovery_reset_requested')

    def test_existing_lock_stops_before_recovery_or_nor_access(self):
        install.SessionLock('ST123', self.root / 'previous', root=self.lock_dir)
        self.assertEqual(self.run_main(), 1)
        self.assertEqual(self.transport.halt_requests, 0)
        self.assertFalse(self.nor.events)
        self.request.assert_not_called()
        self.reset.assert_not_called()


class TransportTests(unittest.TestCase):
    def test_timeout_reaps_only_cli_and_does_not_send_another_command(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = install.Transport('fake-cli', 'ST123', directory)
            with patch.object(install.subprocess, 'run', side_effect=
                              subprocess.TimeoutExpired(['fake-cli'], 5, output=b'partial')) as run:
                with self.assertRaisesRegex(RuntimeError, 'may still be executing'):
                    transport.call('-u', '0x341B4100', '224', 'status.bin')
            run.assert_called_once()
            self.assertEqual(transport.halt_requests, 0)
            self.assertEqual((Path(directory) / 'cli-0001.log').read_bytes(), b'partial')
            args = run.call_args.args[0]
            self.assertIn('mode=HOTPLUG', args)
            self.assertIn('ap=1', args)
            self.assertNotIn('-el', args)
            self.assertNotIn('-rst', args)


if __name__ == '__main__':
    unittest.main()
