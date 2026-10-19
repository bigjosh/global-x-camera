"""Snapshot completed compact bench logs; never operate the bench."""
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
TMP = ROOT/'tmp/bringup'
EXCLUDE_NAMES = {'frame.bin', 'frame.png', 'frame-16bit.png', 'analog.csv', 'boot.sal'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8', newline='\n')


def main():
    if (HERE/'attempt-source-index.json').exists():
        raise RuntimeError('Attempt snapshot already exists; add a later checkpoint separately')
    included, excluded = [], []
    for label, folder in [('preflight-v41', 'status-leds-v44-preflight-20261018'),
                          ('program-v44', 'status-leds-v44-program-20261018'),
                          ('reset1', 'status-leds-v44-reset1-20261018'),
                          ('reset2', 'status-leds-v44-reset2-20261018')]:
        for source in sorted((TMP/folder).rglob('*')):
            if not source.is_file():
                continue
            relative = source.relative_to(TMP/folder)
            row = dict(source=source.relative_to(ROOT).as_posix(), bytes=source.stat().st_size)
            if source.name in EXCLUDE_NAMES:
                row.update(sha256=sha(source.read_bytes()), reason='Frame pixels, large analog CSV or Logic recording excluded')
                excluded.append(row)
                continue
            if source.stat().st_size > 1048576:
                raise ValueError(f'Unexpected large compact-log candidate: {source}')
            data = source.read_bytes()
            destination = HERE/label/relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            row.update(archive=destination.relative_to(HERE).as_posix(), sha256=sha(data))
            included.append(row)

    # Snapshot complete JSONL lines while the JS session is still live.
    # Keep only ready/command-response metadata; do not retain raw statistics.
    session = TMP/'status-leds-v44-js110.jsonl'
    data = session.read_bytes()
    end = data.rfind(b'\n')+1
    complete = data[:end]
    retained = []
    for line in complete.splitlines():
        event = json.loads(line)
        if event.get('event') == 'statistics':
            continue
        event.pop('statistics', None)
        retained.append(event)
    (HERE/'js110-session-metadata.jsonl').write_text(
        ''.join(json.dumps(item)+'\n' for item in retained), encoding='utf-8', newline='\n')
    controls = {}
    for name in ('status-leds-v44-control.json', 'status-leds-v44-response.json'):
        value = json.loads((TMP/name).read_text())
        value.pop('statistics', None)
        controls[name] = value
    dump(HERE/'js110-control-snapshot.json', dict(
        captured_utc=datetime.now(timezone.utc).isoformat(), session_still_running=True,
        source=session.relative_to(ROOT).as_posix(), source_complete_line_bytes=end,
        source_complete_line_sha256=sha(complete), retained_events=len(retained),
        raw_statistics_retained=False, control_snapshots=controls,
        limitation='Retained output settings are not measured pin levels; this is not a session-close or final-restoration record'))

    analog = TMP/'status-leds-v44-reset2-20261018/logic/analog.csv'
    with analog.open(newline='') as stream:
        reader = csv.reader(stream)
        header = next(reader)
        low, high = [float('inf')]*6, [float('-inf')]*6
        count, first, last = 0, None, None
        for row in reader:
            stamp = float(row[0])
            if first is None:
                first = stamp
            last = stamp
            for i, field in enumerate(row[1:]):
                value = float(field)
                low[i], high[i] = min(low[i], value), max(high[i], value)
            count += 1
    dump(HERE/'reset2-analog-summary.json', dict(
        source=analog.relative_to(ROOT).as_posix(), source_bytes=analog.stat().st_size,
        source_sha256=sha(analog.read_bytes()), samples=count, first_time_s=first, last_time_s=last,
        channels={header[i+1]:dict(min_v=low[i], max_v=high[i]) for i in range(6)},
        interpretation='Samples are near zero, not literal zero. Physical probe/ground connection was unverified; do not infer MCU rails discharged or powered off.'))
    dump(HERE/'attempt-source-index.json', dict(
        snapshot_utc=datetime.now(timezone.utc).isoformat(), included=included, excluded=excluded,
        session='JS metadata is separately filtered and time-bounded; raw stream is not copied'))
    print(json.dumps(dict(copied_files=len(included), copied_bytes=sum(i['bytes'] for i in included),
                         excluded_files=len(excluded), js_metadata_events=len(retained), analog_samples=count)))


if __name__ == '__main__':
    main()
