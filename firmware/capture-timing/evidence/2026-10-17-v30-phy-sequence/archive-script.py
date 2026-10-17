"""Plan or publish byte-exact PHY-sequencing evidence from an explicit JSON list.

No instrument access. Defaults to validation only; --write publishes immutable
files after every source, attribution and destination has been checked.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

DEST = Path(__file__).resolve().parent
ROOT = DEST.parents[3]
EVIDENCE = DEST.parent
sys.path.insert(0, str(ROOT / 'firmware/capture-timing'))
from summarize import summarize_documents


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2) + '\n').encode('utf-8')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def repo_path(value):
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError(f'Source escapes repository: {value}')
    return path


def short(path):
    return str(path.relative_to(ROOT)).replace('\\', '/')


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', value):
        raise ValueError(f'Invalid experiment/build identifier: {value!r}')
    return value


class Plan:
    def __init__(self):
        self.pending = {}
        self.files = {}

    def add(self, relative, data, source=None, shared=False):
        relative = Path(relative)
        path = (DEST / relative).resolve()
        boundary = EVIDENCE.resolve() if shared else DEST.resolve()
        if not path.is_relative_to(boundary):
            raise ValueError(f'Archive destination escapes boundary: {relative}')
        if len(data) > 2_000_000:
            raise ValueError(f'Unexpected large evidence file: {source or relative}')
        if path.exists() and path.read_bytes() != data:
            raise ValueError(f'Refusing different overwrite: {path}')
        if path in self.pending and self.pending[path] != data:
            raise ValueError(f'Conflicting planned bytes: {path}')
        if shared and not path.exists():
            raise ValueError(f'Shared object does not exist: {path}')
        if not shared:
            self.pending[path] = data
        if source is not None:
            key = str(relative).replace('\\', '/')
            self.files[key] = dict(source=source, archive=key,
                                   bytes=len(data), sha256=digest(data))

    def copy(self, source, relative):
        self.add(relative, source.read_bytes(), short(source))

    def generated(self, relative, value):
        self.add(relative, encoded(value), 'derived by archive-script.py')

    def write(self):
        for path, data in self.pending.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                if path.read_bytes() != data:
                    raise ValueError(f'Destination changed after validation: {path}')
            else:
                with path.open('xb') as stream:
                    stream.write(data)


def shared_object(expected):
    for path in sorted(EVIDENCE.glob(f'*/source-objects/{expected}.*')):
        if digest(path.read_bytes()) == expected:
            return path
    return None


def sources_for(plan, builds):
    provenance = []
    for build_id, (directory, manifest) in builds.items():
        for name, expected in manifest.get('sources', {}).items():
            if not re.fullmatch(r'[a-fA-F0-9]{64}', expected):
                raise ValueError(f'Invalid source hash in {build_id}: {name}')
            source = repo_path(name)
            record = dict(build=build_id, source=name.replace('\\', '/'),
                          expected_sha256=expected)
            current = source.read_bytes() if source.exists() else None
            record['current_sha256'] = digest(current) if current is not None else None
            exact = current is not None and digest(current) == expected
            shared = shared_object(expected)
            if shared is not None:
                relative = Path('..') / shared.relative_to(EVIDENCE)
                plan.add(relative, shared.read_bytes(), short(shared), shared=True)
                record.update(status='verified exact bytes archived',
                              archive=str(relative).replace('\\', '/'),
                              current_source_matches=exact)
            elif exact:
                relative = Path('source-objects') / (expected + source.suffix.lower())
                plan.copy(source, relative)
                record.update(status='verified exact bytes archived', archive=str(relative).replace('\\', '/'),
                              current_source_matches=True)
            else:
                record['status'] = ('missing; historical bytes unavailable' if current is None
                                    else 'changed since build; historical bytes unavailable')
            provenance.append(record)
    return provenance


def copy_capture(plan, directory, logic, archive):
    # The compact raw records are retained even when no frame/timing was produced.
    for name in ('timing.json', 'events-analysis.json', 'analysis-note.json',
                 'diagnostic-analysis.json', 'phy-summary.json', 'offline-failure-summary.json',
                 'logic.log', 'cycle.log', 'bench.log'):
        path = directory / name
        if path.exists():
            plan.copy(path, archive / name)
    ram = directory / 'ram'
    if ram.exists():
        for path in sorted(ram.iterdir()):
            if path.is_file() and (path.suffix.lower() in ('.json', '.jsonl', '.log', '.txt')
                                  or path.suffix.lower() == '.bin' and path.name != 'frame.bin'):
                if path.suffix.lower() == '.bin' and path.stat().st_size > 65536:
                    raise ValueError(f'Unexpected RAM dump size: {path}')
                plan.copy(path, archive / 'ram' / path.name)
    for name in ('digital.csv', 'capture-config.json', 'boot-summary.json',
                 'rail-validation.json', 'powered-state.json'):
        path = logic / name
        if path.exists():
            plan.copy(path, archive / 'logic' / name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    config_path = repo_path(args.config)
    config = read_json(config_path)
    if config.get('schema') != 1 or not config.get('captures') or not config.get('builds'):
        raise ValueError('Configuration needs schema=1 and nonempty captures/builds lists')
    plan = Plan()
    builds = {}
    for item in config['builds']:
        name = identifier(item['id'])
        if name in builds:
            raise ValueError(f'Duplicate build: {name}')
        directory = repo_path(item['directory'])
        manifest = read_json(directory / 'manifest.json')
        builds[name] = directory, manifest
        plan.copy(directory / 'manifest.json', Path('builds') / name / 'manifest.json')
    ledger, visual = [], []
    ids = set()
    for item in config['captures']:
        name = identifier(item['id'])
        if name in ids or item['outcome'] not in ('completed', 'failed', 'partial'):
            raise ValueError(f'Duplicate id or invalid explicit outcome: {name}')
        ids.add(name)
        directory = repo_path(item['directory'])
        if not directory.is_dir():
            raise ValueError(f'Capture directory does not exist: {directory}')
        receiver_dir, receiver = builds[item['receiver_build']]
        prefix_dir, prefix = builds[item['prefix_build']]
        if prefix.get('stage2_sha256') != receiver.get('raw_sha256'):
            raise ValueError(f'Prefix/receiver payload attribution mismatch: {name}')
        expected_manifest = prefix.get('stage2_manifest_sha256')
        if expected_manifest and digest((receiver_dir / 'manifest.json').read_bytes()) != expected_manifest:
            raise ValueError(f'Receiver manifest bytes do not match prefix: {name}')
        entry = dict(experiment_id=name, outcome=item['outcome'],
                     outcome_note=item.get('outcome_note'), capture_dir=short(directory),
                     receiver_build=item['receiver_build'], prefix_build=item['prefix_build'],
                     summary=None, programming_verification='not supplied')
        archive = Path('captures') / name
        logic = repo_path(item['logic_directory']) if item.get('logic_directory') else directory / 'logic'
        copy_capture(plan, directory, logic, archive)
        timing_path, result_path = directory / 'timing.json', directory / 'ram/capture-result.json'
        result = read_json(result_path) if result_path.exists() else None
        if result is not None and result.get('build_sha256') != receiver['raw_sha256']:
            raise ValueError(f'RAM result/build attribution mismatch: {name}')
        if result is not None and timing_path.exists():
            try:
                entry['summary'] = summarize_documents(read_json(timing_path), result)
            except (ValueError, KeyError, TypeError) as error:
                entry['summary_unavailable_reason'] = str(error)
        else:
            entry['summary_unavailable_reason'] = 'Timing and/or RAM result absent; no timing inferred.'
        rail = logic / 'rail-validation.json'
        entry['rail_validation'] = read_json(rail) if rail.exists() else None
        cycle_value = item.get('programming_cycle_directory')
        if cycle_value:
            cycle = repo_path(cycle_value)
            for path in sorted(cycle.rglob('*')):
                relative = path.relative_to(cycle)
                if (path.is_file() and (relative.parts[0] in ('write', 'info', 'maintenance')
                                       or relative == Path('programmed-image.json'))
                        and (path.suffix.lower() in ('.json', '.jsonl', '.log', '.txt')
                             or path.suffix.lower() == '.bin' and path.name != 'readback.bin'
                             and path.stat().st_size <= 65536)):
                    plan.copy(path, archive / 'cycle' / relative)
            programmed_path, verified_path = cycle / 'programmed-image.json', cycle / 'write/verified.json'
            if programmed_path.exists() and verified_path.exists():
                programmed, verified = read_json(programmed_path), read_json(verified_path)
                if not (programmed['sha256'] == verified['sha256'] == prefix['program_sha256']
                        and verified.get('byte_for_byte_match') is True):
                    raise ValueError(f'Programmed image attribution mismatch: {name}')
                entry['programming_verification'] = 'full byte-for-byte readback matches prefix manifest'
            else:
                entry['programming_verification'] = 'supplied cycle lacks complete verification records'
        if item['outcome'] == 'completed' and not (
                entry['summary'] is not None and result.get('completed') is True
                and result.get('image_integrity_matches') is True
                and result.get('frames', 0) >= 1
                and entry['summary']['phases_us']['first_frame_complete'] is not None
                and entry['rail_validation']
                and entry['rail_validation'].get('passed') is True
                and entry['programming_verification'].startswith('full byte-for-byte')):
            raise ValueError(f'Completed capture lacks frame/timing/rails/programming qualification: {name}')
        review = item.get('visual_review')
        if review is not None:
            if not result or not all(review.get(k) for k in ('status', 'reviewer', 'provenance')):
                raise ValueError(f'Visual assertion requires result, status, reviewer and provenance: {name}')
            visual.append(dict(experiment_id=name, **review,
                               source_result_sha256=digest(result_path.read_bytes()),
                               raw_result_visual_field_preserved=True))
        else:
            visual.append(dict(experiment_id=name, status='not supplied; no visual success inferred'))
        ledger.append(entry)
    provenance = sources_for(plan, builds)
    # Explicit additional compact records (for example final power-release evidence).
    for item in config.get('extra_files', []):
        source = repo_path(item['source'])
        if source.suffix.lower() not in ('.json', '.jsonl', '.log', '.txt', '.csv', '.md', '.py', '.cfg'):
            raise ValueError(f'Unsupported extra-file type: {source}')
        plan.copy(source, Path('extra') / item['archive'])
    license_path = EVIDENCE / '2026-10-17-through-v16/license-index.json'
    for item in read_json(license_path)['files']:
        source = repo_path(item['source'])
        if digest(source.read_bytes()) != item['sha256']:
            raise ValueError(f'License source changed: {source}')
        plan.copy(source, Path(item['archive']))
    plan.copy(license_path, Path('license-index.json'))
    plan.copy(config_path, Path('archive-config.json'))
    plan.copy(Path(__file__).resolve(), Path('archive-script.py'))
    plan.generated('source-provenance.json', provenance)
    plan.generated('visual-review.json', dict(date=config.get('date'), reviews=visual))
    plan.generated('ledger.json', dict(schema=1, time_unit='us', experiments=ledger))
    # The index cannot include its own hash; all other generated records are indexed.
    plan.add('archive-index.json', encoded(dict(schema=1,
        scope=config.get('scope', 'Controlled receiver PHY sequencing diagnostics.'),
        files=list(plan.files.values()))))
    if args.write:
        plan.write()
    print(json.dumps(dict(mode='written' if args.write else 'validated; no files written',
        experiments=len(ledger), files=len(plan.files),
        bytes=sum(item['bytes'] for item in plan.files.values()),
        sources_unavailable=[item for item in provenance
                             if item['status'] != 'verified exact bytes archived']), indent=2))


if __name__ == '__main__':
    main()
