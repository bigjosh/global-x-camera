"""Recovery output ownership/failure checks. Never imports an instrument API."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import js110_session as session


class FakeDriver:
    def __init__(self, initial=None, failures=None):
        self.initial = {
            session.RANGE_TOPIC: 128, 's/sstats/ctrl': 0, 's/v/range/select': 0,
            session.EXTIO_TOPIC: 3300, session.GPO_TOPICS[0]: 0, session.GPO_TOPICS[1]: 1,
            's/gpi/0/ctrl': 0, 's/gpi/1/ctrl': 0, 's/i/lsb_src': 0, 's/v/lsb_src': 0}
        self.initial.update(initial or {})
        self.settings = dict(self.initial)
        self.failures = failures or {}
        self.counts = {}
        self.commands = []
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def device_paths(self):
        return ['u/js110/fake']

    def open(self, path, mode, timeout):
        assert path == 'u/js110/fake' and mode == 'restore'
        return self

    def query(self, topic, timeout):
        self.queries.append(topic)
        return self.settings[topic]

    def publish(self, topic, value, timeout):
        self.commands.append((topic, value))
        key = (topic, value)
        self.counts[key] = self.counts.get(key, 0) + 1
        # Simulate the difficult case: the device changed but USB reported an
        # error afterward. A successful return is not required for restoration.
        self.settings[topic] = value
        if self.failures.get(key) == self.counts[key]:
            raise RuntimeError('simulated publish error after device changed')

    def subscribe(self, *args):
        pass

    def unsubscribe(self, *args, **kwargs):
        pass


class RecoverySessionTests(unittest.TestCase):
    def exercise(self, commands=(), *, enabled=True, initial=None, failures=None,
                 inject_interrupt=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = SimpleNamespace(device='u/js110/fake', duration=5,
                control=root/'control.json', response=root/'response.json',
                log=root/'log.jsonl', recovery_output=enabled, stream_log=None)
            driver = FakeDriver(initial, failures)
            requests = iter([dict(request, id=str(i)) for i, request in enumerate([
                *commands, {'state': 'stop'}])])
            original_emit = session.Reporter.emit

            def next_command(reporter, event, **values):
                original_emit(reporter, event, **values)
                if event == 'response' and values.get('state') == 'recovery' and inject_interrupt:
                    raise KeyboardInterrupt('simulated Ctrl-C after asserted recovery')
                if event == 'ready' or (event == 'response' and values.get('state') != 'stop'):
                    request = next(requests, None)
                    if request is not None:
                        args.control.write_text(json.dumps(request))

            with patch.object(session.Reporter, 'emit', next_command), redirect_stdout(io.StringIO()):
                code = session.run_session(args, lambda: driver, 'offline-fake')
            records = [json.loads(line) for line in args.log.read_text().splitlines()]
            return code, driver, records, json.loads(args.response.read_text())

    def assert_other_output_untouched(self, driver):
        self.assertFalse(any(topic == session.GPO_TOPICS[1] for topic, _ in driver.commands))
        self.assertEqual(driver.settings[session.GPO_TOPICS[1]], driver.initial[session.GPO_TOPICS[1]])

    def test_legacy_does_not_access_gpio_and_rejects_recovery(self):
        code, driver, records, final = self.exercise([
            {'state': 'recovery', 'asserted': True}, {'state': 'query'}], enabled=False)
        self.assertEqual(code, 0)
        self.assertTrue(final['ok'])
        self.assertTrue(all('gpo' not in topic and 'extio' not in topic for topic in driver.queries))
        self.assertTrue(all('gpo' not in topic and 'extio' not in topic for topic, _ in driver.commands))
        response = next(item for item in records if item.get('id') == '0')
        self.assertFalse(response['ok'])
        self.assertIn('--recovery-output', response['error'])
        self.assertNotIn('recovery_output', final)

    def test_assert_release_and_query_never_change_power_or_other_output(self):
        code, driver, records, final = self.exercise([
            {'state': 'recovery', 'asserted': True}, {'state': 'query'},
            {'state': 'recovery', 'asserted': False}])
        self.assertEqual(code, 0)
        responses = [item for item in records if item['event'] == 'response']
        self.assertTrue(responses[0]['recovery_output']['asserted'])
        self.assertTrue(responses[1]['recovery_output']['asserted'])
        self.assertFalse(responses[2]['recovery_output']['asserted'])
        self.assertTrue(all(item['range'] == 128 for item in responses))
        self.assertEqual([command for command in driver.commands if command[0] == session.RANGE_TOPIC],
                         [(session.RANGE_TOPIC, 128)])  # final restoration only
        self.assertFalse(any(topic == session.EXTIO_TOPIC for topic, _ in driver.commands))
        self.assertEqual(driver.settings, driver.initial)
        self.assertEqual(final['recovery_output']['gpo1'], 1)
        self.assertEqual(final['recovery_output']['extio_voltage_mv'], 3300)
        self.assert_other_output_untouched(driver)

    def test_strict_boolean_rejects_numbers_strings_containers_and_missing(self):
        bad = [None, 0, 1, 'true', [], {}]
        code, driver, records, _ = self.exercise([
            *({'state': 'recovery', 'asserted': value} for value in bad), {'state': 'recovery'}])
        self.assertEqual(code, 0)
        rejected = [item for item in records if item['event'] == 'response' and not item['ok']]
        self.assertEqual(len(rejected), len(bad) + 1)
        self.assertTrue(all('JSON boolean' in item['error'] for item in rejected))
        self.assertFalse(any(topic == session.GPO_TOPICS[0] for topic, _ in driver.commands))

    def test_off_supply_releases_retained_high_before_enable_and_restores_without_glitch(self):
        initial = {session.EXTIO_TOPIC: 0, session.GPO_TOPICS[0]: 1, session.GPO_TOPICS[1]: 0}
        code, driver, _, final = self.exercise(initial=initial)
        self.assertEqual(code, 0)
        gpio = [(topic, value) for topic, value in driver.commands
                if topic in (session.EXTIO_TOPIC, *session.GPO_TOPICS)]
        self.assertEqual(gpio, [(session.GPO_TOPICS[0], 0), (session.EXTIO_TOPIC, 3300),
                               (session.EXTIO_TOPIC, 0), (session.GPO_TOPICS[0], 1)])
        self.assertEqual(driver.settings, driver.initial)
        self.assertTrue(final['ok'])
        self.assert_other_output_untouched(driver)

    def test_other_voltage_is_rejected_before_gpio_mutation(self):
        for voltage in (1800, 2500, 5000):
            with self.subTest(voltage=voltage):
                code, driver, records, final = self.exercise(initial={session.EXTIO_TOPIC: voltage})
                self.assertEqual(code, 1)
                self.assertFalse(any(item['event'] == 'ready' for item in records))
                self.assertFalse(any(topic in (session.EXTIO_TOPIC, *session.GPO_TOPICS)
                                     for topic, _ in driver.commands))
                self.assertEqual(driver.settings, driver.initial)
                self.assertFalse(final['ok'])

    def test_off_supply_with_other_gpio_activity_is_rejected_before_mutation(self):
        for active in (session.GPO_TOPICS[1], 's/gpi/0/ctrl', 's/gpi/1/ctrl',
                       's/i/lsb_src', 's/v/lsb_src'):
            with self.subTest(active=active):
                initial = {session.EXTIO_TOPIC: 0, session.GPO_TOPICS[1]: 0, active: 1}
                code, driver, records, _ = self.exercise(initial=initial)
                self.assertEqual(code, 1)
                self.assertFalse(any(item['event'] == 'ready' for item in records))
                self.assertFalse(any(topic in (session.EXTIO_TOPIC, *session.GPO_TOPICS)
                                     for topic, _ in driver.commands))
                self.assertEqual(driver.settings, driver.initial)

    def test_failed_assert_still_restores_maybe_changed_output_and_power(self):
        code, driver, _, final = self.exercise([{'state': 'recovery', 'asserted': True}],
            failures={(session.GPO_TOPICS[0], 1): 1})
        self.assertEqual(code, 1)
        self.assertFalse(final['ok'])
        self.assertEqual(driver.settings, driver.initial)
        self.assertEqual(final['recovery_restore_errors'], [])
        self.assert_other_output_untouched(driver)

    def test_failed_setup_voltage_still_restores_all_maybe_changed_settings(self):
        initial = {session.EXTIO_TOPIC: 0, session.GPO_TOPICS[0]: 1, session.GPO_TOPICS[1]: 0}
        code, driver, records, final = self.exercise(initial=initial,
            failures={(session.EXTIO_TOPIC, 3300): 1})
        self.assertEqual(code, 1)
        self.assertFalse(any(item['event'] == 'ready' for item in records))
        self.assertEqual(driver.settings, driver.initial)
        self.assertEqual(final['recovery_restore_errors'], [])

    def test_restore_failure_does_not_skip_output_power_or_statistics_restoration(self):
        initial = {session.EXTIO_TOPIC: 0, session.GPO_TOPICS[0]: 1, session.GPO_TOPICS[1]: 0}
        code, driver, records, final = self.exercise(initial=initial,
            failures={(session.EXTIO_TOPIC, 0): 1})
        self.assertEqual(code, 1)
        self.assertFalse(final['ok'])
        self.assertTrue(final['recovery_restore_errors'])
        self.assertTrue(any(item['event'] == 'recovery_restore_error' for item in records))
        self.assertEqual(driver.settings, driver.initial)
        self.assertIn((session.GPO_TOPICS[0], 1), driver.commands)
        self.assertIn((session.RANGE_TOPIC, 128), driver.commands)
        self.assertIn(('s/sstats/ctrl', 0), driver.commands)

    def test_ctrl_c_after_assert_restores_output_before_power(self):
        code, driver, _, final = self.exercise([{'state': 'recovery', 'asserted': True}],
            inject_interrupt=True)
        self.assertEqual(code, 130)
        self.assertEqual(final['reason'], 'interrupt')
        self.assertEqual(driver.settings, driver.initial)
        self.assertLess(driver.commands.index((session.GPO_TOPICS[0], 0)),
                        driver.commands.index((session.RANGE_TOPIC, 128)))


class RecoveryOwnershipTests(unittest.TestCase):
    def test_unowned_output_change_prevents_shared_voltage_restore_without_overwrite(self):
        driver = FakeDriver({session.EXTIO_TOPIC: 0, session.GPO_TOPICS[1]: 0})
        recovery = session.RecoveryOutput(driver)
        recovery.start()
        recovery.set_asserted(True)
        driver.settings[session.GPO_TOPICS[1]] = 1
        current, errors = recovery.restore()
        self.assertTrue(errors)
        self.assertIsNone(current)
        self.assertEqual(driver.settings[session.EXTIO_TOPIC], 3300)
        self.assertEqual(driver.settings[session.GPO_TOPICS[0]], 0)
        self.assertEqual(driver.settings[session.GPO_TOPICS[1]], 1)
        self.assertNotIn((session.EXTIO_TOPIC, 0), driver.commands)
        self.assertFalse(any(topic == session.GPO_TOPICS[1] for topic, _ in driver.commands))


if __name__ == '__main__':
    unittest.main()
