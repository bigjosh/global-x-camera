"""Offline failure-path checks; no instrument driver or capture API is imported.

Run with the Python used for the isolated Joulescope dependencies:
  python -m unittest discover -s firmware/boot-timing/tests -v
"""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HELPERS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HELPERS))
sys.path.insert(0, str(HELPERS.parents[1] / 'tmp/bringup/joulescope-deps'))
import numpy as np

import capture_cycle
import js110_session as session


def packet(sample_id=100, values=(1.0, 2.0), decimation=1):
    return {'sample_id': sample_id, 'sample_rate': 2000000,
            'decimate_factor': decimation, 'utc': 100 << 30,
            'data': np.array(values, dtype=np.float32)}


class StreamCoverageTests(unittest.TestCase):
    def record(self, packets):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stream.jsonl'
            stream = session.StreamLog(path)
            for signal, value in packets:
                stream.receive('u/js110/fake/' + signal, value)
            status = stream.close()
            records = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertFalse(stream.thread.is_alive())
            self.assertEqual(records[-1]['event'], 'stream_stop')
            self.assertEqual(records[-1]['coverage'], status['coverage'])
            return status, records

    def test_no_samples_does_not_pass_coverage_but_preserves_legacy_flag(self):
        status, _ = self.record([])
        self.assertTrue(status['complete'])
        self.assertIn('logging_only', status['complete_scope'])
        self.assertFalse(status['coverage']['passed'])
        self.assertFalse(status['coverage']['checks']['current_samples_present'])
        self.assertFalse(status['coverage']['checks']['voltage_samples_present'])

    def test_empty_or_missing_signal_does_not_pass(self):
        for voltage_packets in ([], [('s/v/!data', packet(values=()))]):
            with self.subTest(voltage_packets=len(voltage_packets)):
                status, _ = self.record([('s/i/!data', packet())] + voltage_packets)
                self.assertTrue(status['complete'])
                self.assertFalse(status['coverage']['passed'])
                self.assertFalse(status['coverage']['checks']['voltage_samples_present'])

    def test_contiguous_decimated_streams_pass_and_keep_nonfinite_warning(self):
        status, records = self.record([
            ('s/i/!data', packet(values=(1.0, float('nan')), decimation=4)),
            ('s/v/!data', packet(decimation=4)),
            ('s/i/!data', packet(sample_id=108, decimation=4)),
            ('s/v/!data', packet(sample_id=108, decimation=4))])
        self.assertTrue(status['complete'])
        self.assertTrue(status['coverage']['passed'])
        current = status['coverage']['signals']['current']
        self.assertEqual(current['samples'], 4)
        self.assertEqual(current['last_sample_id_end_exclusive'], 116)
        self.assertEqual(current['nonfinite_samples'], 1)
        self.assertEqual(records[3]['gap_native_samples'], 0)

    def test_gap_and_counter_reset_fail_coverage_without_relabeling_logging(self):
        for next_id, missing, overlaps in ((105, 3, 0), (99, 0, 1)):
            with self.subTest(next_id=next_id):
                status, _ = self.record([
                    ('s/i/!data', packet()), ('s/v/!data', packet()),
                    ('s/i/!data', packet(sample_id=next_id))])
                self.assertTrue(status['complete'])
                self.assertFalse(status['coverage']['passed'])
                current = status['coverage']['signals']['current']
                self.assertEqual(current['discontinuities'], 1)
                self.assertEqual(current['missing_native_samples'], missing)
                self.assertEqual(current['overlap_or_reset_events'], overlaps)

    def test_worker_write_failure_is_reported_and_thread_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            stream = session.StreamLog(Path(directory) / 'stream.jsonl')
            original_write = stream._write

            def fail_chunk(record):
                if record['event'] == 'stream_chunk':
                    raise OSError('simulated full disk')
                original_write(record)

            stream._write = fail_chunk
            stream.receive('s/i/!data', packet())
            status = stream.close()
            self.assertFalse(status['complete'])
            self.assertIn('simulated full disk', status['error'])
            self.assertFalse(stream.thread.is_alive())


