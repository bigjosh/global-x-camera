"""Freeze completed noncontinuous-clock comparison and recovery guard evidence."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/bringup'
builds, captures, extra = [], [], []
for mode in ('early', 'late'):
    for kind in ('receiver', 'staged'):
        builds.append(dict(id=f'{mode}-v31-{kind}',
            directory=f'tmp/bringup/capture-phy-{mode}-v31-noncontinuous-20261017/{kind}',
            hardware_status_at_checkpoint='programmed and tested; see explicit capture outcome'))
    capture = dict(id=f'{mode}-v31-cold-01', directory=f'tmp/bringup/phy-v31-{mode}-cold-01',
        receiver_build=f'{mode}-v31-receiver', prefix_build=f'{mode}-v31-staged',
        programming_directory=f'tmp/bringup/phy-v31-{mode}-program',
        outcome='completed' if mode == 'early' else 'failed')
    if mode == 'early':
        capture.update(outcome_note='First frame valid; usual startup lane-1 ECTRL remains.',
            visual_review=dict(status='Recognizable detailed workshop/bench scene; valid nonuniform grayscale.',
                reviewer='root bench controller',
                provenance='Root personally inspected frame.png and explicitly supplied this assertion.'))
    else:
        capture['outcome_note'] = ('Exposure fired but no frame before 2 s timeout, stage 0x8000001c. '
            'No CSI errors observed; no ACTCLF after receiver release. Final SR1=0x76180000 '
            'contains clock Stop after the missed frame. This is not a successful capture.')
    captures.append(capture)
for directory in ('phy-v30d-late-failure-maintenance', 'phy-v30d-late-failure-maintenance-fixed',
                  'phy-v31-late-maintenance', 'phy-v31-late-info', 'phy-v31-early-info'):
    for path in sorted((BASE / directory).iterdir()):
        if path.is_file():
            extra.append(dict(source=str(path.relative_to(ROOT)).replace('\\', '/'),
                              archive=f'maintenance/{directory}/{path.name}'))
for name in ('powered-state.json', 'capture-config.json', 'boot-summary.json', 'digital.csv'):
    extra.append(dict(source='tmp/bringup/phy-sequence-session-renewal/' + name,
                      archive='session-renewal/' + name))
for name in ('phy-sequence-session.jsonl', 'phy-sequence-response.json',
             'phy-sequence2-session.jsonl', 'phy-sequence2-response.json'):
    extra.append(dict(source='tmp/bringup/' + name, archive='session-renewal/' + name))
for name in ('prepare_maintenance.py', 'test_maintenance_guards.py', 'maintenance-review.md'):
    extra.append(dict(source='firmware/capture-timing/' + name, archive='reviewed-host-tools/' + name))
for name in ('build.py', 'transforms.py', 'summarize.py', 'README.md'):
    extra.append(dict(source='firmware/capture-timing/late_phy/' + name,
                      archive='current-host-tools/' + name))
extra.append(dict(source='tmp/bringup/phy-v31-make-archive-config.py', archive='analysis/phy-v31-make-archive-config.py'))
expected = (BASE / 'capture-phy-late-v30d-guarded-20261017/receiver/capture.bin').read_bytes()
live = (BASE / 'phy-v30d-late-failure-maintenance/failed-phy-live-code.bin').read_bytes()
if len(live) != len(expected):
    raise ValueError('Unexpected original guard failure image size')
differences = [i for i, (a, b) in enumerate(zip(expected, live)) if a != b]
proof = dict(source='offline byte comparison of original rejected live receiver',
    expected_sha256=hashlib.sha256(expected).hexdigest(), live_sha256=hashlib.sha256(live).hexdigest(),
    code_bytes=len(expected), differing_offsets=differences,
    only_final_system_core_clock_word_differs=all(i >= len(expected) - 4 for i in differences),
    initializer_hz=int.from_bytes(expected[-4:], 'little'), runtime_hz=int.from_bytes(live[-4:], 'little'),
    limitation='This explains the strict byte-equality guard rejection; successful maintenance still '
               'requires all independent terminal-state and no-DMA checks.')
proof_path = BASE / 'phy-v31-original-guard-rejection.json'
with proof_path.open('x', encoding='utf-8') as stream:
    json.dump(proof, stream, indent=2)
    stream.write('\n')
extra.append(dict(source='tmp/bringup/' + proof_path.name, archive='analysis/' + proof_path.name))
config = dict(schema=1, date='2026-10-17', checkpoint_utc=datetime.now(timezone.utc).isoformat(),
    scope='Matched v31 noncontinuous-clock early/late receiver-release comparison. '
          'Early first frame succeeds with warning; late first frame times out. '
          'Second-trigger diagnostic and final restoration are outside this checkpoint.',
    ongoing_js110_session='Session 2 remains active; its log/response are checkpoint snapshots, not final release evidence.',
    final_baseline_restoration='pending root bench owner', builds=builds, captures=captures, extra_files=extra)
with (BASE / 'phy-v31-archive-config.json').open('x', encoding='utf-8') as stream:
    json.dump(config, stream, indent=2)
    stream.write('\n')
print(json.dumps(proof, indent=2))
