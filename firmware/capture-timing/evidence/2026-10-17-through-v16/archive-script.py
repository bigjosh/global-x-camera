import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/bringup'
DEST = ROOT / 'firmware/capture-timing/evidence/2026-10-17-through-v16'
sys.path.insert(0, str(ROOT / 'firmware/capture-timing'))
from summarize import summarize_documents

def digest(data):
    return hashlib.sha256(data).hexdigest()

def publish(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f'Refusing different overwrite: {path}')
    else:
        with path.open('xb') as stream:
            stream.write(data)

records = []
def copy(source, relative):
    data = source.read_bytes()
    if len(data) > 2_000_000:
        raise ValueError(f'Unexpected large evidence file: {source}')
    target = DEST / relative
    publish(target, data)
    records.append(dict(source=str(source.relative_to(ROOT)).replace('\\','/'),
                        archive=str(relative).replace('\\','/'), bytes=len(data), sha256=digest(data)))
    return target

def json_publish(path, value):
    publish(path, (json.dumps(value, indent=2) + '\n').encode())

# id, capture directory, stage2/monolithic build, optional prefix build
experiments = [
    ('v3-ram', 'capture-opt-rom-v3-trace', 'capture-rom-clocks-v3-20261017', None),
    ('v5-ram', 'capture-opt-v5-02', 'capture-fixed100k-v5-20261017', None),
    ('v6-ram', 'capture-opt-v6-01', 'capture-fast400-v6-20261017', None),
    ('v7-ram', 'capture-opt-v7-01', 'capture-fastplus-v7-20261017', None),
    ('v8a-ram', 'capture-opt-v8a-01', 'capture-shortreset-v8a-20261017', None),
    ('v9-ram', 'capture-opt-v9-01', 'capture-small-v9-20261017', None),
    ('v9-cold', 'capture-opt-v9-cold-01', 'capture-small-v9-20261017', None),
    ('v11-cold', 'capture-opt-v11-cold-01', 'capture-stage2-v11b-20261017', 'capture-staged-v11b-20261017'),
    ('v13-cold', 'capture-opt-v13-cold-01', 'capture-stage2-fastphy-v13b-20261017', 'capture-staged-fastphy-v13b-20261017'),
    ('v14-cold', 'capture-opt-v14-cycle-01/cold', 'capture-stage2-batched-v14-20261017', 'capture-staged-batched-v14-20261017'),
    ('v15-cold', 'capture-opt-v15-cycle-01/cold', 'capture-stage2-early-v15-20261017', 'capture-staged-early-v15-20261017'),
]
for variant in ('base','coarse650','coarse1301','frame2168','frame8666','pll1'):
    experiments.append((f'v16-{variant}-cold', f'capture-opt-v16-{variant}-cycle-01/cold',
                        f'capture-sweep-v16-20261017/{variant}-stage2',
                        f'capture-sweep-v16-20261017/{variant}-staged'))

ledger, visual, builds, source_status = [], [], {}, []
for name, capture, build, prefix in experiments:
    directory = BASE / capture
    timing_source = directory / ('events-analysis.json' if name == 'v3-ram' else 'timing.json')
    result_source = BASE / 'capture-opt-ram-rom-v3-image/capture-result.json' if name == 'v3-ram' else directory / 'ram/capture-result.json'
    logic = directory if name == 'v3-ram' else directory / 'logic'
    timing = json.loads(timing_source.read_text(encoding='utf-8-sig'))
    result = json.loads(result_source.read_text(encoding='utf-8-sig'))
    manifest = json.loads((BASE / build / 'manifest.json').read_text())
    if result.get('build_sha256') != manifest['raw_sha256']:
        raise ValueError(f'Build attribution mismatch: {name}')
    summary = summarize_documents(timing, result)
    summary.update(experiment_id=name, capture_dir=capture,
                   build_manifest=f'builds/{build}/manifest.json',
                   prefix_manifest=f'builds/{prefix}/manifest.json' if prefix else None)
    rail = logic / 'rail-validation.json'
    summary['rail_validation'] = json.loads(rail.read_text()) if rail.exists() else None
    ledger.append(summary)
    dest = Path('captures') / name
    copy(timing_source, dest / 'timing.json')
    copy(result_source, dest / 'ram/capture-result.json')
    for filename in ('digital.csv', 'capture-config.json', 'boot-summary.json', 'rail-validation.json'):
        source = logic / filename
        if source.exists():
            copy(source, dest / 'logic' / filename)
    for build_dir in (build, prefix):
        if build_dir and build_dir not in builds:
            path = BASE / build_dir / 'manifest.json'
            builds[build_dir] = json.loads(path.read_text())
            copy(path, Path('builds') / build_dir / 'manifest.json')
    visual.append(dict(experiment_id=name,
                       status='not reviewed' if name == 'v9-cold' else 'LED grid discernible',
                       reviewer='root bench controller',
                       provenance='Root controller assertion in delegated archive request; no image inspection by archiving agent.',
                       source_result_sha256=digest(result_source.read_bytes()),
                       raw_result_visual_field_preserved=True))

# Preserve the build-declared sources only when their bytes still match. Content
# addressing avoids copying identical vendor files for every experiment.
for build, manifest in builds.items():
    for path, expected in manifest.get('sources', {}).items():
        source = ROOT / path
        record = dict(build=build, source=path.replace('\\','/'), expected_sha256=expected)
        if not source.exists():
            record['status'] = 'missing'
        else:
            data = source.read_bytes()
            actual = digest(data)
            record['current_sha256'] = actual
            if actual != expected:
                record['status'] = 'changed since build; historical bytes not archived'
            else:
                object_path = Path('source-objects') / (expected + source.suffix.lower())
                if not (DEST / object_path).exists():
                    copy(source, object_path)
                record.update(status='verified exact bytes archived', archive=str(object_path).replace('\\','/'))
        source_status.append(record)

publish(DEST.parent / '.gitattributes', b'# Preserve byte-exact archived hashes across Git checkouts.\n** -text\n')
copy(Path(__file__).resolve(), Path('archive-script.py'))
json_publish(DEST / 'archive-index.json', dict(schema=1, scope='Through v16; interim, later experiments excluded.', files=records))
json_publish(DEST / 'source-provenance.json', source_status)
json_publish(DEST / 'visual-review.json', dict(date='2026-10-17', reviews=visual))
json_publish(DEST / 'ledger.json', dict(schema=1, time_unit='us', experiments=ledger))
print(json.dumps(dict(experiments=len(ledger), files=len(records), copied_bytes=sum(r['bytes'] for r in records),
                      changed_sources=[r for r in source_status if r['status'] != 'verified exact bytes archived']), indent=2))
