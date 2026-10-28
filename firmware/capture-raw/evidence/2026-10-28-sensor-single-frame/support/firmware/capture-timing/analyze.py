"""Offline correlation of capture.c's PE0 toggles with its ordered RAM events.

No hardware access. The default cold-boot mode requires exactly one NRST release
and one later PD0 rise in the selected interval. For a RAM launch use --mode ram
and an explicit --after-s before the launch. Every PE0 transition after the first
event must match one RAM event; missing/extra transitions are errors, not guesses.
"""
import argparse
import csv
import json
import math
from pathlib import Path

LABELS = {
    2: 'main entry', 3: 'clock setup complete', 4: 'camera access configured',
    5: 'I2C ready', 6: 'sensor initialization begins', 10: 'sensor shutdown low',
    11: 'sensor shutdown high', 12: 'sensor initialization complete',
    15: 'exposure and gains configured', 21: 'receiver configured',
    22: 'receiver armed', 24: 'START_STREAM transaction begins',
    25: 'START_STREAM transaction returns', 26: 'sensor start returns',
    29: 'receiver VSYNC callback', 30: 'frame complete callback',
    31: 'main observes completed frame', 40: 'frame hash complete',
    50: 'PA0 rising-edge callback', 51: 'PA0 falling-edge callback',
    70: 'receiver pipe error', 71: 'receiver common error',
    73: 'CSI lane 0 error', 74: 'CSI lane 1 error',
    100: 'sensor READY polling begins', 101: 'sensor model check begins',
    102: 'sensor patch setup begins', 103: 'sensor MCU boot begins',
    104: 'sensor video-timing patch begins', 105: 'sensor Bayer setup begins',
    106: 'sensor GPIO setup begins', 107: 'sensor clocks and frame setup begins',
    108: 'sensor output setup begins', 109: 'sensor stream setup begins',
    110: 'early sensor output setup begins', 111: 'early sensor output setup complete',
    148: 'cold no-reset host pin snapshot', 149: 'cold no-reset host HIGH enabled',
    150: 'pre-START diagnostic dwell begins', 151: 'pre-START diagnostic dwell ends',
    152: 'I2C follower trigger begins', 153: 'I2C follower trigger write returns',
    200: 'stage 1 entry', 201: 'stage 1 sensor shutdown low',
    202: 'stage 1 sensor shutdown high', 203: 'stage 2 NOR load begins',
    204: 'stage 2 NOR load complete', 205: 'stage 2 CRC passed',
    206: 'stage 1 handoff', 207: 'stage 2 entry',
    208: 'stage 1 no-reset host pin snapshot', 209: 'stage 1 no-reset host HIGH enabled',
    220: 'stage 1 sensor initialization begins', 250: 'early-START receiver armed before deadline',
}


def transitions(path):
    """Return actual channel transitions, retaining the first row as state only."""
    edges = [[] for _ in range(6)]
    previous = None
    previous_time = -math.inf
    with Path(path).open(newline='', encoding='utf-8-sig') as source:
        rows = csv.DictReader(source)
        required = ['Time [s]'] + [f'Channel {i}' for i in range(6)]
        if any(key not in (rows.fieldnames or []) for key in required):
            raise ValueError('Expected the six-channel Saleae digital CSV export')
        for row in rows:
            stamp = float(row['Time [s]'])
            state = [int(row[f'Channel {i}']) for i in range(6)]
            if not math.isfinite(stamp) or stamp < previous_time:
                raise ValueError('CSV timestamps must be finite and monotonic')
            if any(value not in (0, 1) for value in state):
                raise ValueError('CSV channel values must be digital 0/1')
            if previous is not None:
                for channel, value in enumerate(state):
                    if value != previous[channel]:
                        edges[channel].append((stamp, value))
            previous, previous_time = state, stamp
    if previous is None:
        raise ValueError('CSV has no samples')
    return edges