class FakeDriver:
    """In-memory settings and callbacks only; never imports the real driver."""
    initial = {session.RANGE_TOPIC: 128, 's/sstats/ctrl': 0, 's/v/range/select': 0,
               'h/fs': 1000000, 's/i/ctrl': 0, 's/v/ctrl': 0}

    def __init__(self, packets, fail_restore=None):
        self.settings = dict(self.initial)
        self.packets = packets
        self.fail_restore = fail_restore
        self.commands = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def device_paths(self):
        return ['u/js110/fake']

    def open(self, device, mode, timeout):
        if device != 'u/js110/fake' or mode != 'restore':
            raise AssertionError('Unexpected device or open mode')
        return self

    def query(self, topic, timeout):
        return self.settings[topic]

    def publish(self, topic, value, timeout):
        self.commands.append((topic, value))
        if topic == self.fail_restore and value == self.initial[topic]:
            raise RuntimeError('simulated restore failure')
        self.settings[topic] = value

    def subscribe(self, topic, flags, callback):
        for suffix, value in self.packets:
            if topic == 'u/js110/fake/' + suffix:
                callback(topic, value)

    def unsubscribe(self, topic, callback, timeout):
        pass


class SessionRestorationTests(unittest.TestCase):
    def run_fake_session(self, packets, fail_restore=None):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            args = SimpleNamespace(device='u/js110/fake', duration=5,
                control=folder/'control.json', response=folder/'response.json',
                log=folder/'session.jsonl', stream_log=folder/'stream.jsonl')
            driver = FakeDriver(packets, fail_restore)
            original_emit = session.Reporter.emit

            def command_after_response(reporter, event, **values):
                original_emit(reporter, event, **values)
                if event == 'ready':
                    args.control.write_text(json.dumps({'id': 'range', 'state': '2A'}))
                elif event == 'response' and values.get('id') == 'range':
                    args.control.write_text(json.dumps({'id': 'stop', 'state': 'stop'}))

            with patch.object(session.Reporter, 'emit', command_after_response), redirect_stdout(io.StringIO()):
                code = session.run_session(args, lambda: driver, 'fake')
            final = json.loads(args.response.read_text())
            log = [json.loads(line) for line in args.log.read_text().splitlines()]
            return code, driver, final, log

    def test_missing_signal_fails_session_after_restoring_all_settings(self):
        code, driver, final, _ = self.run_fake_session([('s/i/!data', packet())])
        self.assertEqual(code, 1)
        self.assertFalse(final['ok'])
        self.assertTrue(final['stream']['complete'])
        self.assertFalse(final['stream']['coverage']['passed'])
        self.assertIn((session.RANGE_TOPIC, 2), driver.commands)
        self.assertEqual(driver.settings, driver.initial)

    def test_continuous_signals_pass_and_restore_all_settings(self):
        code, driver, final, _ = self.run_fake_session([
            ('s/i/!data', packet()), ('s/v/!data', packet())])
        self.assertEqual(code, 0)
        self.assertTrue(final['ok'])
        self.assertEqual(driver.settings, driver.initial)

    def test_restore_failure_does_not_prevent_remaining_restoration(self):
        code, driver, final, log = self.run_fake_session([
            ('s/i/!data', packet()), ('s/v/!data', packet())], fail_restore='s/i/ctrl')
        self.assertEqual(code, 1)
        self.assertFalse(final['ok'])
        for topic, value in driver.initial.items():
            if topic != 's/i/ctrl':
                self.assertEqual(driver.settings[topic], value)
        self.assertTrue(any(record['event'] == 'stream_restore_error' for record in log))


