"""Offline phase context from the analyses bound by the completed comparison."""
from pathlib import Path
import hashlib
import json
import statistics

HERE = Path(__file__).resolve().parent
summary_path = HERE/'summary.json'
summary = json.loads(summary_path.read_text())
rows = []
for run, source in zip(summary['rows'], summary['sources']):
    data = Path(source['analysis']).read_bytes()
    assert hashlib.sha256(data).hexdigest() == source['analysis_sha256']
    analysis = json.loads(data)
    events = {item['id']: item for item in analysis['marker_decode']['events']}
    phases = analysis['cycle']['phase_windows_overlapping_not_additive']
    row = dict(label=run['label'], group=run['group'],
               onset_to_plateau_ms=run['plateau_from_onset_ms'],
               post5ms_to_plateau_energy_mJ=run['post5ms_to_plateau_energy_mJ'])
    for phase, first, last in (('SD_init', 4, 5), ('scan_preparation', 5, 6), ('slot_transport', 6, 7)):
        value = phases[phase]
        assert value['valid']
        assert abs(value['duration_ms']-(events[last]['time_ms']-events[first]['time_ms'])) < 1e-9
        for field in ('duration_ms', 'energy_mJ', 'current_mean_mA'):
            row[phase+'_'+field] = value[field]
    rows.append(row)

groups = {}
for group in ('C17 fitted', 'C17 removed'):
    selected = [row for row in rows if row['group'] == group]
    groups[group] = {key: {'min': min(row[key] for row in selected),
                           'median': statistics.median(row[key] for row in selected),
                           'max': max(row[key] for row in selected)}
                     for key in selected[0] if key not in ('group', 'label')}
result = dict(summary_sha256=hashlib.sha256(summary_path.read_bytes()).hexdigest(),
              rows=rows, groups=groups,
              interpretation='The shorter SD transport interval dominates the lower total cycle energy. Do not attribute that energy reduction to C17 removal.',
              limits=['Phase intervals include whole-board consumption, not isolated SD current.',
                      'Transport interval includes bus transfers, card waits and host scheduling; these markers do not separate them.',
                      'The fixed firmware and SD history differ from a randomized C17-only experiment.',
                      'No root documentation changes or hardware access.'])
with (HERE/'sd-timing-context.json').open('x', encoding='utf-8') as stream:
    json.dump(result, stream, indent=2)
    stream.write('\n')
lines = ['SD timing confounds the apparent cycle-energy saving', '',
         '| Run | SD init (ms) | Scan/preparation (ms) | Slot transport (ms) | Transport energy (mJ) |',
         '|---|---:|---:|---:|---:|']
for row in rows:
    lines.append('| {label} | {SD_init_duration_ms:.3f} | {scan_preparation_duration_ms:.3f} | '
                 '{slot_transport_duration_ms:.3f} | {slot_transport_energy_mJ:.3f} |'.format(**row))
old, new = groups['C17 fitted'], groups['C17 removed']
lines.extend(['',
    'Median SD initialization: {:.3f} → {:.3f} ms.'.format(old['SD_init_duration_ms']['median'], new['SD_init_duration_ms']['median']),
    'Median scan/preparation: {:.3f} → {:.3f} ms.'.format(old['scan_preparation_duration_ms']['median'], new['scan_preparation_duration_ms']['median']),
    'Median slot transport: {:.3f} → {:.3f} ms.'.format(old['slot_transport_duration_ms']['median'], new['slot_transport_duration_ms']['median']),
    'Median transport energy: {:.3f} → {:.3f} mJ.'.format(old['slot_transport_energy_mJ']['median'], new['slot_transport_energy_mJ']['median']),
    '', result['interpretation'],
    'These are whole-board phase intervals; transport combines bus transfers, card waits and host scheduling.',
    'The power trace does not determine why card service time changed. Startup charge and peak comparisons remain separately limited by instrument response.',
    'No hardware was operated and no root documentation was edited.'])
with (HERE/'sd-timing-context.md').open('x', encoding='utf-8') as stream:
    stream.write('\n'.join(lines)+'\n')
print(json.dumps(groups, indent=2))
