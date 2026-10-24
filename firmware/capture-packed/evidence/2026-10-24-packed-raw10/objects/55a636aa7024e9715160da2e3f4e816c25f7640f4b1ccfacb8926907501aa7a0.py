"""Offline mailbox acknowledgement tests; no target or instrument access."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
spec=importlib.util.spec_from_file_location('raw_restore_audit',HERE/'restore_normal.py')
restore=importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore)


class RestoreAudit(unittest.TestCase):
    def exercise(self,state,first,later=None):
        with tempfile.TemporaryDirectory(prefix='restore-offline-',dir=HERE) as folder:
            base=Path(folder)
            token='raw10-final-'+state+'-123'
            first=dict(first,id=token)
            (base/'js-response.json').write_text(json.dumps(first))
            sleeps=[]
            def advance(seconds):
                sleeps.append(seconds)
                if later is None:
                    self.fail('Unexpected wait in offline acknowledgement test')
                (base/'js-response.json').write_text(json.dumps(dict(later,id=token)))
            with patch.object(restore,'BASE',base), \
                 patch.object(restore.time,'monotonic_ns',return_value=123), \
                 patch.object(restore.time,'sleep',side_effect=advance):
                result=restore.command(state)
            self.assertEqual(json.loads((base/'js-control.json').read_text()),dict(id=token,state=state))
            return result,sleeps

    def test_stop_waits_past_initial_ack(self):
        result,sleeps=self.exercise('stop',dict(event='response',ok=True,range=128),
            dict(event='stopped',ok=True,range=128,starting_range=128,restore_error=None))
        self.assertEqual(result['event'],'stopped')
        self.assertEqual(sleeps,[.1])

    def test_failed_restore_rejected(self):
        for record in [dict(event='stopped',ok=False,range=128,starting_range=128),
                       dict(event='stopped',ok=True,range=0,starting_range=128),
                       dict(event='stopped',ok=True,range=128,starting_range=0),
                       dict(event='stopped',ok=True,range=128,starting_range=128,restore_error='failed')]:
            with self.subTest(record=record),self.assertRaises(RuntimeError):
                self.exercise('stop',record)

    def test_failed_power_ack_rejected(self):
        with self.assertRaises(RuntimeError):
            self.exercise('off',dict(event='response',ok=False))

    def test_normal_power_ack(self):
        result,sleeps=self.exercise('off',dict(event='response',ok=True,range=0))
        self.assertTrue(result['ok'])
        self.assertFalse(sleeps)


if __name__=='__main__': unittest.main(verbosity=2)
