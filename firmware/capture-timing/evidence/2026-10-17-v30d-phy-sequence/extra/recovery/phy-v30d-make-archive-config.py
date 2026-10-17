"""Freeze actual guarded continuous-clock trials and successful debug recovery."""
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/bringup'
builds = []
for mode in ('early', 'late'):
    for kind in ('receiver', 'staged'):
        builds.append(dict(id=f'{mode}-v30d-{kind}',
            directory=f'tmp/bringup/capture-phy-{mode}-v30d-guarded-20261017/{kind}',
            hardware_status_at_checkpoint='programmed and tested; see explicit capture outcome'))
captures = [
    dict(id='early-v30d-cold-01', directory='tmp/bringup/phy-v30d-early-cold-01',
         receiver_build='early-v30d-receiver', prefix_build='early-v30d-staged',
         programming_directory='tmp/bringup/phy-v30d-early-program', outcome='completed',
         outcome_note='Valid first frame with startup lane-1 ECTRL; raw lane-1 flag returns after sensor stop.',
         visual_review=dict(status='Recognizable detailed bench/workshop scene; valid nonuniform grayscale.',
             reviewer='root bench controller',
             provenance='Root personally inspected frame.png and supplied this assertion to the archiving agent. '
                        'The scene is no longer the earlier LED-grid framing.')),
    dict(id='late-v30d-cold-01', directory='tmp/bringup/phy-v30d-late-cycle-01/cold',
         receiver_build='late-v30d-receiver', prefix_build='late-v30d-staged',
         programming_cycle_directory='tmp/bringup/phy-v30d-late-cycle-01', outcome='failed',
         outcome_note='Exposure strobe occurred but no frame arrived before 2 s timeout, stage 0x8000001c. '
                      'No ECTRL observed; this does not qualify as an error-free capture. '
                      'ACTCLF remained clear in snapshots after PHY release.')]
extra = []
for directory in ('phy-v30-prefix-recovery-proof', 'phy-v30-prefix-maintenance', 'phy-v30-recovery-info'):
    for path in sorted((BASE / directory).iterdir()):
        if path.is_file():
            extra.append(dict(source=str(path.relative_to(ROOT)).replace('\\', '/'),
                              archive=f'recovery/{directory}/{path.name}'))
for name in ('phy-v30-ap2-underreset-init.cfg', 'phy-v30-ap2-underreset-init.log',
             'phy-v30-after-underreset-core.log', 'phy-v30-prefix-recovery-proof.log',
             'read-v30-prefix-proof.py', 'recover-v30-prefix.py', 'phy-v30d-make-archive-config.py'):
    extra.append(dict(source='tmp/bringup/' + name, archive='recovery/' + name))
for name in ('build.py', 'transforms.py', 'summarize.py', 'README.md'):
    extra.append(dict(source='firmware/capture-timing/late_phy/' + name,
                      archive='current-host-tools/' + name))
config = dict(schema=1, date='2026-10-17', checkpoint_utc=datetime.now(timezone.utc).isoformat(),
    scope='Successful debug recovery and matched v30d continuous-clock comparison. '
          'Early capture works with startup warning; late capture times out without a frame. '
          'Noncontinuous-clock follow-up and final baseline restoration are outside this checkpoint.',
    board_recovery='Core access and guarded normal-boot programming restored without boot-jumper changes.',
    final_baseline_restoration='pending root bench owner',
    builds=builds, captures=captures, extra_files=extra)
destination = BASE / 'phy-v30d-archive-config.json'
with destination.open('x', encoding='utf-8') as stream:
    json.dump(config, stream, indent=2)
    stream.write('\n')
print(destination)
