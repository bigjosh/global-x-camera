"""Offline, fail-closed compact archive for the November 5 C14-removed campaign.

No instrument modules, commands, network, or firmware operations. All measurements
remain byte-identical. Raw streams and private image/sector payloads are inventoried
by hash only. Default is a read-only validation/plan; --execute creates the archive.
Run only after root has finished the three-image verification and reviewed this file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
DEST = REPO / 'docs/power/evidence/2026-11-05-c14-removed'
PREFIX = '6378483a91b560ffc6b31d74a9dd1205996a14c8030447ffddf7deddc9d23874'
READER = 'ef85e7106b3cb0cb253fe4a174e926a1bd227c006b7bfa46ab0433a1496ae000'
RUNS = ('run01', 'run02', 'run03')
CHARTS = {
    'startup-current-charge.png', 'startup-current-charge.svg',
    'startup-250us-current-charge.png', 'startup-250us-current-charge.svg',
    'startup-source-voltage.png', 'startup-source-voltage.svg',
    'new-cycles-current-phases.png', 'new-cycles-current-phases.svg',
    'active-current-anomaly.png', 'active-current-anomaly.svg',
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def inside(path, root=HERE):
    path = Path(path).resolve(strict=True)
    require(path.is_relative_to(root.resolve()), f'Outside permitted source: {path}')
    require(path.is_file(), f'Not a regular file: {path}')
    return path


def read(path):
    return json.loads(inside(path).read_text(encoding='utf-8-sig'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def info(path):
    path = inside(path, REPO)
    return {'source': path.relative_to(REPO).as_posix(),
            'bytes': path.stat().st_size, 'sha256': sha(path)}


class Archive:
    def __init__(self):
        self.files = {}
        self.private = {}

    def add(self, source, target=None):
        source = inside(source, REPO)
        target = target or source.relative_to(HERE).as_posix()
        target = Path(target)
        require(not target.is_absolute() and '..' not in target.parts, 'Bad archive path')
        require(target.name not in {'README.md', 'NOTES.md', 'AGENTS.md'}, 'Root-owned file')
        require(source.suffix in {'.json', '.jsonl', '.csv', '.py'} or
                source.name in CHARTS, f'Not an allowed compact artifact: {source}')
        require(source.stat().st_size < 8 * 1024 * 1024, f'Unexpectedly large artifact: {source}')
        key = target.as_posix()
        record = dict(info(source), destination=key)
        require(key not in self.files or self.files[key] == record, f'Destination collision: {key}')
        self.files[key] = record
        return record

    def optional(self, relative):
        if (HERE / relative).is_file():
            return self.add(HERE / relative)

    def exclude(self, source, expected=None, size=None, reason='Private payload; hash only'):
        source = inside(source)
        record = info(source)
        if expected is not None:
            require(record['sha256'] == expected, f'Hash mismatch: {source}')
        if size is not None:
            require(record['bytes'] == size, f'Length mismatch: {source}')
        record['reason'] = reason
        self.private[record['source']] = record
        return record

    def proof_bundle(self, folder):
        for name in ('plan.json', 'proof.json', 'verified.json'):
            path = folder / name
            if path.is_file():
                self.add(path)


def validate_park(path):
    value = read(path)
    require(value.get('passed') is True, f'Recovery failed: {path}')
    require(value.get('prefix_sha256') == PREFIX, f'Wrong recovery prefix: {path}')
    require(value.get('context', {}).get('PC') == 0x3418078C, f'Wrong recovery PC: {path}')
    vcp = value.get('vcp_status', {})
    require(vcp.get('good_pulses', 0) >= 3 and vcp.get('bad_pulses') == 0,
            f'UART train not qualified: {path}')


def identity(card):
    return tuple(card.get(k) for k in ('sector_count', 'cid0', 'cid1', 'cid2', 'cid3'))


def validate_read(path, lba, count, card_identity):
    value = read(path)
    p = value['proof']
    require(value.get('passed') is True and value.get('binary_sha256') == READER,
            f'Wrong or failed read helper: {path}')
    for key, expected in dict(operation=3, state=3, result=0, sd_error=0,
            media_idle=1, initialized=0, controller_owned=0, cleanup_error=0,
            written_sectors=0, formatted_slots=0, read_lba=lba,
            read_count=count, read_bytes=count*512, clock_hz=25000000,
            card_write_lo=0, card_write_hi=0).items():
        require(p.get(key) == expected, f'Read proof {key} mismatch: {path}')
    require(identity(value['card']) == card_identity, f'Card identity mismatch: {path}')
    return value


def bind_reference(archive, reference, private=False):
    path = inside(reference['path'])
    require(sha(path) == reference['sha256'], f'Bound reference changed: {path}')
    if private:
        archive.exclude(path, reference['sha256'])
    else:
        archive.add(path)


def prepare(args):
    archive = Archive()
    comparison = args.comparison.resolve(strict=True)
    images = args.images.resolve(strict=True)
    require(comparison.is_relative_to(HERE) and images.is_relative_to(HERE),
            'Comparison and image directories must be within this campaign')

    for name in ('devices-preflight.json', 'owners-preflight.json', 'preflight.json',
                 'park-current01.json', 'park-current02.json'):
        archive.add(HERE / name)

    for run in RUNS:
        trace = HERE / run / 'trace'
        result = read(trace / 'result.json')
        require(result.get('success') is True and result.get('mode') == 'cold-normal',
                f'Incomplete/non-normal recording: {run}')
        require(result.get('on_range') == 1 and not result.get('errors') and
                not result.get('cleanup_errors'), f'Range or recording errors: {run}')
        require(result.get('final_power_range') == 128 and
                result.get('initial_settings') == result.get('restored_settings'),
                f'Settings not restored: {run}')
        require(result['proof']['prefix_sha256'] == PREFIX, f'Wrong preflight prefix: {run}')
        bind_reference(archive, result['proof'])
        archive.add(trace / 'result.json')
        archive.add(trace / 'events.jsonl')
        for key, suffix in {'current': 'f32', 'voltage': 'f32', 'power': 'f32',
                            'gpi0': 'u1', 'gpi1': 'u1', 'current_range': 'u8'}.items():
            archive.exclude(trace / f'{key}.{suffix}', result['sha256'][key],
                            result['bytes'][key], 'Raw instrument stream; local only')
        archive.exclude(trace / 'chunks.jsonl', reason='Detailed sample/chunk metadata; local only')
        park = HERE / run / 'park/result.json'
        validate_park(park)
        archive.add(park)
        archive.add(HERE / run / 'recovery/uart-events.json')

    # Initial recovery and abandoned preliminary attempt are retained as history,
    # without promoting the preliminary capture into an image-readback claim.
    for rel in ('park-initial/result.json', 'recovery-initial/uart-events.json',
                'before-run01/park/result.json', 'before-run01/recovery/uart-events.json',
                'allocation-capture/plan.json', 'standby-flags/result.json',
                'standby-flags/prior-park-result.json',
                'standby-flags/park-check/result.json'):
        archive.optional(rel)
    archive.proof_bundle(HERE / 'allocation-capture-live')
    archive.proof_bundle(HERE / 'postcycles-read-entry')

    alloc = read(HERE / 'allocation-capture-live/verified.json')
    p = alloc['proof']
    require(alloc.get('passed') is True and alloc.get('binary_sha256') == READER,
            'Fresh allocation capture did not pass')
    for key, expected in dict(operation=1, state=3, result=0, sd_error=0,
            media_idle=1, initialized=0, controller_owned=0, cleanup_error=0,
            written_sectors=3730, frames=1, errors=0).items():
        require(p.get(key) == expected, f'Allocation proof {key} mismatch')
    require(p['scan_headers'] == p['slot'] + 1, 'Allocation was not a fresh linear scan')
    card_identity = identity(alloc['card'])
    require(None not in card_identity, 'Missing card identity')
    expected_slots = list(range(p['slot'] + 1, p['slot'] + 4))

    before = read(HERE / 'before-headers/summary.json')
    require(before.get('passed') is True and before.get('read_sectors') == 3 and
            before.get('one_sector_per_slot') is True, 'Incomplete FREE header read')
    require([s['slot'] for s in before['slots']] == expected_slots, 'Wrong pre-cycle slots')
    erased_byte = before['layout']['erased_byte']
    require(erased_byte in (0, 255), 'Unknown erased byte')
    scr_source = before['scr_source']
    bind_reference(archive, scr_source['proof'])
    bind_reference(archive, scr_source['scr_binary'], private=True)
    require(scr_source['erased_byte'] == erased_byte and
            identity(scr_source['card_identity']) == card_identity,
            'SCR identity/erase status differs from fresh allocation capture')
    for item in before['slots']:
        require(item['header']['state'] == 'FREE' and item['header']['occupied'] is False,
                'A measured slot was not FREE before the cycles')
        bind_reference(archive, item['data'], private=True)
        require(Path(item['data']['path']).read_bytes() == bytes([erased_byte])*512,
                'FREE sector is not entirely erased')
        bind_reference(archive, item['proof'])
        validate_read(item['proof']['path'], item['header']['slot_lba'], 1, card_identity)
        archive.proof_bundle(HERE / 'before-headers' / f"slot-{item['slot']}")
    archive.add(HERE / 'before-headers/summary.json')
    archive.add(HERE / 'before-headers/scr-source.json')

    summary = read(images / 'summary.json')
    require(summary.get('passed') is True, 'Three-image readback is not complete')
    validations = sorted(images.glob('slot-*/readback-validation.json'))
    require(len(validations) == 3, 'Expected exactly three completed image validations')
    actual_slots = []
    for validation_path in validations:
        v = read(validation_path)
        slot = v['slot']
        actual_slots.append(slot)
        for key in ('passed', 'full_slot_read', 'full_payload_read', 'start_magic_valid',
                    'completion_marker_valid', 'png_samples_match_read_raw'):
            require(v.get(key) is True, f'{key} not qualified for slot {slot}')
        require(v.get('bytes') == 1909600 and v.get('slot_bytes') == 1909760,
                f'Wrong full image size for slot {slot}')
        require(v.get('original_sensor_frame_comparison') is False,
                'Cold-readback provenance unexpectedly changed; review before archiving')
        require(v.get('scr_source') == scr_source, f'SCR binding changed for slot {slot}')
        archive.add(validation_path)
        for artifact in v['artifacts']:
            bind_reference(archive, artifact, private=True)
        folder = validation_path.parent
        combined = hashlib.sha256()
        chunks = sorted(folder.glob('payload-*'))
        require(len(chunks) == 8, f'Expected eight read chunks for slot {slot}')
        for index, chunk in enumerate(chunks):
            offset = index * 512
            count = min(512, 3730-offset)
            require(chunk.name == f'payload-{offset:04d}', 'Noncontiguous image chunks')
            vr = validate_read(chunk / 'verified.json', slot*3730+offset, count, card_identity)
            data = chunk / 'operation/sectors.bin'
            if not data.exists():
                data = chunk / 'sectors.bin'
            archive.exclude(data, vr['read_sha256'], count*512)
            combined.update(data.read_bytes())
            archive.proof_bundle(chunk)
        require(combined.hexdigest() == v['slot_sha256'], f'Assembled slot mismatch: {slot}')
        archive.exclude(folder / 'slot.bin', v['slot_sha256'], 1909760)
        archive.exclude(folder / 'frame.bin', v['raw_sha256'], 1909600)
        archive.exclude(folder / 'scene.png', v['png_sha256'])
    require(sorted(actual_slots) == expected_slots, 'Readback slots differ from measured slots')
    archive.add(images / 'summary.json')
    archive.add(images / 'scr-source.json')

    comp = read(comparison / 'comparison.json')
    new_rows = [row for row in comp['rows'] if row['group'] == 'c14_removed']
    require([row['run'] for row in new_rows] == list(RUNS) and not comp['historical_only'],
            'Comparison does not contain all three new runs')
    require(comp.get('explicit_new_gpio_remapping') is True,
            'Current physical GPI remapping has not been explicitly analyzed')
    for file in comparison.iterdir():
        if file.name in CHARTS or file.name in ('comparison.json', 'comparison.csv') or \
                file.name.endswith('-analysis.json'):
            archive.add(file, 'analysis/' + file.name)
    # Original failed marker interpretation stays visible beside the corrected one.
    for rel in ('analysis/run01.json', 'analysis/run01-explicit-gpi-remap.json'):
        if (HERE / rel).is_file():
            archive.add(HERE / rel, 'analysis/original/' + Path(rel).name)

    # Root owns the interpretation. Preserve anomaly context even when it is a
    # failed/ambiguous diagnostic; its presence does not qualify an explanation.
    anomaly = HERE / 'active-anomaly-context'
    if anomaly.is_dir():
        for file in anomaly.iterdir():
            if file.suffix == '.json' or file.name in CHARTS:
                archive.add(file)
    if args.nor_directory:
        nor = args.nor_directory.resolve(strict=True)
        require(nor.is_dir() and nor.is_relative_to(HERE), 'NOR proof directory outside campaign')
        for file in nor.rglob('*'):
            if file.is_file() and file.suffix in {'.json', '.jsonl'}:
                archive.add(file)
            elif file.is_file() and file.suffix == '.bin':
                archive.exclude(file, reason='NOR/code/register proof bytes; local only, hash retained')

    for name in ('record_startup.py', 'analyze_inrush.py', 'test_record_startup.py',
                 'test_analyze_inrush.py'):
        archive.add(HERE.parent / name, 'support/' + name)
    for name in ('analyze_swapped.py', 'compare_c14.py', 'archive_c14.py',
                 'read_nor_identity.py', 'final_power_off.py'):
        archive.add(HERE / name, 'support/' + name)
    for name in ('final-off/result.json', 'final-off/park/result.json',
                 'final-recovery/uart-events.json', 'standby-flags/result.json',
                 'after-images/park/result.json'):
        archive.optional(name)
    archive.add(REPO / 'tmp/bringup/sd-fourbit-20261024/magic_readback.py',
                'support/magic_readback.py')
    if args.final_state:
        archive.add(inside(args.final_state), 'final-state.json')
    for file in HERE.glob('*final-state*.json'):
        archive.add(file)
    for file in args.extra_json:
        require(file.suffix == '.json', '--extra-json accepts only JSON metadata')
        archive.add(inside(file))

    manifest = dict(schema=1, campaign_local_date='2026-11-05',
        local_timezone='America/New_York', generated_utc=datetime.now(timezone.utc).isoformat(),
        measured_slots=expected_slots, preliminary_capture_slot=p['slot'],
        installed_prefix_sha256=PREFIX, reader_binary_sha256=READER,
        archival_policy='Exact source bytes; no raw streams, frame, scene or SD payload copied.',
        limits=[
            'UTC measurement timestamps remain unchanged; the campaign was November 5 local time.',
            'Preliminary allocation capture is not full image-readback qualification.',
            'Cold saved images have no retained original camera RAM for equality comparison.',
            'Original reversed GPI interpretation and explicit corrected mapping are both retained.',
            'Historical controls are not an isolated C14 A/B comparison.',
            'Native startup peaks and source-voltage transients remain physically unqualified.',
            'Normal cold-active current around 330 mA is not attributed or resolved here; this is not only a RAM-helper observation.',
            'Warm PHY IDs 0007/C131 were valid but BMCR 0/0 triggered BETH_BMCR7; that diagnostic does not identify the current anomaly cause.',
            'Current support source hashes do not prove those exact bytes executed earlier; compare source_sha256 in each measurement.',
            'SHA256SUMS covers this generated inventory and archival files only, not later root-authored README/NOTES.',
        ],
        archived_files=sorted(archive.files.values(), key=lambda x:x['destination']),
        excluded_local_payloads=sorted(archive.private.values(), key=lambda x:x['source']))
    return archive, manifest


def write_archive(archive, manifest):
    # Preflight every collision before creating the destination or any artifact.
    outputs = list(archive.files) + ['archive-manifest.json', 'SHA256SUMS', '.gitattributes']
    require(not any((DEST / rel).exists() for rel in outputs), 'Archive collision; no file overwritten')
    require(DEST.resolve().is_relative_to(REPO / 'docs/power/evidence'), 'Bad archive destination')
    for record in archive.files.values():
        source = inside(REPO / record['source'], REPO)
        require(sha(source) == record['sha256'], f'Source changed after validation: {source}')
    DEST.mkdir(parents=True, exist_ok=True)
    hashes = []
    for record in manifest['archived_files']:
        dest = DEST / record['destination']
        dest.parent.mkdir(parents=True, exist_ok=True)
        blob = (REPO / record['source']).read_bytes()
        require(hashlib.sha256(blob).hexdigest() == record['sha256'], 'Concurrent source change')
        with dest.open('xb') as stream:
            stream.write(blob)
        require(sha(dest) == record['sha256'], f'Copy mismatch: {dest}')
        hashes.append((record['destination'], record['sha256']))
    generated = {
        '.gitattributes': b'# Preserve exact hash-bound archival bytes in this subtree.\n* -text\n',
        'archive-manifest.json': (json.dumps(manifest, indent=2, allow_nan=False)+'\n').encode(),
    }
    for name, blob in generated.items():
        with (DEST / name).open('xb') as stream:
            stream.write(blob)
        hashes.append((name, hashlib.sha256(blob).hexdigest()))
    with (DEST / 'SHA256SUMS').open('xb') as stream:
        stream.write(''.join(f'{digest}  {name}\n' for name, digest in sorted(hashes)).encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comparison', required=True, type=Path)
    parser.add_argument('--images', required=True, type=Path)
    parser.add_argument('--final-state', type=Path)
    parser.add_argument('--nor-directory', type=Path,
                        help='Optional completed read-only NOR proof folder, metadata copied and binary hashes retained')
    parser.add_argument('--extra-json', type=Path, action='append', default=[],
                        help='Additional root-selected campaign metadata; repeatable')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    archive, manifest = prepare(args)
    if args.execute:
        write_archive(archive, manifest)
    print(json.dumps(dict(validated=True, executed=args.execute, destination=str(DEST),
        files=len(archive.files), archive_bytes=sum(r['bytes'] for r in archive.files.values()),
        excluded_local_payloads=len(archive.private), measured_slots=manifest['measured_slots']), indent=2))


if __name__ == '__main__':
    main()
