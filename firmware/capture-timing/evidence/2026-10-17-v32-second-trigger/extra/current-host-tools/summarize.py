"""Offline compact view of the v30 raw PHY history and external event timing."""
import argparse
import json
from pathlib import Path

LABELS = {299: 'stage2 initial state', 300: 'CSI reset held in prefix',
          301: 'before CSI peripheral reset release', 302: 'after CSI peripheral reset release',
          303: 'before lane merger config', 304: 'after lane merger config',
          305: 'before PHY PEN release', 306: 'after PHY PEN release',
          307: 'START acknowledged and STREAMING', 308: 'Stop qualification change',
          309: 'both data Stop flags qualified', 310: 'receiver armed',
          311: 'before FSYNC write', 312: 'after FSYNC write', 313: 'frame received',
          314: 'FSYNC acknowledged', 315: 'before capture stop',
          316: 'after sensor stop', 317: 'completed capture', 320: 'CSI IRQ entry'}


def summarize(folder):
    result = json.loads((folder / 'ram/capture-result.json').read_text())
    timing = json.loads((folder / 'timing.json').read_text())
    if not timing['matched'] or not result['late_phy_header_valid']:
        raise ValueError('Require a valid PHY header and exact external event correlation')
    header = result['late_phy_status_words'][:32]
    records = []
    for row in result['late_phy_snapshots']:
        entry = dict(row)
        sr1 = entry['sr1']
        entry['label'] = LABELS.get(entry['id'], hex(entry['id']))
        valid = row['prcr'] != 0xffffffff
        entry['csi_registers_read'] = valid
        entry['error_bits_sr1'] = hex(sr1 & 0x1f1f) if valid else None
        entry['stop_data0'] = bool(sr1 & 0x80000) if valid else None
        entry['stop_data1'] = bool(sr1 & 0x2000000) if valid else None
        entry['stop_clock'] = bool(sr1 & 0x10000000) if valid else None
        entry['active_clock'] = bool(sr1 & 0x80000000) if valid else None
        for key in ('sr0', 'sr1', 'ier0', 'ier1', 'prcr', 'pcr', 'cr', 'lmcfgr', 'apb5rstr'):
            entry[key] = f'0x{entry[key]:08x}'
        records.append(entry)
    events = [{**row, 'label': LABELS.get(row['id'], row['label'])}
              for row in timing['events']
              if row['id'] in (21, 22, 24, 25, 26, 29, 30, 40, 50, 51, 73, 74, 152, 153)
              or row['id'] in LABELS or row['id'] & 0x80000000]
    return dict(completed=result['completed'], stage=hex(result['stage']),
                mode='late' if header[6] else 'early',
                camera_error=hex(result['camera_error']), callback_count=result['errors'],
                snapshot_count=header[2], snapshot_overflow=header[3],
                skipped_csi_read_count=header[7],
                observed_sr1_error_union=hex(header[5] & 0x1f1f),
                image_integrity_matches=result.get('image_integrity_matches'),
                sample_statistics=result.get('sample_statistics'),
                events=events, snapshots=records,
                limitations='Snapshots are not continuous waveforms; HAL masks each source after its first callback. '
                            'Event timestamps are external markers; raw snapshots retain unconverted CPU cycles.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    data = summarize(args.capture)
    with args.out.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')
    print(json.dumps({key: value for key, value in data.items() if key not in ('events', 'snapshots')}, indent=2))
