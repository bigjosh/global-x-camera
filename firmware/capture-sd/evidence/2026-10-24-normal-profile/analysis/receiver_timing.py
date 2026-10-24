"""Offline, exact normal-profile RCP2-to-SAVE timing partition.

No device operations. Durations use the reported nominal 400 MHz DWT clock.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from fine_timing import require, validate_raw_report, analyze_report


def delta(end, begin):
    value = (end-begin) & 0xffffffff
    require(value < 0x80000000, 'Reversed or ambiguous cycle interval')
    return value


def partition(frame, receiver_raw, maintenance, report_raw, loader_raw):
    require(len(receiver_raw) == 128, 'RCP2 size')
    words = list(struct.unpack('<32I', receiver_raw))
    require(frame.get('receiver_proof_valid_after_maintenance') is True,
            'Receiver proof was not valid after maintenance')
    require(frame.get('receiver_words') == words, 'RCP2 raw/JSON disagreement')
    require(words[:6] == [0x52435032, 2, 32, 0, 2, 0x1f],
            'Need successful normal RCP2 proof')
    require(words[6:12] == [0x34000000, 3055360, 1120, 1364, 10, 43],
            'Unexpected frame geometry/layout')
    require(words[12:16] == [0, 3055360, 0, 255],
            'Hash/byte count/error/canary flags differ')
    require(words[22:24] == [0, 0] and words[25:] == [0]*7,
            'Normal profile must skip full scans/register dumps')
    storage = maintenance['storage_proof']
    require(storage.get('recognized') and storage.get('automatic_save'),
            'Missing automatic SAVE ownership')
    report = storage['report']
    validate_raw_report(report, report_raw)
    fine = analyze_report(report, storage['card'])
    require(fine['profile'] == 'normal', 'Different SAVE profile')
    require(frame['save']['raw_words'] == report['raw_words'],
            'Receiver and maintenance SAVE report differ')
    require(len(loader_raw) == 64, 'Loader proof size')
    loader = list(struct.unpack('<16I', loader_raw))
    require(loader == storage['loader_words'], 'Loader raw/JSON disagreement')
    require(loader[0] == 0x534c4431 and loader[8] > 0 and
            loader[9] and loader[10] == 0 and loader[11],
            'Loader did not successfully return')
    bounds = [words[16], words[17], words[18], words[19], words[20],
              words[21], words[24], loader[1], loader[9], report['begin']]
    labels = [
        'essential_frame_checks', 'bookkeeping_before_pipe_stop',
        'pipe_stop', 'receiver_data_disable', 'sensor_stop_call',
        'bookkeeping_to_handoff', 'handoff_to_loader_start',
        'nor_module_read_and_crc', 'loader_tail_entry_bss_and_report_initialization']
    values = [delta(b, a) for a, b in zip(bounds, bounds[1:])]
    total = delta(bounds[-1], bounds[0])
    require(sum(values) == total, 'Receiver partition wraps more than once')
    return {
        'schema': 1, 'profile': 'normal', 'cpu_hz_assumed': 400000000,
        'start': 'RCP2 post-frame processing begin', 'end': 'SAVE P_BEGIN',
        'start_cycle': bounds[0], 'end_cycle': bounds[-1],
        'total_cycles': total, 'total_ms': total/400000,
        'partition_sum_exact': True,
        'disjoint_cycles': dict(zip(labels, values)),
        'disjoint_ms': {k:v/400000 for k,v in zip(labels, values)},
        'module_sha256': storage['module_sha256'], 'name': fine['name'],
        'limits': [
            'This starts at post-frame processing, not at the frame interrupt or exposure end.',
            'All boundaries use DWT; milliseconds assume nominal 400 MHz and include timer overhead.',
            'Sensor STOP is the full function interval including its polling and protocol overhead.',
            'The loader-to-SAVE interval includes loader tail, I-cache disable, entry/context setup, BSS zeroing and report initialization. It is not a pure BSS timer.',
            'Normal profile skips full-frame FNV/statistics and bulk register dumps; zero scan fields mean skipped.',
            'These intervals are sequential and disjoint. No Saleae or Joulescope alignment is inferred.'
        ]}


def analyze(spec_path):
    spec_path = Path(spec_path).resolve()
    spec = json.loads(spec_path.read_text())
    require(spec.get('schema') == 1, 'Spec schema')
    inputs = {}
    for role, item in spec['artifacts'].items():
        path = Path(item['path'])
        data = (path if path.is_absolute() else spec_path.parent/path).read_bytes()
        require(hashlib.sha256(data).hexdigest() == item['sha256'], 'Hash differs: '+role)
        inputs[role] = data
    result = partition(json.loads(inputs['frame_result']), inputs['receiver_raw'],
        json.loads(inputs['maintenance']), inputs['report_raw'], inputs['loader_raw'])
    result['input_sha256'] = {k:v['sha256'] for k,v in spec['artifacts'].items()}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    result = analyze(args.spec)
    args.out.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'total_ms': result['total_ms'], 'exact_partition': True}))
