"""Archive completed RAW10 experiments offline, preserving exact source bytes.

Only this evidence directory is modified. No hardware modules are imported.
Sources, binaries and small logs are content-addressed; test-pattern payloads
are compressed losslessly. Scene payloads, raw readback chunks, object files,
ELFs and instrument captures are deliberately not copied.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile
import zlib

HERE = Path(__file__).resolve().parent
BUILDS = ('native10-diagonal-v3', 'native10-diagonal-v4',
          'opaque8-diagonal-v4', 'opaque8-scene-v4')
TOOL_NAMES = ('run_capture.py', 'analyze_raw.py', 'test_run_capture_audit.py',
              'register-audit.md', 'restore_normal.py', 'test_restore_audit.py')
EXPERIMENT_TOOLS = ('build.py', 'experiment.c', 'experiment.h', 'protocol.py',
                    'test_protocol.py', 'test_artifacts.py', 'verify_decode.py',
                    'README.md')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_bytes((json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8'))


def put(data, extension):
    digest = sha(data)
    rel = 'objects/' + digest + extension
    path = HERE / rel
    path.parent.mkdir(exist_ok=True)
    if path.exists() and path.read_bytes() != data:
        raise ValueError('Content-address collision: ' + rel)
    if not path.exists():
        path.write_bytes(data)
    return dict(path=rel, sha256=digest, bytes=len(data))


def text_identity(data, extension):
    if extension.lower() in ('.c', '.h', '.s', '.ld', '.py', '.json', '.md', '.txt', '.log', '.jsonl'):
        try:
            data.decode('utf-8')
            encoding = 'utf-8'
        except UnicodeDecodeError:
            encoding = 'opaque non-UTF8 bytes'
        return dict(encoding=encoding, crlf_sequences=data.count(b'\r\n'),
                    bare_lf_sequences=data.count(b'\n') - data.count(b'\r\n'),
                    normalized=False)
    return {}


def preserve(path):
    data = path.read_bytes()
    return dict(**put(data, path.suffix.lower()), **text_identity(data, path.suffix))


def zip_records(folder):
    kept, omitted = {}, {}
    for path in sorted(folder.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts:
            continue
        rel = path.relative_to(folder).as_posix()
        if path.name == 'frame.bin' or path.name.startswith('frame-') or path.suffix.lower() in ('.png', '.sal', '.jls', '.csv'):
            reason = 'pixel payload/readback duplicate or instrument capture omitted'
        elif path.suffix.lower() in ('.o', '.elf', '.lst', '.map'):
            reason = 'intermediate build object omitted'
        elif path.stat().st_size > 1_000_000:
            reason = 'large artifact omitted'
        else:
            reason = None
        data = path.read_bytes()
        item = dict(sha256=sha(data), bytes=len(data))
        if reason:
            omitted[rel] = dict(**item, reason=reason)
        else:
            kept[rel] = dict(**item, **text_identity(data, path.suffix))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for rel in kept:
            info = zipfile.ZipInfo(rel, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (folder / rel).read_bytes(), compresslevel=9)
    return dict(archive=put(buf.getvalue(), '.zip'), entries=kept, omitted=omitted)


def collect(source, include_final, extra=()):
    index = dict(schema=1, source_root=str(source), byte_preservation=True,
                 line_ending_normalization=False, builds={}, tools={}, records={},
                 pattern_payloads={}, limits=[
                     'Packed capture only; no SD streaming/DMA qualification.',
                     'Normal installed firmware was not replaced by these RAM experiments.',
                     'Scene pixel payloads are intentionally absent; scene records retain hashes.',
                     'External vendor header/toolchain closure is not duplicated; these records replay measurements, not a portable build environment.',
                     'PVT-wide behavior and alternative dimensions are not established.'])
    for name in BUILDS:
        folder = source / 'experiment' / name
        manifest = json.loads((folder / 'manifest.json').read_bytes())
        files = {}
        for filename, expected in manifest['source_hashes'].items():
            path = folder / filename
            record = preserve(path)
            if record['sha256'] != expected:
                raise ValueError('Frozen source hash changed: ' + str(path))
            files[filename] = record
        for filename in ('capture.bin', 'manifest.json', 'symbols.txt'):
            files[filename] = preserve(folder / filename)
        if files['capture.bin']['sha256'] != manifest['binary_sha256']:
            raise ValueError('Binary hash differs: ' + name)
        index['builds'][name] = dict(files=files,
            qualification='failed post-capture FP context cleanup' if name.endswith('v3') else 'see trial records')
    for name in TOOL_NAMES:
        index['tools'][name] = preserve(source / name)
    for name in EXPERIMENT_TOOLS:
        index['tools']['experiment/' + name] = preserve(source / 'experiment' / name)
    for path in sorted((source / 'experiment').glob('*.json')):
        index['tools']['experiment/' + path.name] = preserve(path)
    for path in sorted((source / 'experiment').glob('*.build.*.txt')):
        index['tools']['experiment/' + path.name] = preserve(path)
    for path in extra:
        if path.name in index['tools']:
            raise ValueError('Duplicate extra artifact name: ' + path.name)
        index['tools'][path.name] = preserve(path)

    bench = source / 'bench'
    index['bench_metadata'] = {}
    for path in sorted(bench.glob('*.json')):
        if path.name != 'js-response.json':
            index['bench_metadata'][path.name] = preserve(path)
    for folder in sorted(p for p in bench.iterdir() if p.is_dir()):
        complete = (folder / 'verified.json').exists()
        failed = folder.name in ('native-pattern01', 'native-v3-context-diagnostic')
        recovery = folder.name.startswith('recovery-vcp') or folder.name == 'early-park01'
        restoration = include_final and folder.name == 'restore-normal' and (folder / 'state.json').exists()
        if not (complete or failed or recovery or restoration):
            continue
        # A recovery folder is completed when the host produced its summary.
        if recovery and not any(folder.glob('*.json')):
            continue
        record = zip_records(folder)
        record['classification'] = ('completed trial' if complete else
            'failed experiment retained' if failed else
            'completed normal-boot restoration' if restoration else 'recovery record')
        if complete:
            verified = json.loads((folder / 'verified.json').read_bytes())
            record['verified'] = verified
            if verified.get('proof', {}).get('pattern') == 1 and verified.get('passed'):
                raw = (folder / 'frame.bin').read_bytes()
                if sha(raw) != verified['frame_sha256']:
                    raise ValueError('Frame hash changed: ' + folder.name)
                compressed = zlib.compress(raw, 9)
                index['pattern_payloads'][folder.name] = dict(
                    compressed=put(compressed, '.zlib'), raw_sha256=sha(raw),
                    raw_bytes=len(raw), mode=verified['proof']['mode'],
                    deterministic_sensor_pattern=True)
        index['records'][folder.name] = record
    if include_final:
        index['bench_session'] = {}
        for name in ('js-response.json', 'js-session.jsonl'):
            path = bench / name
            if path.exists():
                raw = path.read_bytes()
                index['bench_session'][name] = dict(
                    compressed=put(zlib.compress(raw, 9), '.zlib'),
                    raw_sha256=sha(raw), raw_bytes=len(raw),
                    **text_identity(raw, path.suffix))
    # All object hashes are verified by replay; old incremental snapshots remain
    # immutable and indexed even after the live runner or note advances.
    index['objects'] = {p.relative_to(HERE).as_posix(): dict(sha256=sha(p.read_bytes()), bytes=p.stat().st_size)
                        for p in sorted((HERE / 'objects').iterdir()) if p.is_file()}
    write_json(HERE / 'index.json', index)
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--extra', action='append', type=Path, default=[],
                        help='Additional completed offline note/report to preserve.')
    parser.add_argument('--final', action='store_true', help='Also freeze the completed bench session log.')
    args = parser.parse_args()
    index = collect(args.source.resolve(), args.final, args.extra)
    print(json.dumps(dict(builds=len(index['builds']), records=list(index['records']),
                          pattern_payloads=list(index['pattern_payloads']),
                          unique_objects=len(index['objects']),
                          object_bytes=sum(v['bytes'] for v in index['objects'].values())), indent=2))


if __name__ == '__main__':
    main()
