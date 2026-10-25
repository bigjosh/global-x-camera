"""Trace extraction through the real completed-capture gate; no hardware access.

These tests use the existing camera/card/idle fixtures. They do not mock the
trace decoder or relax the gate to make an incomplete log look successful.
"""
import copy
import importlib.util
from pathlib import Path
import re
import shutil
import struct
import tempfile
import unittest
from unittest.mock import patch

import cycle_trace
from cycle_trace_transform import transform
from test_inspect_flash import f, fixture

HERE = Path(__file__).resolve().parent
LAYOUT = dict(address=0x343FB000, words=256, schema=1, clock_hz=400000000,
    headers=['cycle_trace_events.h', 'cycle_trace_sd.h'],
    completion='awake terminal; no Standby entry timing')


def trace_fixture(folder):
    p, manifest, code, payloads = fixture()
    shutil.copyfile(HERE / 'runtime.h', folder / 'runtime.h')
    manifest['cycle_trace'] = copy.deepcopy(LAYOUT)
    manifest['flags'] = ['-DRAW_CYCLE_TRACE=1']
    manifest['source_hashes'] = {}
    for name in LAYOUT['headers']:
        shutil.copyfile(HERE / name, folder / name)
        manifest['source_hashes'][name] = cycle_trace.sha256((folder / name).read_bytes())
    words = [cycle_trace.UNSET] * cycle_trace.WORDS
    words[:10] = [cycle_trace.MAGIC, 1, 256, 400000000, 0, 90, 220, 128, 32,
                  cycle_trace.DONE]
    words[32] = 100                         # RUNTIME_BEGIN
    words[32 + 47] = 210                    # TERMINAL_READY
    words[160:192] = [0] * 32
    words[160] = 1                         # SD_INIT_CALLS
    words[160 + 8] = 1                      # SD_CMD25_CALLS
    payloads['cycle-trace.bin'] = struct.pack('<256I', *words)
    header = [0] * 64
    header[0] = 0x43545031
    header[2] = 3
    payloads['prefix-trace-header.bin'] = struct.pack('<64I', *header)
    payloads['prefix-trace-events.bin'] = b''.join(
        struct.pack('<4I', event, ticks, 0, 400000000)
        for event, ticks in [(200, 5), (100, 10), (206, 80)])
    sensor = [0] * 32
    sensor[:3] = [0x53454E31, 37, 0]
    sensor[4:8] = [40, 50, 20, 30]
    payloads['prefix-sensor.bin'] = struct.pack('<32I', *sensor)
    loader = [0] * 64
    loader[:4] = [0x53314F4B, 0, 15804, 15804]
    loader[20:22] = [123, 123]
    loader[24:26] = [60, 70]
    payloads['prefix-loader.bin'] = struct.pack('<64I', *loader)
    return p, manifest, code, payloads


class FakeBench:
    def __init__(self, folder, payloads):
        self.output = folder / 'inspection'
        self.payloads = payloads
        self.uploads = []

    def upload(self, address, count, name):
        self.uploads.append((address, count, name))
        result = self.payloads[name]
        if len(result) != count:
            raise AssertionError(f'Fixture length differs for {name}')
        return result


