"""Fixed RAM log decoding and ARM hook assembly checks; no hardware access."""
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import unittest

import cycle_trace as trace

HERE = Path(__file__).resolve().parent
TC = Path('D:/ST/STM32CubeIDE_1.15.1/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.12.3.rel1.win32_1.0.200.202406191623/tools/bin')
SOURCE = """
#define CTE_BEGIN 0 // Work begins
#define CTE_END 1U /* Work finishes */
#define CTE_OPTIONAL_NEVER_HIT 2
#define CTC_LOOPS 0
"""


def words(start=100, *, complete=True):
    result = [trace.UNSET] * trace.WORDS
    result[:10] = [trace.MAGIC, trace.SCHEMA, trace.WORDS, trace.HZ,
                   0 if complete else trace.UNSET, start,
                   (start + 300) & trace.UNSET if complete else trace.UNSET,
                   trace.EVENT_COUNT, trace.COUNTER_COUNT,
                   trace.DONE if complete else trace.UNSET]
    result[trace.EVENT_WORD] = (start + 100) & trace.UNSET
    result[trace.EVENT_WORD + 1] = (start + 200) & trace.UNSET
    result[trace.COUNTER_WORD:trace.COUNTER_WORD + trace.COUNTER_COUNT] = [0] * trace.COUNTER_COUNT
    result[trace.COUNTER_WORD] = 3
    return result


def binary(values):
    return struct.pack('<256I', *values)


