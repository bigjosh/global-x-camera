"""Report rail-to-GPIO timing from a Logic raw CSV export.

CH0=NRST, CH1=PD0, CH2=PE0, CH3=auxiliary 3.3 V, CH4=target 5 V.
These voltage crossings are bench references, not an MCU PGOOD signal.
"""

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import median
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bringup'))
from probe_capture import columns, read_digital


def analyze(folder):
    digital = read_digital(folder / 'digital.csv')['channels']
    crossings = {3: [], 4: []}
    armed = {3: False, 4: False}
    thresholds = {3: 2.97, 4: 4.5}
    low_start = {3: None, 4: None}
    low_starts = {3: [], 4: []}
    preceding_low = {3: None, 4: None}
    last_low = {3: None, 4: None}
    previous_time = None
    sample_deltas = []
    with (folder / 'analog.csv').open(newline='', encoding='utf-8-sig') as stream:
        rows = csv.DictReader(stream)
        time_col, names = columns(rows.fieldnames or [])
        if any(ch not in names for ch in (3, 4)):
            raise ValueError('Analog channels 3 and 4 are required for rail timing.')
        if any(ch not in digital for ch in (0, 1, 2)):
            raise ValueError('Digital channels 0, 1 and 2 are required.')
        for row in rows:
            t = float(row[time_col])
            if not math.isfinite(t) or (previous_time is not None and t < previous_time):
                raise ValueError('Analog timestamps must be finite and nondecreasing.')
            if previous_time is not None and t > previous_time and len(sample_deltas) < 4096:
                sample_deltas.append(t - previous_time)
            previous_time = t
            for ch in (3, 4):
                v = float(row[names[ch]])
                if not math.isfinite(v):
                    raise ValueError(f'Non-finite voltage on channel {ch}.')
                if v < 0.1:
                    armed[ch] = True
                    if low_start[ch] is None:
                        low_start[ch] = t
                        low_starts[ch].append(t)
                    last_low[ch] = t
                elif low_start[ch] is not None:
                    preceding_low[ch] = [low_start[ch], last_low[ch]]
                    low_start[ch] = None
                if armed[ch] and v >= thresholds[ch]:
                    crossings[ch].append({'rise_s': t, 'preceding_low_s': preceding_low[ch]})
                    armed[ch] = False

    results = []
    for i, cycle in enumerate(crossings[4]):
        t5 = cycle['rise_s']
        # Associate events with the observed ramp, not an arbitrary lookback
        # before its 90% threshold. A slow ramp can have an earlier GPIO edge.
        lower = cycle['preceding_low_s'][1]
        upper = next((start for start in low_starts[4] if start > t5), float('inf'))
        edge = lambda ch: next((t for t, v in digital[ch]['edges']
                                if v == 1 and lower <= t < upper), None)
        pd0, pe0, reset = edge(1), edge(2), edge(0)
        cycle3 = next((event for event in crossings[3] if lower <= event['rise_s'] < upper), None)
        t3 = cycle3['rise_s'] if cycle3 is not None else None
        item = {'target_5v_4_5v_crossing_s': t5,
                'aux_3v3_2_97v_crossing_s': t3,
                'nrst_rise_s': reset, 'pd0_rise_s': pd0, 'pe0_rise_s': pe0}
        for name, ref in [('target_5v', t5), ('aux_3v3', t3), ('nrst', reset)]:
            item[name + '_to_pd0_ms'] = (pd0 - ref) * 1000 if pd0 is not None and ref is not None else None
        item['preceding_observed_off_s'] = {}
        for ch, event in ((3, cycle3), (4, cycle)):
            interval = event['preceding_low_s'] if event is not None else None
            item['preceding_observed_off_s'][str(ch)] = interval[1] - interval[0] if interval else None
        results.append(item)
    config_path = folder / 'capture-config.json'
    config = json.loads(config_path.read_text(encoding='utf-8-sig')) if config_path.exists() else {}
    digital_rate = config.get('digital_sample_rate')
    if digital_rate is not None and digital_rate <= 0:
        raise ValueError('Configured digital sample rate must be positive.')
    result = {'references': {'ch3': 'auxiliary 3.3 V crossing 2.97 V',
                             'ch4': 'target 5 V crossing 4.50 V'},
              'analog_sample_spacing_us': median(sample_deltas) * 1e6 if sample_deltas else None,
              'digital_sample_spacing_us': 1e6 / digital_rate if digital_rate else None,
              'cycles': results,
              'limitations': ['No MCU PGOOD or always-on/core rail probe in this channel map.',
                              'Observed off intervals do not alone prove every MCU rail was discharged.',
                              'Off means samples below 0.1 V on the named rail; a single low sample can arm a crossing.',
                              'Analog spacing is measured from the CSV; digital spacing requires capture-config.json.',
                              'Timing is for this image and this board supply setup.']}
    (folder / 'boot-summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    analyze(args.folder.resolve())
