"""Freeze second-trigger diagnostic, explicitly excluding first-frame claims."""
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
builds = [dict(id=f'late-v32-{kind}',
    directory=f'tmp/bringup/capture-phy-late-v32-second-trigger-20261017/{kind}')
    for kind in ('receiver', 'staged')]
capture = dict(id='late-v32-second-trigger-cold-01',
    directory='tmp/bringup/phy-v32-second-trigger-cycle-01/cold',
    receiver_build='late-v32-receiver', prefix_build='late-v32-staged',
    programming_cycle_directory='tmp/bringup/phy-v32-second-trigger-cycle-01',
    outcome='completed',
    outcome_note='Second requested sensor image received. First exposure produced no receiver VSYNC/frame. '
                 'Not eligible for first-frame latency or first-frame-success claims. '
                 'No PHY reset or DCMIPP rearm between requests. Only recorded ECTRL occurs during later sensor stop.',
    visual_review=dict(status='Recognizable detailed workshop/bench scene in the SECOND requested image.',
        reviewer='root bench controller',
        provenance='Root personally inspected frame.png and supplied this assertion.'))
extra = [dict(source='tmp/bringup/phy-v32-make-archive-config.py', archive='analysis/phy-v32-make-archive-config.py')]
for name in ('build.py', 'transforms.py', 'summarize.py', 'README.md'):
    extra.append(dict(source='firmware/capture-timing/late_phy/' + name,
                      archive='current-host-tools/' + name))
config = dict(schema=1, date='2026-10-17', checkpoint_utc=datetime.now(timezone.utc).isoformat(),
    scope='Late-enable, noncontinuous-clock second-trigger diagnostic. First image missed; '
          'second image received without intervening PHY reset or receiver rearm. '
          'No first-frame qualification or final baseline restoration claim.',
    final_baseline_restoration='pending root bench owner', builds=builds, captures=[capture], extra_files=extra)
with (ROOT / 'tmp/bringup/phy-v32-archive-config.json').open('x', encoding='utf-8') as stream:
    json.dump(config, stream, indent=2)
    stream.write('\n')
