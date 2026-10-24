"""Extend the explicit RAW-slot evidence selection, offline and byte-exact.

No device modules are imported. Only this evidence folder is written. Files are
content addressed and optionally zlib compressed; superseded indexes survive as
immutable snapshots. Add completed records/builds in selection.json, never glob
an active bench into the archive. Scene pixels are excluded by default.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
TEXT = {'.c', '.h', '.s', '.ld', '.py', '.json', '.jsonl', '.md', '.txt', '.log'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def sha_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for raw in iter(lambda: stream.read(4*1024*1024), b''):
            digest.update(raw)
    return digest.hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode()


def put(raw):
    digest = sha(raw)
    compressed = zlib.compress(raw, 9)
    use_zlib = len(compressed) + 16 < len(raw)
    data = compressed if use_zlib else raw
    rel = 'objects/' + digest + ('.zlib' if use_zlib else '.bin')
    dest = HERE / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.read_bytes() != data:
        raise ValueError('Immutable object changed: ' + rel)
    if not dest.exists():
        dest.write_bytes(data)
    return dict(path=rel, encoding='zlib' if use_zlib else 'identity',
                sha256=digest, bytes=len(raw), stored_sha256=sha(data), stored_bytes=len(data))


def preserve(path):
    raw = path.read_bytes()
    record = put(raw)
    if path.suffix.lower() in TEXT:
        record.update(crlf_sequences=raw.count(b'\r\n'),
                      bare_lf_sequences=raw.count(b'\n')-raw.count(b'\r\n'),
                      normalized=False)
    return record


def root_path(value):
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    path.relative_to(ROOT)
    return path


def is_pixels(name):
    return (name in ('frame.bin', 'payload-padded.bin', 'sectors.bin', 'snapshots.bin')
            or bool(re.fullmatch(r'frame-[0-9a-f]+\.bin', name)))


def is_metadata_sector(raw):
    return (len(raw) == 512 and raw[:8] in (b'GXRWVOL1', b'GXRAWSL1')
            and int.from_bytes(raw[508:], 'little') == zlib.crc32(raw[:508]))


def collect_record(folder, selected):
    files, omitted = {}, {}
    for path in sorted(folder.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts:
            continue
        name = path.name
        rel = path.relative_to(folder).as_posix()
        metadata = rel in selected.get('metadata_sectors', [])
        if metadata and not is_metadata_sector(path.read_bytes()):
            raise ValueError('Selected metadata sector is not a CRC-valid RAW header')
        reason = None
        if path.suffix.lower() in ('.sal', '.jls', '.csv', '.png', '.jpg', '.jpeg'):
            reason = 'image preview or instrument recording excluded'
        elif is_pixels(name) and selected.get('pixels', 'omit') != 'pattern' and not metadata:
            reason = 'scene/unspecified pixel payload excluded'
        elif re.fullmatch(r'frame-[0-9a-f]+\.bin', name):
            reason = 'duplicate segmented RAM read; complete pattern frame retained'
        elif name.startswith('cli-') and not selected.get('keep_cli'):
            reason = 'repeated debugger text; calls and binary proofs retained'
        elif re.fullmatch(r'proof-\d+\.bin', name):
            reason = 'intermediate progress poll; final proof retained'
        elif path.suffix.lower() in ('.o', '.elf', '.lst', '.map'):
            reason = 'build intermediate excluded'
        elif (path.stat().st_size > 65536 and selected.get('pixels', 'omit') != 'pattern'
              and rel not in selected.get('keep_files', [])):
            reason = 'large unspecified payload excluded'
        if reason:
            omitted[rel] = dict(bytes=path.stat().st_size, sha256=sha_file(path), reason=reason)
        else:
            files[rel] = preserve(path)
    # Explicit small text attachments can preserve console/diagnostic records
    # saved beside, rather than inside, the selected operation directory.
    for name, source in selected.get('attachments', {}).items():
        if (not name or '/' in name or '\\' in name or ':' in name
                or name in ('.', '..')):
            raise ValueError('Unsafe attachment name')
        path = root_path(source)
        if path.suffix.lower() not in TEXT or path.stat().st_size > 4*1024*1024:
            raise ValueError('Attachment must be bounded text evidence')
        rel = 'attachments/' + name
        if rel in files or rel in omitted:
            raise ValueError('Repeated attachment name')
        files[rel] = preserve(path)
    return dict(source=folder.relative_to(ROOT).as_posix(),
                classification=selected['classification'], pixels=selected.get('pixels', 'omit'),
                capture=selected.get('capture'), metadata_sectors=selected.get('metadata_sectors', []),
                files=files, omitted=omitted)


def collect_build(folder):
    m = json.loads((folder / 'manifest.json').read_bytes())
    files = {}
    for name, expected in m['source_hashes'].items():
        path = (folder / name).resolve()
        path.relative_to(folder)
        item = preserve(path)
        if item['sha256'] != expected:
            raise ValueError('Frozen source differs: ' + str(path))
        files[name] = item
    for name in ('capture.bin', 'manifest.json', 'symbols.txt', 'raw-late.json', 'offline-review.json'):
        if (folder / name).exists():
            files[name] = preserve(folder / name)
    if files['capture.bin']['sha256'] != m['binary_sha256']:
        raise ValueError('Build binary differs: ' + str(folder))
    # Later cold builds can include their complete stage-one recovery image.
    staged = folder / 'staged'
    if staged.exists():
        pm = json.loads((staged / 'manifest.json').read_bytes())
        for source, expected in pm['sources'].items():
            name = Path(source).name
            item = preserve(staged / name)
            if item['sha256'] != expected:
                raise ValueError('Frozen prefix source differs: ' + name)
            files['staged/' + name] = item
        for name in ('manifest.json', 'stage1.bin', 'stage1_boot.bin', 'stage2.bin',
                     'stage2-full.bin', 'capture_sector_0.bin', 'symbols.txt'):
            if (staged / name).exists():
                files['staged/' + name] = preserve(staged / name)
        if files['staged/capture_sector_0.bin']['sha256'] != pm['program_sha256']:
            raise ValueError('Cold sector identity differs')
    return dict(source=folder.relative_to(ROOT).as_posix(), files=files)


def add_reference(index, folder):
    prior = json.loads((folder / 'index.json').read_bytes())
    item = prior['tools']['experiment/verify_decode.py']
    raw = (folder / item['path']).read_bytes()
    if sha(raw) != item['sha256']:
        raise ValueError('Independent decoder differs')
    index['tools']['verify_decode.py'] = dict(**put(raw),
        provenance='Prior packed-RAW archive: experiment/verify_decode.py')
    p = prior['pattern_payloads']['native-pattern02']
    compressed = (folder / p['compressed']['path']).read_bytes()
    raw = zlib.decompress(compressed)
    if (sha(compressed) != p['compressed']['sha256'] or sha(raw) != p['raw_sha256']
            or len(raw) != p['raw_bytes']):
        raise ValueError('Independent native16 pattern reference differs')
    index['native16_reference'] = dict(**put(raw),
        provenance=str(folder.relative_to(ROOT)) + ':native-pattern02',
        pixels=len(raw)//2)


def collect(selection):
    bench = root_path(selection['bench'])
    index = dict(schema=1, byte_preservation=True, line_ending_normalization=False,
                 selection=selection, records={}, builds={}, tools={}, limits=selection['limits'])
    builds = {}
    for selected in selection['records']:
        name = selected['id']
        folder = root_path(selected.get('source', str(bench / name)))
        if not folder.is_dir():
            raise ValueError('Selected record missing: ' + name)
        if selected.get('pixels') == 'pattern':
            origin = bench / selected.get('capture', name)
            verified = json.loads((origin / 'verified.json').read_bytes())
            if verified['proof']['pattern'] != 1 or not verified.get('frame_sha256'):
                raise ValueError('Pattern payload lacks capture provenance: ' + name)
            if sha((origin / 'frame.bin').read_bytes()) != verified['frame_sha256']:
                raise ValueError('Pattern frame hash differs: ' + name)
        if name in index['records']:
            raise ValueError('Repeated record id: ' + name)
        index['records'][name] = collect_record(folder, selected)
        for path in folder.rglob('plan.json'):
            plan = json.loads(path.read_bytes())
            if plan.get('build'):
                build = root_path(plan['build'])
                builds[str(build)] = build
    for value in selection.get('extra_builds', []):
        folder = root_path(value)
        builds[str(folder)] = folder
    for folder in builds.values():
        name = folder.name
        if name in index['builds']:
            raise ValueError('Build basename collision: ' + name)
        index['builds'][name] = collect_build(folder)
    for name, value in selection['tools'].items():
        path = root_path(value)
        if not path.exists():
            raise ValueError('Selected tool missing: ' + str(path))
        index['tools'][name] = dict(**preserve(path), provenance='Archive-time source snapshot')
    add_reference(index, root_path(selection['reference_archive']))
    return index


def save_index(index):
    path = HERE / 'index.json'
    if path.exists():
        previous = path.read_bytes()
        dest = HERE / 'indexes' / (sha(previous) + '.json')
        dest.parent.mkdir(exist_ok=True)
        if not dest.exists():
            dest.write_bytes(previous)
    path.write_bytes(json_bytes(index))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection', type=Path, default=HERE/'selection.json')
    args = parser.parse_args()
    index = collect(json.loads(args.selection.read_bytes()))
    save_index(index)
    objects = list((HERE / 'objects').glob('*'))
    print(json.dumps(dict(records=len(index['records']), builds=list(index['builds']),
        unique_objects=len(objects), stored_bytes=sum(p.stat().st_size for p in objects)), indent=2))


if __name__ == '__main__':
    main()