class TraceDecoderTests(unittest.TestCase):
    def setUp(self):
        self.definitions = trace.parse_definitions(SOURCE)

    def test_complete_exact_events_and_never_hit(self):
        result = trace.decode(binary(words()), self.definitions, require_complete=True)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['result'], 0)
        self.assertEqual(result['address'], 0x343FB000)
        self.assertEqual([e['name'] for e in result['events']], ['BEGIN', 'END'])
        self.assertEqual([e['since_init_ticks'] for e in result['events']], [100, 200])
        self.assertEqual(result['events'][1]['since_init_ms'], .0005)
        self.assertEqual(result['events'][0]['description'], 'Work begins')
        self.assertEqual(result['events'][1]['description'], 'Work finishes')
        self.assertEqual(result['never_hit'][0]['description'], 'OPTIONAL NEVER HIT')
        self.assertEqual(result['counters'][0]['value'], 3)
        self.assertEqual(result['completion_since_init_ms'], .00075)
        self.assertNotIn('durations', result)

    def test_partial_and_finish_in_progress_are_explicit(self):
        for update in ({}, {6: 350}, {6: 350, 4: 0}):
            record = words(complete=False)
            for index, value in update.items():
                record[index] = value
            result = trace.decode(binary(record), self.definitions)
            self.assertEqual(result['status'], 'partial')
            with self.assertRaisesRegex(ValueError, 'partial'):
                trace.decode(binary(record), self.definitions, require_complete=True)

    def test_done_is_not_a_success_result(self):
        record = words(); record[4] = 1234
        result = trace.decode(binary(record), self.definitions, require_complete=True)
        self.assertEqual(result['result'], 1234)
        self.assertEqual(result['status'], 'complete')
        self.assertNotIn('success', result)

    def test_rollover_and_zero_timestamp_are_real_events(self):
        record = words(0xFFFFFF9C)  # first event exactly zero after rollover
        result = trace.decode(binary(record), self.definitions, require_complete=True)
        self.assertEqual(result['events'][0]['ticks'], 0)
        self.assertEqual(result['events'][0]['since_init_ticks'], 100)
        self.assertEqual(result['events'][1]['since_init_ticks'], 200)
        self.assertEqual(result['completion_since_init_ms'], .00075)

    def test_tied_events_sort_by_id_without_claiming_order(self):
        record = words(); record[trace.EVENT_WORD + 1] = record[trace.EVENT_WORD]
        result = trace.decode(binary(record), self.definitions)
        self.assertEqual([e['id'] for e in result['events']], [0, 1])
        self.assertEqual(result['events'][0]['since_init_ticks'], result['events'][1]['since_init_ticks'])

    def test_truncated_extended_and_wrong_header_refused(self):
        for data in (binary(words())[:-1], binary(words()) + b'\0', bytes(1024)):
            with self.assertRaises(ValueError): trace.decode(data, self.definitions)
        for index in (0, 1, 2, 3, 7, 8, 9):
            record = words(); record[index] ^= 1
            with self.subTest(index=index), self.assertRaises(ValueError):
                trace.decode(binary(record), self.definitions)

    def test_uninitialized_and_inconsistent_done_refused(self):
        for index in (4, 5, 6):
            record = words(); record[index] = trace.UNSET
            with self.subTest(index=index), self.assertRaises(ValueError):
                trace.decode(binary(record), self.definitions)
        record = words(); record[trace.EVENT_WORD + 1] = record[6] + 1
        with self.assertRaisesRegex(ValueError, 'after completed'):
            trace.decode(binary(record), self.definitions)

    def test_unknown_hit_or_nonzero_counter_refused(self):
        for index in (trace.EVENT_WORD + 5, trace.COUNTER_WORD + 5):
            record = words(); record[index] = 2
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, 'no build definition'):
                trace.decode(binary(record), self.definitions)

    def test_reserved_words_remain_sentinel(self):
        for index in (10, 31, 192, 255):
            record = words(); record[index] = 0
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, 'Reserved'):
                trace.decode(binary(record), self.definitions)

    def test_duplicate_range_expression_and_name_refused(self):
        for source in (
            '#define CTE_X 1\n#define CTE_Y 1',
            '#define CTE_X 1\n#define CTE_X 2',
            '#define CTC_X 0\n#define CTC_Y 0',
            '#define CTE_X 128', '#define CTC_X 32',
            '#define CTE_X -1', '#define CTE_X (1 + 2)',
        ):
            with self.subTest(source=source), self.assertRaises(ValueError):
                trace.parse_definitions(source)
        parsed = trace.parse_definitions('#define CTE_X 0x7Fu // Last\n#define CTC_X 31UL')
        self.assertEqual(parsed['events'][127]['description'], 'Last')
        self.assertIn(31, parsed['counters'])

    def test_header_hash_binding_and_cross_header_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'events.h'; path.write_text(SOURCE)
            digest = trace.sha256(path.read_bytes())
            definitions = trace.load_definitions([path], {str(path): digest})
            result = trace.decode(binary(words()), definitions)
            self.assertTrue(result['event_header_hashes_verified'])
            self.assertEqual(result['event_headers'][0]['sha256'], digest)
            for expected in ({str(path): '0' * 64}, {}, {'different': digest}):
                with self.subTest(expected=expected), self.assertRaises(ValueError):
                    trace.load_definitions([path], expected)
            with self.assertRaisesRegex(ValueError, 'Duplicate header'):
                trace.load_definitions([path, path])
            other = Path(directory) / 'sd.h'; other.write_text('#define CTE_ANOTHER 1')
            with self.assertRaisesRegex(ValueError, 'across headers'):
                trace.load_definitions([path, other])

    def test_canonical_headers_are_unambiguous(self):
        definitions = trace.load_definitions([HERE / 'cycle_trace_events.h', HERE / 'cycle_trace_sd.h'])
        self.assertGreater(len(definitions['events']), 70)
        self.assertGreater(len(definitions['counters']), 10)

    def test_cli_hash_bound_decode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            header = root / 'events.h'; header.write_text(SOURCE)
            dump = root / 'trace.bin'; dump.write_bytes(binary(words()))
            out = root / 'trace.json'
            process = subprocess.run([sys.executable, str(HERE / 'cycle_trace.py'), str(dump),
                '--header', str(header), '--header-sha256', f'{header}={trace.sha256(header.read_bytes())}',
                '--require-complete', '--out', str(out)], capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            result = json.loads(out.read_text())
            self.assertEqual(result['status'], 'complete')
            self.assertTrue(result['event_header_hashes_verified'])


class TraceAssemblyTests(unittest.TestCase):
    def test_actual_arm_mark_is_counter_read_and_fixed_store_without_call(self):
        gcc = TC / 'arm-none-eabi-gcc.exe'
        self.assertTrue(gcc.exists(), 'Repository ARM compiler required')
        source = '''#include "cycle_trace.h"
void trace_mark_only(void) { CYCLE_MARK(RUNTIME_BEGIN); }
void trace_init_only(void) { cycle_trace_init(); }
void trace_finish_only(unsigned result) { cycle_trace_finish(result); }
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = root / 'hooks.c'; code.write_text(source)
            for enabled in (0, 1):
                assembly = root / f'hooks{enabled}.s'
                process = subprocess.run([str(gcc), '-std=c11', '-Os', '-mcpu=cortex-m55',
                    '-mthumb', '-S', f'-DRAW_CYCLE_TRACE={enabled}', '-I', str(HERE),
                    str(code), '-o', str(assembly)], capture_output=True, text=True)
                self.assertEqual(process.returncode, 0, process.stderr)
                text = assembly.read_text()
                marker = text.split('trace_mark_only:', 1)[1].split('.size\ttrace_mark_only', 1)[0]
                self.assertNotRegex(marker, r'\bblx?\b')
                self.assertNotRegex(marker, r'\b(?:dsb|dmb|isb)\b')
                if enabled:
                    # Exactly one pointer load (DWT) and one volatile store.
                    # Address materialization may use additional literal loads.
                    self.assertEqual(len(re.findall(r'\bldr(?:\.w)?\s+[^\n]+\[', marker)), 1, marker)
                    self.assertEqual(len(re.findall(r'\bstr(?:\.w)?\s+', marker)), 1, marker)
                    self.assertIn('dsb sy', text)
                else:
                    self.assertNotRegex(marker, r'\b(?:ldr|str)(?:\.w)?\b')
                    self.assertNotIn('dsb sy', text)


class PrefixTraceTests(unittest.TestCase):
    def setUp(self):
        self.header = [0] * 64
        self.header[0] = 0x43545031; self.header[2] = 2
        self.sensor = [0] * 32
        self.sensor[0:3] = [0x53454E31, 37, 0]
        self.sensor[4:8] = [900000, 920000, 40000, 400000]
        self.loader = [0] * 64
        self.loader[0:4] = [0x53314F4B, 0, 15804, 15804]
        self.loader[20:22] = [0x12345678, 0x12345678]
        self.loader[24:26] = [930000, 2500000]
        self.records = [(200, 20000, 0, trace.HZ), (400, 3000000, 123, trace.HZ)]

    def decode(self, **kwargs):
        return trace.decode_prefix(struct.pack('<64I', *self.header),
            b''.join(struct.pack('<4I', *record) for record in self.records),
            struct.pack('<32I', *self.sensor), struct.pack('<64I', *self.loader), **kwargs)

    def test_successful_prefix_preserves_known_and_unknown_records(self):
        result = self.decode()
        self.assertTrue(result['prefix_success'])
        self.assertTrue(result['events'][0]['known_prefix_event'])
        self.assertFalse(result['events'][1]['known_prefix_event'])
        self.assertEqual(result['events'][1]['hal_tick'], 123)
        fixed = {item['name']: item for item in result['fixed_timestamps']}
        self.assertEqual(fixed['SENSOR_READY']['since_prefix_dwt_zero_ms'], .1)
        self.assertEqual(fixed['EARLY_NOR_END']['since_prefix_dwt_zero_ms'], 6.25)
        self.assertEqual(len(fixed), 6)
        self.assertNotIn('durations', result)

    def test_incomplete_prefix_is_not_success_and_omits_unqualified_fixed_values(self):
        self.loader[0:2] = [0x5331524E, trace.UNSET]
        self.sensor[1:3] = [2, 123]
        with self.assertRaisesRegex(ValueError, 'successful completion'): self.decode()
        result = self.decode(require_success=False)
        self.assertFalse(result['prefix_success'])
        self.assertEqual(result['fixed_timestamps'], [])

    def test_malformed_count_clock_and_success_fields_refused(self):
        self.header[2] = 201
        with self.assertRaises(ValueError): self.decode()
        self.header[2] = 2
        self.records[1] = (400, 3000000, 123, 200000000)
        with self.assertRaisesRegex(ValueError, 'clock'): self.decode()
        self.records[1] = (400, 3000000, 123, trace.HZ)
        self.loader[3] = 15800
        with self.assertRaisesRegex(ValueError, 'inconsistent'): self.decode()
        self.loader[3] = 15804; self.loader[21] ^= 1
        with self.assertRaisesRegex(ValueError, 'inconsistent'): self.decode()

    def set_startup_bracket(self):
        self.header[16:18] = [0x33330000, 0x00100000]
        self.header[2] = 3
        self.records = [(207, 2501000, 0, trace.HZ),
                        (2, 2527000, 0, 64000000),
                        (3, 2532000, 0, trace.HZ)]

    def test_exact_startup_software_clock_default_is_distinct_from_actual_clock(self):
        self.set_startup_bracket()
        result = self.decode()
        self.assertEqual(len(result['software_clock_exceptions']), 1)
        event = result['events'][1]
        self.assertEqual(event['clock_hz'], trace.HZ)
        self.assertEqual(event['reported_software_clock_hz'], 64000000)
        self.assertTrue(event['startup_software_clock_default'])
        self.assertEqual(event['since_prefix_dwt_zero_ms'], 6.3175)

    def test_startup_exception_cannot_normalize_other_mismatches(self):
        self.set_startup_bracket()
        for bad_record in ((4, 2527000, 0, 64000000), (2, 2527000, 1, 64000000),
                           (2, 2527000, 0, 32000000), (2, 2500000, 0, 64000000)):
            self.records[1] = bad_record
            with self.subTest(record=bad_record), self.assertRaisesRegex(ValueError, 'clock'):
                self.decode()
        for position, record in ((0, (206, 2501000, 0, trace.HZ)),
                                 (2, (4, 2532000, 0, trace.HZ)),
                                 (2, (3, 2532000, 0, 64000000))):
            self.set_startup_bracket(); self.records[position] = record
            with self.subTest(record=record), self.assertRaisesRegex(ValueError, 'clock'):
                self.decode()
        self.set_startup_bracket(); self.header[16] ^= 1
        with self.assertRaisesRegex(ValueError, 'clock'): self.decode()
        self.set_startup_bracket(); self.header[17] ^= 1
        with self.assertRaisesRegex(ValueError, 'clock'): self.decode()
        self.set_startup_bracket(); self.header[2] = 4
        self.records.append((2, 2600000, 1, trace.HZ))
        with self.assertRaisesRegex(ValueError, 'clock'): self.decode()
        self.set_startup_bracket(); self.loader[0:2] = [0x5331524E, trace.UNSET]
        with self.assertRaisesRegex(ValueError, 'clock'): self.decode(require_success=False)


if __name__ == '__main__':
    unittest.main()