class CaptureFailureTests(unittest.TestCase):
    def exercise(self, cycle_code=0, inspection_code=0, capture_code=0,
                 cycle_exception=None, wait_timeout=False, cycle_interrupt=False):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'capture'
            calls = []

            class FakeCapture:
                returncode = None

                def __init__(self, argv, **kwargs):
                    calls.append(('capture', argv))
                    output.mkdir()
                    (output/'started').touch()

                def poll(self):
                    return self.returncode

                def wait(self, timeout):
                    if not (output/'stop').exists():
                        raise AssertionError('Must request capture stop before waiting')
                    calls.append(('wait', timeout))
                    if wait_timeout:
                        raise subprocess.TimeoutExpired('fake-capture', timeout)
                    self.returncode = capture_code
                    return self.returncode

            class FakeCycle:
                returncode = None
                pid = 12345
                interrupted = False

                def __init__(self, argv, **kwargs):
                    self.args = argv
                    calls.append(('cycle_once.py', argv))

                def poll(self):
                    return self.returncode

                def wait(self, timeout):
                    if cycle_interrupt and not self.interrupted:
                        self.interrupted = True
                        raise KeyboardInterrupt('simulated interruption while OFF')
                    if cycle_exception is not None:
                        raise cycle_exception
                    if self.interrupted:
                        calls.append(('cycle_restored', self.args))
                    self.returncode = cycle_code
                    return self.returncode

                def kill(self):
                    raise AssertionError('Must not kill a power-control child')

            def fake_popen(argv, **kwargs):
                if Path(argv[1]).name == 'cycle_once.py':
                    return FakeCycle(argv, **kwargs)
                return FakeCapture(argv, **kwargs)

            def fake_run(argv, **kwargs):
                name = Path(argv[1]).name
                calls.append((name, argv))
                if name != 'inspect_cycle.py':
                    raise AssertionError('Unexpected subprocess')
                (output/'independent-review.json').write_text(json.dumps(
                    {'passed': inspection_code == 0}))
                return subprocess.CompletedProcess(argv, inspection_code)

            error = None
            with patch.object(capture_cycle.subprocess, 'Popen', fake_popen), \
                 patch.object(capture_cycle.subprocess, 'run', fake_run), \
                 patch.object(capture_cycle.time, 'sleep'):
                try:
                    capture_cycle.main([str(output), '--control', str(Path(directory)/'control'),
                        '--response', str(Path(directory)/'response'), '--ch5-signal', 'main-vddio'])
                except RuntimeError as exc:
                    error = exc
            return json.loads((output/'cycle-outcome.json').read_text()), calls, error

    def test_cycle_failure_still_inspects_after_capture_finishes(self):
        outcome, calls, error = self.exercise(cycle_code=1)
        self.assertIsNotNone(error)
        self.assertFalse(outcome['passed'])
        self.assertEqual(outcome['inspection_status'], 'passed')
        self.assertEqual([item['stage'] for item in outcome['errors']], ['cycle'])
        self.assertEqual([name for name, _ in calls],
                         ['capture', 'cycle_once.py', 'wait', 'inspect_cycle.py'])
        for name, argv in calls:
            if name != 'wait':
                self.assertEqual(argv[0], sys.executable)
                self.assertTrue(Path(argv[1]).is_absolute())

    def test_command_and_inspection_failures_are_both_retained(self):
        outcome, _, error = self.exercise(cycle_code=1, inspection_code=1)
        self.assertIsNotNone(error)
        self.assertEqual(outcome['inspection_status'], 'failed')
        self.assertEqual([item['stage'] for item in outcome['errors']], ['cycle', 'inspection'])

    def test_cycle_timeout_still_inspects_saved_capture(self):
        outcome, _, error = self.exercise(cycle_exception=TimeoutError('no restore response'))
        self.assertIsNotNone(error)
        self.assertEqual(outcome['inspection_status'], 'passed')
        self.assertEqual(outcome['errors'][0]['message'], 'no restore response')
        self.assertEqual(outcome['cycle_status'], 'still_running_after_wait')
        self.assertEqual(outcome['cycle_pid'], 12345)

    def test_interrupt_waits_for_restoration_before_stopping_capture(self):
        outcome, calls, error = self.exercise(cycle_interrupt=True)
        self.assertIsNotNone(error)
        self.assertEqual(outcome['cycle_status'], 'finished')
        self.assertEqual(outcome['cycle_returncode'], 0)
        self.assertFalse(outcome['passed'])
        self.assertEqual([item['stage'] for item in outcome['errors']], ['cycle_interrupted'])
        order = [name for name, _ in calls]
        self.assertLess(order.index('cycle_restored'), order.index('wait'))
        self.assertEqual(outcome['inspection_status'], 'passed')

    def test_export_failure_still_inspects_and_records_both_failures(self):
        outcome, _, error = self.exercise(capture_code=1, inspection_code=1)
        self.assertIsNotNone(error)
        self.assertEqual([item['stage'] for item in outcome['errors']],
                         ['capture_export', 'inspection'])

    def test_unfinished_capture_is_not_inspected_or_terminated(self):
        outcome, calls, error = self.exercise(wait_timeout=True)
        self.assertIsNotNone(error)
        self.assertEqual(outcome['inspection_status'], 'skipped_capture_still_running')
        self.assertNotIn('inspect_cycle.py', [name for name, _ in calls])

    def test_success_requires_all_three_stages_to_pass(self):
        outcome, _, error = self.exercise()
        self.assertIsNone(error)
        self.assertTrue(outcome['passed'])
        self.assertEqual(outcome['inspection_status'], 'passed')