def correlate(edges, result, mode='cold', after_s=None, before_s=None):
    if mode not in ('cold', 'ram'):
        raise ValueError('Unknown launch mode')
    if mode == 'ram' and after_s is None:
        raise ValueError('RAM launches require --after-s; PD0 may already be high')
    lower = -math.inf if after_s is None else after_s
    upper = math.inf if before_s is None else before_s
    if lower >= upper:
        raise ValueError('Selected time interval is empty')
    selected = [[(t, v) for t, v in channel if lower < t <= upper] for channel in edges]
    events = result.get('events', [])
    if not events:
        raise ValueError('RAM result has no events to correlate')
    if result.get('event_count') != len(events):
        raise ValueError('RAM event count differs from the event table length')
    if len(events) >= 200:
        raise ValueError('Event buffer reached capacity; later toggles may be unrecorded')
    nrst = pd0 = None
    if mode == 'cold':
        releases = [t for t, v in selected[0] if v == 1]
        if len(releases) != 1:
            raise ValueError(f'Expected exactly one NRST release, found {len(releases)}; trim the interval')
        nrst = releases[0]
        markers = [t for t, v in selected[1] if v == 1 and t > nrst]
        if len(markers) != 1:
            raise ValueError(f'Expected exactly one post-reset PD0 rise, found {len(markers)}')
        pd0 = markers[0]
        pe0 = [(t, v) for t, v in selected[2] if t > pd0]
    else:
        pe0 = selected[2]
        # capture_early sets PE0 low. This optional falling edge is not event().
        if pe0 and pe0[0][1] == 0:
            pe0 = pe0[1:]
    if len(pe0) != len(events):
        raise ValueError(f'PE0 has {len(pe0)} event edges but RAM has {len(events)}; refusing an ambiguous alignment')
    if not pe0 or pe0[0][1] != 1:
        raise ValueError('First event must raise PE0 from its initialized low state')
    rows = []
    clocks_known = False
    for index, (event, (stamp, level)) in enumerate(zip(events, pe0)):
        if level != (1 if index % 2 == 0 else 0):
            raise ValueError('PE0 transitions do not alternate from the initialized low state')
        row = dict(event)
        row.update(index=index, label=LABELS.get(event['id'], f'event {event["id"]:#x}'),
                   time_s=stamp, pe0_level=level)
        if nrst is not None:
            row['after_nrst_us'] = (stamp - nrst) * 1e6
            row['after_pd0_us'] = (stamp - pd0) * 1e6
        if index:
            previous = rows[-1]
            row['external_delta_us'] = (stamp - previous['time_s']) * 1e6
            # The startup SystemCoreClock field can be stale. Never convert
            # main-entry -> clock-ready, even when those fields happen to match.
            if clocks_known and previous['core_hz'] == row['core_hz'] and row['core_hz']:
                delta = (row['cycles'] - previous['cycles']) & 0xffffffff
                row['dwt_delta_us'] = delta * 1e6 / row['core_hz']
                row['external_minus_dwt_us'] = row['external_delta_us'] - row['dwt_delta_us']
                if row['external_delta_us'] > 0:
                    row['observed_cycles_per_second'] = delta * 1e6 / row['external_delta_us']
        if event['id'] == 3:
            clocks_known = True
        rows.append(row)
    warnings = [
        'PE0 timestamps include event logging and interrupt latency; this script does not bound them.',
        'PA0 events are exposure evidence only after qualifying the sensor route, zero strobe offsets, and first-frame association.',
        'A visible LED-panel image must be checked separately; matching checksums or pixel range alone is insufficient.',
    ]
    if mode == 'ram':
        warnings.append('RAM launch has no autonomous reset-to-capture timing; --after-s is a caller-supplied alignment boundary.')
    if any(row.get('external_delta_us', 0) >= 1000 and 'dwt_delta_us' in row
           and abs(row['external_delta_us'] - row['dwt_delta_us']) > .005 * row['external_delta_us']
           for row in rows):
        warnings.append('At least one interval of 1 ms or more disagrees with nominal-clock DWT conversion by over 0.5%; use external time and investigate clock tolerance or DWT stoppage.')
    if not result.get('completed'):
        warnings.append('Firmware did not reach the completed-frame terminal state.')
    if not result.get('image_integrity_matches'):
        warnings.append('Host-to-MCU frame integrity has not passed.')
    for name in ('camera_error', 'errors', 'result'):
        if result.get(name, 0):
            warnings.append(f'Firmware {name} is nonzero: {result[name]}.')
    pulses, pending, stream_seen = [], None, False
    for row in rows:
        if row['id'] == 24:
            stream_seen = True
        elif row['id'] == 50:
            if pending is not None:
                warnings.append('Repeated PA0 rise without a matching fall.')
            pending = (row, stream_seen)
        elif row['id'] == 51:
            if pending is None:
                warnings.append('PA0 fall without a preceding recorded rise.')
            else:
                start, after_stream = pending
                pulse = dict(rise_index=start['index'], fall_index=row['index'],
                             width_us=(row['time_s'] - start['time_s']) * 1e6,
                             rise_after_start_stream=after_stream)
                if nrst is not None:
                    pulse['rise_after_nrst_us'] = start['after_nrst_us']
                pulses.append(pulse)
                pending = None
    if pending:
        warnings.append('Last PA0 rise has no recorded fall.')
    return dict(matched=True, mode=mode, nrst_release_s=nrst, pd0_rise_s=pd0,
                events=rows, pa0_pulses=pulses, warnings=warnings,
                exposure_qualified=False, note='Correlation only; qualification requires the evidence described in exposure-measurement.md.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--mode', choices=('cold', 'ram'), default='cold')
    parser.add_argument('--after-s', type=float)
    parser.add_argument('--before-s', type=float)
    parser.add_argument('--out', type=Path, help='New JSON output file; default prints JSON')
    args = parser.parse_args()
    for value in (args.after_s, args.before_s):
        if value is not None and not math.isfinite(value):
            parser.error('Time bounds must be finite')
    result = json.loads(args.result.read_text(encoding='utf-8-sig'))
    analysis = correlate(transitions(args.csv), result, args.mode, args.after_s, args.before_s)
    text = json.dumps(analysis, indent=2) + '\n'
    if args.out:
        with args.out.open('x', encoding='utf-8') as output:
            output.write(text)
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
