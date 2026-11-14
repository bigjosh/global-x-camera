"""Offline schema6 telemetry tests; no bench module is imported."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import struct
import unittest

HERE = Path(__file__).resolve().parent


def functions():
    tree = ast.parse((HERE / 'console.py').read_text())
    names = {'read_status', 'positions', 'checked', 'require_current_wiring'}
    ns = dict(hashlib=hashlib, json=json, struct=struct)
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'offline-status', 'exec'), ns)
    return ns


class DualTelemetryTests(unittest.TestCase):
    def test_historical_and_dual_status_read_their_exact_declared_extent(self):
        class Bench:
            def __init__(self, blob): self.blob, self.reads = blob, []
            def upload(self, address, size, name):
                self.reads.append((address, size)); return self.blob
        for schema, words, address in ((5, 64, 0x343C2000), (6, 96, 0x343C2400)):
            values = [0] * words
            values[:6] = [0x31434441, schema, 19, 4, 0, 20]
            values[-1] = 20
            m = dict(schema=schema, proof=address, proof_words=words,
                     proof_sequence_end_word=words-1,
                     fields=['MAGIC', 'VERSION', 'NONCE', 'STATE', 'ERROR_CODE', 'SEQUENCE'])
            bench = Bench(struct.pack('<' + str(words) + 'I', *values))
            result = functions()['read_status'](bench, m, 19, 'sample')
            self.assertEqual(bench.reads, [(address, words*4)])
            self.assertEqual(result['SEQUENCE'], result['SEQUENCE_END'])
            with self.assertRaises(ValueError):
                functions()['read_status'](bench, m, 20, 'wrong-nonce')

    def test_position_fractions_use_each_own_high_endpoint_and_keep_outliers(self):
        check = functions()['positions']
        self.assertEqual(check(dict(RAW=1921, A0_RAW=1, A2_RAW=3841,
                                    ASA_RAW=2881, A4_RAW=3841)),
                         dict(exposure_position=.5, asa_position=.75))
        self.assertEqual(check(dict(RAW=1921, A0_RAW=1, A2_RAW=3841,
                                    ASA_RAW=961, A4_RAW=1921))['asa_position'], .5)
        self.assertGreater(check(dict(RAW=4095, A0_RAW=0, A2_RAW=3800,
                                      ASA_RAW=4095, A4_RAW=3800))['asa_position'], 1)
        self.assertEqual(check(dict(RAW=0, A0_RAW=1, A2_RAW=1,
                                    ASA_RAW=0, A4_RAW=0)),
                         dict(exposure_position=None, asa_position=None))

    def test_current_binary_contract_and_coherent_monitor_fence(self):
        build = HERE.parents[1] / 'tmp/bringup/knobs-both-20261113/diagnostic'
        if not build.exists():
            self.skipTest('Optional local schema6 build unavailable')
        manifest = json.loads((build / 'manifest.json').read_text())
        checked, _ = functions()['checked'](build, manifest['sha256'])
        functions()['require_current_wiring'](checked)
        self.assertEqual((checked['schema'], checked['proof_words'], len(checked['fields'])), (6, 96, 78))
        self.assertEqual(checked['fields'][63], 'ASA_RAW')
        self.assertEqual(checked['adc_security_probe']['words'][-2:], ['GPIOG_SEC', 'GPIOH_SEC'])
        source = (HERE / 'console.py').read_text()
        monitor = source[source.index('def monitor('):source.index('def main(')]
        self.assertLess(monitor.index("seq != p['SEQUENCE'] or seq & 1"), monitor.index('p.update(positions(p))'))
        self.assertLess(monitor.index("seq != p['SEQUENCE'] or seq & 1"), monitor.index("readings.jsonl"))
        for key in ('asa_wiring', 'asa_adc', 'asa_digital_wiper'):
            bad = copy.deepcopy(checked); bad[key] = 'wrong'
            with self.assertRaises(ValueError): functions()['require_current_wiring'](bad)


if __name__ == '__main__':
    unittest.main()
