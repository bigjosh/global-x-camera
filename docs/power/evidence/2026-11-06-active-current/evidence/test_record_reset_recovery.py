"""Offline guards for the reset-held recovery recorder; never opens instruments."""
import ast
import contextlib
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import unittest

import record_reset_recovery as recorder


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


prior = module(recorder.CAMPAIGN.parent/'inrush-20261105/test_record_startup.py',
               'prior_recorder_tests')
prior.recorder = recorder
CleanupTests = prior.CleanupTests
ArgumentTests = prior.ArgumentTests
ProofTests = prior.ProofTests


def functions(path):
    tree = ast.parse(Path(path).read_text())
    return {node.name: node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))}


def hold_block(run, has_train):
    matches = []
    for node in ast.walk(run):
        if not isinstance(node, ast.If):
            continue
        if ast.unparse(node.test) != "a.mode == 'cold-reset-held'":
            continue
        text = ast.unparse(node)
        if 'reset_hold_observation_complete' in text:
            assert ('uart.start_train()' in text) == has_train
            matches.append(node)
    assert len(matches) == 1
    return matches[0]


class ResetRecoveryTests(unittest.TestCase):
    def test_runtime_is_identical_outside_powered_reset_hold(self):
        old = functions(recorder.CAMPAIGN/'record_startup.py')
        new = functions(Path(recorder.__file__))
        self.assertEqual(set(old), set(new))
        for name in old:
            if name not in ('run', 'parse_args'):
                self.assertEqual(ast.dump(old[name]), ast.dump(new[name]), name)
        before = hold_block(old['run'], False)
        after = hold_block(new['run'], True)
        before.body = after.body = [ast.Pass()]
        self.assertEqual(ast.dump(old['run']), ast.dump(new['run']))

    def execute_hold(self, duration, deliver=True):
        new = functions(Path(recorder.__file__))
        block = hold_block(new['run'], True)
        code = compile(ast.fix_missing_locations(ast.Module(body=block.body,
                                                           type_ignores=[])),
                       '<source-bound-held-reset>', 'exec')
        history = []
        state = {'elapsed': 0.0, 'train': False, 'released': False}

        class FakeUART:
            def __init__(self):
                self.state = {'bytes': 0}

            def start_train(self):
                assert not state['train']
                state['train'] = True
                history.append(('train', state['elapsed']))

            def set_break(self, value, reason):
                assert value is False
                state['released'] = True
                history.append(('release', state['elapsed']))

        uart = FakeUART()

        def wait(seconds):
            assert seconds >= 0
            state['elapsed'] += seconds
            if state['train'] and deliver and seconds > 0:
                uart.state['bytes'] += 4096

        try:
            exec(code, {'a': SimpleNamespace(reset_hold_seconds=duration),
                        'uart': uart, 'wait': wait,
                        'event': lambda *a, **kw: history.append(('event', state['elapsed']))})
        except RuntimeError as error:
            return state, history, error
        return state, history, None

    def test_hold_duration_retained_and_train_late_for_all_allowed_bounds(self):
        for duration in (.05, .06, .5, 3.0):
            with self.subTest(duration=duration):
                state, history, error = self.execute_hold(duration)
                self.assertIsNone(error)
                self.assertTrue(state['released'])
                self.assertAlmostEqual(state['elapsed'], duration)
                self.assertAlmostEqual(history[0][1], max(0, duration-.06))
                self.assertEqual([x[0] for x in history], ['train', 'event', 'release'])
                # Four-second transmitter starts late, leaving >=3.94 seconds after release.
                self.assertGreaterEqual(4-(history[-1][1]-history[0][1]), 3.94-1e-12)

    def test_no_delivered_bytes_keeps_reset_asserted_for_existing_off_cleanup(self):
        state, history, error = self.execute_hold(.5, deliver=False)
        self.assertIsInstance(error, RuntimeError)
        self.assertFalse(state['released'])
        self.assertEqual([x[0] for x in history], ['train'])

    def test_cold_reset_does_not_start_train_before_power_on(self):
        self.assertFalse(recorder.wants_train('cold-reset-held'))
        self.assertTrue(recorder.wants_uart('cold-reset-held'))

    def test_reset_recovery_needs_same_three_second_post_window(self):
        args = ['--out', str(recorder.CAMPAIGN/'offline-placeholder'),
                '--mode', 'cold-reset-held', '--execute', '--park-proof', 'unused',
                '--park-current-min-ma', '50', '--park-current-max-ma', '100']
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            recorder.parse_args(args+['--post-seconds', '.5'])
        self.assertEqual(recorder.parse_args(args+['--post-seconds', '3']).post_seconds, 3)


if __name__ == '__main__':
    unittest.main()
