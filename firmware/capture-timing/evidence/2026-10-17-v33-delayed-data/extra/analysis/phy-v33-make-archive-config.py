"""Freeze three first-frame trials with independent startup/stop phase checks."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/bringup'
builds = [dict(id=f'early-v33-{kind}',
    directory=f'tmp/bringup/capture-phy-early-v33-delayed-data-20261017/{kind}')
    for kind in ('receiver', 'staged')]
captures, checks = [], []
for number, name in ((1, 'phy-v33-delayed-data-cycle-01/cold'),
                     (2, 'phy-v33-delayed-data-cold-02'),
                     (3, 'phy-v33-delayed-data-cold-03')):
    folder = BASE / name
    summary_path = folder / 'phy-summary.json'
    summary = json.loads(summary_path.read_text())
    result = json.loads((folder / 'ram/capture-result.json').read_text())
    snapshots = summary['snapshots']
    before = next(i for i, value in enumerate(snapshots) if value['id'] == 315)
    after = next(i for i, value in enumerate(snapshots) if value['id'] == 316)
    errors = [i for i, value in enumerate(snapshots)
              if value['error_bits_sr1'] is not None and int(value['error_bits_sr1'], 16)]
    if not (summary['completed'] and summary['image_integrity_matches']
            and summary['snapshot_overflow'] == 0 and len(errors) == 1
            and before < errors[0] < after
            and snapshots[errors[0]]['error_bits_sr1'] == '0x1000'
            and result['sample_statistics']['invalid_upper_bits'] == 0):
        raise ValueError(f'Unexpected phase or image result: {name}')
    checks.append(dict(capture=name, summary_sha256=hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        passed=True, before_stop_index=before, error_indexes=errors, after_stop_index=after,
        no_recorded_error_through_frame=True, sole_error_during_sensor_stop='lane 1 ECTRL 0x1000',
        limitation='Discrete raw status snapshots and IRQ history, not a continuous lane waveform.'))
    captures.append(dict(id=f'v33-delayed-data-cold-{number:02d}', directory='tmp/bringup/' + name,
        receiver_build='early-v33-receiver', prefix_build='early-v33-staged',
        programming_cycle_directory='tmp/bringup/phy-v33-delayed-data-cycle-01', outcome='completed',
        outcome_note='FIRST requested frame received intact; no recorded startup/through-frame errors. '
                     'One lane-1 ECTRL occurs later during sensor stop. Clock module enabled early; '
                     'data modules enabled after START acknowledgment/STREAMING. Error handling unchanged.',
        visual_review=dict(status='Recognizable detailed workshop/bench scene in the FIRST requested frame.',
            reviewer='root bench controller',
            provenance=f'Root personally inspected frame.png for cold run {number:02d} and explicitly supplied this assertion.')))
proof_name = 'phy-v33-phase-verification.json'
with (BASE / proof_name).open('x', encoding='utf-8') as stream:
    json.dump(dict(schema=1, checks=checks), stream, indent=2)
    stream.write('\n')
extra = [dict(source='tmp/bringup/' + name, archive='analysis/' + name)
         for name in ('phy-v33-make-archive-config.py', proof_name)]
for name in ('build.py', 'transforms.py', 'summarize.py', 'README.md'):
    extra.append(dict(source='firmware/capture-timing/late_phy/' + name,
                      archive='current-host-tools/' + name))
config = dict(schema=1, date='2026-10-17', checkpoint_utc=datetime.now(timezone.utc).isoformat(),
    scope='Three native first-frame cold captures with early clock receiver and delayed data-lane enable. '
          'No recorded startup or through-frame errors; lane-1 control error remains during later sensor stop. '
          'Working candidate on one board, not exact wire-cause proof or final firmware selection.',
    final_baseline_restoration='recorded separately by root bench owner; outside this checkpoint',
    builds=builds, captures=captures, extra_files=extra)
with (BASE / 'phy-v33-archive-config.json').open('x', encoding='utf-8') as stream:
    json.dump(config, stream, indent=2)
    stream.write('\n')
