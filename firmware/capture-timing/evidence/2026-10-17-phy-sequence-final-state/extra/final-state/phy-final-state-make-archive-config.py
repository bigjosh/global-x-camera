"""Freeze verified v25 restoration and physical instrument-release evidence."""
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/bringup'
response = json.loads((BASE / 'phy-sequence2-response.json').read_text())
power = json.loads((BASE / 'phy-sequence-final-release/powered-state.json').read_text())
swd = json.loads((BASE / 'phy-sequence-final-swd/result.json').read_text())
if not (response['event'] == 'stopped' and response['ok'] and response['range'] == 128
        and response['starting_range'] == 128 and response['restore_error'] is None
        and power['passed'] and swd['read_only'] and swd['stage'] == 40
        and swd['board_baseline'] == 'v25' and swd['frames'] == 1):
    raise ValueError('Final instrument/power/baseline proofs do not pass')
extra = []
for folder in ('phy-sequence-final-release', 'phy-sequence-final-swd'):
    for path in sorted((BASE / folder).iterdir()):
        if path.is_file() and path.name not in ('analog.csv', 'boot.sal', 'started', 'stop'):
            extra.append(dict(source=str(path.relative_to(ROOT)).replace('\\', '/'),
                              archive=f'final-state/{folder}/{path.name}'))
for name in ('phy-sequence2-session.jsonl', 'phy-sequence2-response.json',
             'phy-final-state-make-archive-config.py'):
    extra.append(dict(source='tmp/bringup/' + name, archive='final-state/' + name))
config = dict(schema=1, date='2026-10-17', checkpoint_utc=datetime.now(timezone.utc).isoformat(),
    scope='Exact original v25 baseline restoration, independent autonomous cold capture, '
          'clean JS110 release with physical rail verification, and final read-only SWD proof. '
          'v33 remains a preserved diagnostic candidate rather than the installed baseline.',
    root_assertion='No live hardware helpers or captures remain; Logic 2 automation server remains running.',
    builds=[dict(id=f'v25-{kind}', directory=f'tmp/bringup/capture-raw10-trim-os-v25-20261017/{kind}')
            for kind in ('receiver', 'staged')],
    captures=[dict(id='restored-v25-cold', directory='tmp/bringup/phy-sequence-restore-v25/cold',
        receiver_build='v25-receiver', prefix_build='v25-staged',
        programming_cycle_directory='tmp/bringup/phy-sequence-restore-v25', outcome='completed',
        outcome_note='Original v25 image restored exactly. Autonomous first image intact; baseline '
                     'startup error 0x8000 remains expected because the v33 change is not installed.',
        visual_review=dict(status='Recognizable detailed workshop/bench scene after autonomous baseline cold boot.',
            reviewer='root bench controller',
            provenance='Root personally inspected the restored baseline frame and supplied this assertion.'))],
    extra_files=extra)
with (BASE / 'phy-final-state-archive-config.json').open('x', encoding='utf-8') as stream:
    json.dump(config, stream, indent=2)
    stream.write('\n')
