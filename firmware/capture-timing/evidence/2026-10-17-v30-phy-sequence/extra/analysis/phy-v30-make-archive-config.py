"""Select the completed failed runs and unflashed guarded candidates explicitly."""
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/bringup'
builds = []
for name, directory, state in (
    ('early-v30b', 'capture-phy-early-v30b-final-20261017', 'programmed and readback verified; capture stalled'),
    ('early-v30d-unflashed', 'capture-phy-early-v30d-guarded-20261017', 'offline candidate; not flashed at checkpoint'),
    ('late-v30d-unflashed', 'capture-phy-late-v30d-guarded-20261017', 'offline candidate; not flashed at checkpoint'),
):
    for kind in ('receiver', 'staged'):
        builds.append(dict(id=f'{name}-{kind}', directory=f'tmp/bringup/{directory}/{kind}',
                           hardware_status_at_checkpoint=state))
captures = []
for name, directory, logic in (
    ('early-v30b-failed-cold-01', 'phy-v30-early-cycle-01/cold', 'phy-v30-early-cycle-01/cold/logic'),
    ('early-v30b-failed-recovery-cold-02', 'phy-v30-recovery-cold-02', 'phy-v30-recovery-cold-02'),
):
    captures.append(dict(id=name, directory='tmp/bringup/' + directory,
        logic_directory='tmp/bringup/' + logic,
        receiver_build='early-v30b-receiver', prefix_build='early-v30b-staged',
        programming_cycle_directory='tmp/bringup/phy-v30-early-cycle-01', outcome='failed',
        outcome_note='24 externally observed PE0 transitions; no RAM event dump, PHY snapshot or image. '
                     'Core inaccessible. Probable diagnostic read under peripheral reset is a source-based inference.'))
extra = []
for path in sorted(BASE.glob('phy-v30-*')):
    if path.is_file() and path.suffix in ('.log', '.cfg'):
        extra.append(dict(source=str(path.relative_to(ROOT)).replace('\\', '/'),
                          archive='recovery/' + path.name))
for name in ('powered-state.json', 'capture-config.json', 'boot-summary.json', 'digital.csv'):
    extra.append(dict(source='tmp/bringup/phy-sequence-before-20261017/' + name,
                      archive='before-test/' + name))
for name in ('phy-v30-offline-summary.py', 'phy-v30-make-archive-config.py'):
    extra.append(dict(source='tmp/bringup/' + name, archive='analysis/' + name))
for name in ('build.py', 'transforms.py', 'summarize.py', 'README.md'):
    extra.append(dict(source='firmware/capture-timing/late_phy/' + name,
                      archive='current-host-tools/' + name))
config = dict(schema=1, date='2026-10-17',
    checkpoint_utc=datetime.now(timezone.utc).isoformat(),
    scope='Failed v30b early-receiver trial and repeat, recovery records to checkpoint, '
          'and guarded v30d offline build provenance. No successful PHY comparison or restored-board claim.',
    board_recovery_and_final_validation='pending root bench owner',
    builds=builds, captures=captures, extra_files=extra)
destination = BASE / 'phy-v30-archive-config.json'
with destination.open('x', encoding='utf-8') as stream:
    json.dump(config, stream, indent=2)
    stream.write('\n')
print(destination)