class TraceInspectionIntegration(unittest.TestCase):
    def inspect(self, folder, manifest, code, payloads):
        bench = FakeBench(folder, payloads)

        def context(*args):
            self.assertEqual(bench.uploads[-1][2], 'proof-before-halt.bin')
            self.assertNotIn('cycle-trace.bin', [item[2] for item in bench.uploads])
            return {'test': True}

        with patch.object(f.bench.sd, 'context_proof', side_effect=context) as gate, \
             patch.object(f, 'camera_telemetry', return_value={'test': True}):
            result = f.inspect(bench, folder, manifest, code)
            gate.assert_called_once()
        return result, bench

    def test_success_extracts_hash_bound_log_only_after_complete_idle_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            _, manifest, code, data = trace_fixture(folder)
            result, bench = self.inspect(folder, manifest, code, data)
            self.assertTrue(result['passed'])
            self.assertEqual(result['cycle_trace']['status'], 'complete')
            self.assertEqual(result['cycle_trace']['result'], 0)
            self.assertTrue(result['cycle_trace']['event_header_hashes_verified'])
            self.assertTrue(result['prefix_telemetry']['prefix_success'])
            self.assertEqual(result['prefix_telemetry']['event_count'], 3)
            self.assertIn((0x343FB000, 1024, 'cycle-trace.bin'), bench.uploads)
            self.assertEqual((folder / 'cycle-trace.bin').read_bytes(), data['cycle-trace.bin'])
            self.assertTrue((folder / 'cycle-trace.json').exists())
            self.assertTrue((folder / 'prefix-telemetry.json').exists())
            self.assertFalse(result['sd_payload_integrity_verified'])

    def test_disabled_trace_needs_no_header_or_trace_sram_access(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            _, manifest, code, data = fixture()
            shutil.copyfile(HERE / 'runtime.h', folder / 'runtime.h')
            result, bench = self.inspect(folder, manifest, code, data)
            self.assertNotIn('cycle_trace', result)
            self.assertFalse(any('trace' in item[2] or 'prefix' in item[2] for item in bench.uploads))

    def test_layout_and_compile_flag_drift_are_rejected_before_trace_read(self):
        for change in (dict(address=0x343FA000), dict(words=128), dict(schema=2),
                       dict(clock_hz=200000000), dict(headers=['cycle_trace_events.h']),
                       dict(completion='Standby')):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                _, manifest, code, data = trace_fixture(folder)
                manifest['cycle_trace'].update(change)
                with self.assertRaisesRegex(ValueError, 'layout/configuration'):
                    self.inspect(folder, manifest, code, data)
                self.assertFalse((folder / 'cycle-trace.bin').exists())
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            _, manifest, code, data = trace_fixture(folder)
            manifest['flags'] = []
            with self.assertRaisesRegex(ValueError, 'layout/configuration'):
                self.inspect(folder, manifest, code, data)

    def test_frozen_event_headers_must_match_recorded_hashes(self):
        for name in LAYOUT['headers']:
            with self.subTest(header=name), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                _, manifest, code, data = trace_fixture(folder)
                with (folder / name).open('a') as stream:
                    stream.write('\n/* Changed after build. */\n')
                with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
                    self.inspect(folder, manifest, code, data)
                self.assertFalse((folder / 'cycle-trace.bin').exists())

    def test_partial_failed_or_malformed_log_never_reports_success(self):
        mutations = [(9, cycle_trace.UNSET), (4, 1), (0, 0), (1, 2),
                     (10, 0), (6, cycle_trace.UNSET), (32 + 47, 221)]
        for index, value in mutations:
            with self.subTest(word=index, value=value), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                _, manifest, code, data = trace_fixture(folder)
                raw = bytearray(data['cycle-trace.bin'])
                struct.pack_into('<I', raw, 4 * index, value)
                data['cycle-trace.bin'] = bytes(raw)
                with self.assertRaises(ValueError):
                    self.inspect(folder, manifest, code, data)

    def test_bad_prefix_count_or_failed_prefix_refuses_combined_report(self):
        for name, offset, value in [('prefix-trace-header.bin', 8, 201),
                                    ('prefix-loader.bin', 4, 1),
                                    ('prefix-sensor.bin', 8, 1)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                _, manifest, code, data = trace_fixture(folder)
                raw = bytearray(data[name])
                struct.pack_into('<I', raw, offset, value)
                data[name] = bytes(raw)
                with self.assertRaises(ValueError):
                    self.inspect(folder, manifest, code, data)

    def test_successful_logger_does_not_override_active_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            _, manifest, code, data = trace_fixture(folder)
            fields = f.bench.fields(HERE)
            proof = bytearray(data['proof-before.bin'])
            struct.pack_into('<I', proof, fields.index('media_idle') * 4, 0)
            data['proof-before.bin'] = bytes(proof)
            bench = FakeBench(folder, data)
            with patch.object(f.bench.sd, 'context_proof') as gate:
                with self.assertRaises(ValueError):
                    f.inspect(bench, folder, manifest, code)
                gate.assert_not_called()
            self.assertNotIn('cycle-trace.bin', [item[2] for item in bench.uploads])


class ReceiverTraceTransform(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('trace_build_integration', HERE / 'build.py')
        cls.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.builder)
        original = (cls.builder.BASE / 'receiver/capture.c').read_text().replace('\r\n', '\n')
        cls.before = cls.builder.transform_magic(cls.builder.transform_capture(original))

    def test_markers_only_add_logging_preserving_original_source_tokens(self):
        after = transform(self.before)
        self.assertEqual(after.count('#include "cycle_trace.h"'), 1)
        stripped = after.replace('#include "cycle_trace.h"', '')
        stripped = re.sub(r'CYCLE_(?:MARK|COUNT)\([A-Z0-9_]+\);', '', stripped)
        tokens = lambda text: re.findall(r'\w+|[^\w\s]', text)
        self.assertEqual(tokens(stripped), tokens(self.before))
        definitions = cycle_trace.load_definitions([HERE / name for name in LAYOUT['headers']])
        names = {item['name'] for item in definitions['events'].values()}
        self.assertTrue(set(re.findall(r'CYCLE_MARK\((\w+)\)', after)) <= names)

    def test_missing_or_duplicated_anchor_refuses_silent_partial_instrumentation(self):
        for old, new in [('  HAL_Init();', '  changed_HAL_Init();'),
                         ('  HAL_Init();', '  HAL_Init();\n  HAL_Init();')]:
            with self.subTest(replacement=new), self.assertRaisesRegex(ValueError, 'anchor differs'):
                transform(self.before.replace(old, new, 1))
        with self.assertRaisesRegex(ValueError, 'anchor differs'):
            transform(transform(self.before))


if __name__ == '__main__':
    unittest.main()
