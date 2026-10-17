import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / 'tmp/bringup'
DEST = ROOT / 'firmware/capture-timing/evidence/2026-10-17-v28-temperature'
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
    ('v28-temperature-cold', 'capture-opt-v28-temperature-cycle-01/cold', 'capture-receiver-trim-v23-20261017', 'capture-temperature-prestart-v28-20261017'),
]

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
    programmed=json.loads((directory.parent/'programmed-image.json').read_text())
    verified=json.loads((directory.parent/'write/verified.json').read_text())
    image_manifest=json.loads((BASE/(prefix or build)/'manifest.json').read_text())
    if not (programmed['sha256']==verified['sha256']==image_manifest['program_sha256'] and verified['byte_for_byte_match']):
        raise ValueError(f'Programmed image attribution mismatch: {name}')
    summary.update(experiment_id=name, capture_dir=capture,
                   build_manifest=f'builds/{build}/manifest.json',
                   prefix_manifest=f'builds/{prefix}/manifest.json' if prefix else None)
    rail = logic / 'rail-validation.json'
    summary['rail_validation'] = json.loads(rail.read_text()) if rail.exists() else None
    ledger.append(summary)
    dest = Path('captures') / name
    copy(timing_source, dest / 'timing.json')
    copy(result_source, dest / 'ram/capture-result.json')
    for filename in ('trace-00.bin','events.bin','error-events.bin','prefix-status.bin'):
        source=directory/'ram'/filename
        if source.exists(): copy(source,dest/'ram'/filename)
    cycle=directory.parent
    for relative in ('programmed-image.json','write/verified.json','write/status.json','maintenance/result.json','info/status.json'):
        source=cycle/relative
        if source.exists(): copy(source,dest/'cycle'/relative)

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
                       status='LED grid discernible',
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
                shared=DEST.parent/'2026-10-17-v17-through-v24'/object_path
                if shared.exists() and digest(shared.read_bytes())==expected:
                    object_path=Path('../2026-10-17-v17-through-v24')/object_path
                elif not (DEST / object_path).exists():
                    copy(source, object_path)
                record.update(status='verified exact bytes archived', archive=str(object_path).replace('\\','/'))
        source_status.append(record)

publish(DEST.parent / '.gitattributes', b'# Preserve byte-exact archived hashes across Git checkouts.\n** -text\n')
license_source=ROOT/'firmware/capture-timing/evidence/2026-10-17-through-v16/license-index.json'
license_index=json.loads(license_source.read_text())
for license in license_index['files']:
    path=ROOT/license['source']
    assert digest(path.read_bytes())==license['sha256']
    copy(path,Path(license['archive']))
copy(license_source,Path('license-index.json'))
copy(Path(__file__).resolve(), Path('archive-script.py'))
json_publish(DEST / 'archive-index.json', dict(schema=1, scope='v28 temperature-read-before-configuration RAW8 diagnostic; not adopted into normal capture profile.', files=records))
json_publish(DEST / 'source-provenance.json', source_status)
json_publish(DEST / 'visual-review.json', dict(date='2026-10-17', reviews=visual))
json_publish(DEST / 'ledger.json', dict(schema=1, time_unit='us', experiments=ledger))
print(json.dumps(dict(experiments=len(ledger), files=len(records), copied_bytes=sum(r['bytes'] for r in records),
                      changed_sources=[r for r in source_status if r['status'] != 'verified exact bytes archived']), indent=2))