class CycleWaitTests(unittest.TestCase):
    def test_interrupt_preserves_real_fake_child_finally(self):
        """A local child emulates OFF/ON with a file, never an instrument."""
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'fake-power-state'
            code = ('import pathlib,sys,time\n'
                    'state=pathlib.Path(sys.argv[1])\n'
                    'try:\n'
                    ' state.write_text("off")\n'
                    ' time.sleep(0.5)\n'
                    'finally:\n'
                    ' state.write_text("on")\n')
            child = subprocess.Popen([sys.executable, '-c', code, str(state)],
                                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

            class InterruptDuringOff:
                args = child.args
                injected = False

                def wait(self, timeout):
                    if not self.injected:
                        deadline = time.monotonic() + 5
                        while not state.exists() and time.monotonic() < deadline:
                            time.sleep(0.01)
                        if not state.exists():
                            raise AssertionError('Fake child did not reach OFF')
                        self.injected = True
                        raise KeyboardInterrupt('simulated interruption while OFF')
                    return child.wait(timeout=timeout)

                def kill(self):
                    raise AssertionError('Must not kill a power-control child')

            interruptions = []
            try:
                result = capture_cycle.wait_for_cycle(InterruptDuringOff(), 10,
                                                       interruptions.append)
                self.assertEqual(result, 0)
                self.assertEqual(state.read_text(), 'on')
                self.assertEqual(len(interruptions), 1)
            finally:
                # The local fake is bounded. Let its finally finish even if a
                # test assertion fails; no instrument or real power is touched.
                child.wait(timeout=10)

    def test_deadline_reports_child_without_killing_it(self):
        class StillRunning:
            args = ['fake-cycle-child']
            waits = 0

            def wait(self, timeout):
                self.waits += 1
                raise subprocess.TimeoutExpired(self.args, timeout)

            def kill(self):
                raise AssertionError('Must leave restoration-capable child running')

        child = StillRunning()
        with patch.object(capture_cycle.time, 'monotonic', side_effect=[0, 0, 2]):
            with self.assertRaises(subprocess.TimeoutExpired):
                capture_cycle.wait_for_cycle(child, 1, lambda exc: None)
        self.assertEqual(child.waits, 1)


if __name__ == '__main__':
    unittest.main()
