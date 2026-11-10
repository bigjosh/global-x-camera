"""Offline compact 2.2-ohm campaign archive. Default validates/plans; --execute writes.

Run only after root finishes three cold image verifications and approves this
script. No instrument imports or commands. Root owns README/NOTES/AGENTS and
final-state files; this script never creates or replaces them. Native streams,
photos, frame data, SD sectors and other RAM dumps stay local, inventoried only.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DEST = REPO / 'docs/power/evidence/2026-11-06-series-resistor-tested'
BASELINE = HERE.parent / 'c17-removed-20261106'
BUILD = REPO / 'tmp/bringup/sensor-autostop-promote-20261028/design/read-helper'
STAGED = REPO / 'tmp/bringup/sensor-autostop-promote-20261028/flash-standby-v1/staged'
PREFIX = '6378483a91b560ffc6b31d74a9dd1205996a14c8030447ffddf7deddc9d23874'
READER = 'ef85e7106b3cb0cb253fe4a174e926a1bd227c006b7bfa46ab0433a1496ae000'
RUNS = tuple(f'cold-normal{i:02d}' for i in range(1, 4))
CHARTS = {'comparison.png', 'comparison.svg'}
REPORT_MARKDOWN = {'summary.md', 'timing-context.md'}
OWNED = {'README.md', 'NOTES.md', 'AGENTS.md', 'final-state.json'}


def need(ok, why):
    if not ok:
        raise ValueError(why)


def path(p, base=REPO):
    p = Path(p).resolve(strict=True)
    need(p.is_file() and p.is_relative_to(base), f'Outside file boundary: {p}')
    return p


def sha(p):
    with Path(p).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(p):
    return json.loads(path(p).read_text(encoding='utf-8-sig'))


def cid(card):
    return tuple(card[k] for k in ('sector_count', 'cid0', 'cid1', 'cid2', 'cid3'))


class Archive:
    def __init__(self):
        self.files, self.local = {}, {}

    def record(self, p):
        p = path(p)
        return dict(source=p.relative_to(REPO).as_posix(), bytes=p.stat().st_size, sha256=sha(p))

    def add(self, p, target=None, *, frozen=False):
        p = path(p)
        target = Path(target or p.relative_to(HERE))
        need(not target.is_absolute() and '..' not in target.parts and target.name not in OWNED,
             f'Invalid/root-owned destination: {target}')
        need(p.stat().st_size < 8*1024*1024, f'Artifact unexpectedly large: {p}')
        need(frozen or p.suffix in {'.json', '.jsonl', '.log', '.py', '.csv'} or
             (p.parent == HERE/'comparison-report' and p.name in CHARTS | REPORT_MARKDOWN),
             f'Artifact not permitted for copying: {p}')
        key = target.as_posix()
        value = dict(self.record(p), destination=key)
        need(key not in self.files or self.files[key] == value, f'Archive collision: {key}')
        self.files[key] = value

    def private(self, p, expected=None, size=None, reason='Local payload, not copied'):
        value = self.record(p)
        need(expected is None or value['sha256'] == expected, f'Payload hash differs: {p}')
        need(size is None or value['bytes'] == size, f'Payload size differs: {p}')
        self.local[value['source']] = dict(value, reason=reason)

    def reference(self, ref, *, private=False):
        p = path(ref['path'])
        need(sha(p) == ref['sha256'], f'Bound evidence changed: {p}')
        if private:
            self.private(p, ref['sha256'])
        elif p.is_relative_to(HERE):
            self.add(p)
        else:
            self.add(p, 'references/' + p.relative_to(REPO).as_posix())
        return p


def check_read(p, slot_lba, count, identity):
    v = read(p)
    need(v.get('passed') is True and v.get('binary_sha256') == READER, f'Bad READ: {p}')
    expected = dict(operation=3, state=3, result=0, sd_error=0, media_idle=1,
                    initialized=0, controller_owned=0, cleanup_error=0,
                    written_sectors=0, formatted_slots=0, read_lba=slot_lba,
                    read_count=count, read_bytes=count*512, clock_hz=25000000,
                    card_write_lo=0, card_write_hi=0, card_read_lo=count, card_read_hi=0)
    need(all(v['proof'].get(k) == n for k, n in expected.items()), f'READ scope differs: {p}')
    need(cid(v['card']) == identity, f'Card identity differs: {p}')
    return v


def validate_trace(a, folder, target):
    report = read(folder/'analysis.json')
    trace = Path(report['trace']).resolve()
    need(trace.is_relative_to(folder.resolve()), 'Trace is outside its run')
    result = read(trace/'result.json')
    need(result.get('success') is True and result.get('mode') == 'cold-normal' and
         result.get('on_range') == 1 and not result.get('errors') and not result.get('cleanup_errors'),
         f'Incomplete fixed10A cold recording: {folder}')
    need(result['initial_settings'] == result['restored_settings'] and result['final_power_range'] == 128,
         'Instrument settings not restored')
    need(result['proof']['prefix_sha256'] == PREFIX, 'Wrong cold-cycle firmware prefix')
    recorder = folder.parent/'record_startup.py'
    need(sha(recorder) == result['source_sha256'], 'Recorded recorder source changed')
    a.reference(result['proof'])
    need(sha(trace/'result.json') == report['result_sha256'] and
         sha(trace/'chunks.jsonl') == report['source_index_sha256'], 'Trace/analysis bindings differ')
    need(report['marker_decode']['unique_complete_train'] is True and
         {e['id'] for e in report['marker_decode']['events']} == set(range(1, 12)) and
         report['external_exposure_mirror']['complete_envelopes'] == 1 and
         report['gpio_interpretation']['explicit_remapping'] is True,
         'Require11markers, one exposure envelope, and explicit observed GPI roles')
    for name, suffix in [('current', 'f32'), ('voltage', 'f32'), ('power', 'f32'),
                         ('gpi0', 'u1'), ('gpi1', 'u1'), ('current_range', 'u8')]:
        a.private(trace/f'{name}.{suffix}', result['sha256'][name], result['bytes'][name],
                  'Native instrument stream; local only')
    a.private(trace/'chunks.jsonl', reason='Native chunk/sample index; local only')
    for p in (folder/'analysis.json', trace/'result.json', trace/'events.jsonl'):
        a.add(p, target + '/' + p.relative_to(folder).as_posix())
    return report


def prepare():
    a = Archive()
    allocation = read(HERE/'allocation-capture/verified.json')
    p = allocation['proof']
    need(allocation.get('passed') is True and allocation['binary_sha256'] == READER,
         'Fresh warm allocation capture incomplete')
    need(all(p.get(k) == v for k, v in dict(operation=1, state=3, result=0, sd_error=0,
         media_idle=1, controller_owned=0, initialized=0, cleanup_error=0,
         written_sectors=3730, frames=1, errors=0).items()) and p['scan_headers'] == p['slot']+1,
         'Warm allocation capture did not prove a fresh linear scan')
    identity = cid(allocation['card'])
    expected = list(range(p['slot']+1, p['slot']+4))
    # Root first read slots172/173/174, then175/176. Occupied earlier slots
    # remain evidence; select only the three expected fresh slots for this gate.
    header_summaries = [read(HERE/'before-headers/summary.json'),
                        read(HERE/'remaining-headers/summary.json')]
    scr = header_summaries[0]['scr_source']
    need(scr['erased_byte'] in (0, 255) and cid(scr['card_identity']) == identity,
         'SCR/capacity identity differs')
    need(a.reference(scr['proof']) == (HERE/'allocation-capture/verified.json').resolve(),
         'SCR must bind this fresh allocation capture')
    a.reference(scr['scr_binary'], private=True)
    observed = {}
    for before in header_summaries:
        need(before.get('passed') is True and before.get('one_sector_per_slot') is True and
             before.get('read_sectors') == len(before['slots']) and before['scr_source'] == scr,
             'Invalid pre-cycle header scan')
        for item in before['slots']:
            need(item['slot'] not in observed, 'Duplicate pre-cycle slot proof')
            observed[item['slot']] = item
            data = a.reference(item['data'], private=True)
            proof = a.reference(item['proof'])
            check_read(proof, item['slot']*3730, 1, identity)
            if item['slot'] in expected:
                need(item['header']['state'] == 'FREE' and item['header']['occupied'] is False,
                     'Measured slot was not FREE before boot')
                need(data.read_bytes() == bytes([scr['erased_byte']])*512,
                     'FREE sector not entirely erased')
    need(all(slot in observed for slot in expected), 'Missing three expected pre-cycle FREE proofs')
    summary = read(HERE/'images/summary.json')
    need(summary.get('passed') is True and [v['slot'] for v in summary['slots']] == expected,
         'Three cold saved images not yet fully verified')
    for item in summary['slots']:
        validation = a.reference(item['validation'])
        v, slot = read(validation), item['slot']
        need(v['slot'] == slot and all(v.get(k) is True for k in
             ('passed', 'full_slot_read', 'full_payload_read', 'start_magic_valid',
              'completion_marker_valid', 'png_samples_match_read_raw')), 'Image validation incomplete')
        need(v['bytes'] == 1909600 and v['slot_bytes'] == 1909760 and v['scr_source'] == scr and
             v['original_sensor_frame_comparison'] is False, 'Cold image extent/provenance changed')
        for artifact in v['artifacts']:
            a.reference(artifact, private=True)
        a.private(validation.parent/'slot.bin', v['slot_sha256'], 1909760)
        a.private(validation.parent/'frame.bin', v['raw_sha256'], 1909600)
        a.private(validation.parent/'scene.png', v['png_sha256'])
        combined = hashlib.sha256()
        for off in range(0, 3730, 512):
            folder = validation.parent/f'payload-{off:04d}'
            count = min(512, 3730-off)
            vr = check_read(folder/'verified.json', slot*3730+off, count, identity)
            data = folder/'sectors.bin'
            a.private(data, vr['read_sha256'], count*512)
            combined.update(data.read_bytes())
        need(combined.hexdigest() == v['slot_sha256'], 'Full assembled image differs from chunk reads')
    for run in RUNS:
        validate_trace(a, HERE/run, run)
        validate_trace(a, BASELINE/run, 'baseline/'+run)
    comparison = read(HERE/'comparison-report/summary.json')
    need(len(comparison['rows']) == 6 and comparison['groups'] == ['No resistor', '2.2 ohms'],
         'Three-versus-three comparison incomplete or groups unexpected')
    need(comparison['source_script_sha256'] == sha(HERE/'analyze_comparison.py') and
         comparison['verifier_sha256'] == sha(BASELINE/'report/compare_c17.py'),
         'Comparison source or verifier changed')
    for group in comparison['groups']:
        need([r['run'] for r in comparison['rows'] if r['group'] == group] == list(RUNS),
             'Comparison run identities differ')
        need(all(r.get('eleven_phase_markers') and r.get('one_exposure_mirror')
                 for r in comparison['rows'] if r['group'] == group), 'Incomplete marker qualification')
    for source in comparison['sources']:
        need(sha(path(source['analysis_path'])) == source['analysis_sha256'],
             'Comparison analysis source changed')
    timing = read(HERE/'comparison-report/timing-context.json')
    need(timing['summary_sha256'] == sha(HERE/'comparison-report/summary.json'),
         'Timing context does not match this comparison')
    # The root writes final-state after image readbacks and the final bench action.
    # Requiring it prevents accidental archiving while the campaign is still live.
    final_state_path = path(HERE/'final-state.json')
    need(isinstance(read(final_state_path), dict), 'Root final-state record missing or invalid')
    # Compact metadata/control logs only; no recursive dependency/build copying.
    # Every binary from this campaign remains hash-only, including upload copies.
    for f in sorted(HERE.rglob('*')):
        if not f.is_file() or any(x in {'__pycache__', '.matplotlib', '.pytest_cache', 'self-check-report'} for x in f.parts):
            continue
        if f.name in OWNED or 'final-state' in f.name:
            continue
        if f.name == 'chunks.jsonl' or f.suffix in {'.bin', '.f32', '.u1', '.u8', '.jls'}:
            a.private(f)
        elif f.suffix in {'.png', '.svg'}:
            if f.parent == HERE/'comparison-report' and f.name in CHARTS:
                a.add(f)
            else:
                a.private(f, reason='Image/private graphical payload; local only')
        elif f.suffix in {'.json', '.jsonl', '.log', '.py', '.csv'} or \
                (f.parent == HERE/'comparison-report' and f.name in REPORT_MARKDOWN):
            a.add(f)
    # Freeze a single copy of the selected small executables and their manifests.
    need(sha(BUILD/'capture.bin') == READER and sha(STAGED/'stage1.bin') == PREFIX,
         'Frozen executable identity changed')
    for folder, names, target in (
        (BASELINE, ('record_startup.py', 'analyze_inrush.py', 'analyze_swapped.py'), 'support/baseline'),
        (BASELINE/'report', ('compare_c17.py',), 'support/baseline/report'),
        (BUILD, ('capture.bin', 'manifest.json', 'runtime.c', 'sd_card.c', 'sd_card.h'), 'support/read-helper'),
        (STAGED, ('stage1.bin', 'manifest.json'), 'support/current-prefix'),
        (REPO/'tmp/bringup/sd-fourbit-20261024', ('magic_readback.py',), 'support'),
        (REPO/'firmware/raw-slots', ('magic_slots.py', 'raw_slots.py'), 'support/codec'),
        (REPO/'firmware/capture-raw', ('bench.py',), 'support')):
        for name in names:
            a.add(folder/name, target+'/'+name, frozen=True)
    manifest = dict(schema=1, campaign_local_date='2026-11-06',
        generated_utc=datetime.now(timezone.utc).isoformat(), measured_slots=expected,
        warm_allocation_slot=p['slot'], installed_prefix_sha256=PREFIX, reader_binary_sha256=READER,
        nominal_series_resistance_ohms=2.2,
        root_final_state_source=dict(path=str(final_state_path),sha256=sha(final_state_path)),
        archived_files=sorted(a.files.values(), key=lambda x:x['destination']),
        excluded_local_payloads=sorted(a.local.values(), key=lambda x:x['source']),
        limits=['Warm allocation capture uses the earlier explicit-STOP RAM helper; excluded from cold-cycle metrics.',
                'Cold image RAM is lost in Standby: full readback/independent decoding does not prove original-frame equality.',
                'Native startup extrema and source-side voltage remain instrument observations, not independently qualified DUT transients.',
                'Source-side voltage does not establish DUT input droop or downstream rail-ramp compliance.',
                'No matched fresh resistor-removal A/B; SD service time can confound total-energy changes.',
                'Nominal I-squared-R heat is not independently measured incremental source energy.',
                'Root-owned README/NOTES/AGENTS/final-state files are excluded from this generated hash inventory.',
                'Local paths in evidence retain original provenance; image/sector/native-stream bytes are not published.'])
    return a, manifest


def write(a, manifest):
    need(DEST.resolve().is_relative_to(REPO/'docs/power/evidence'), 'Bad destination')
    generated = {'archive-manifest.json', '.gitattributes', 'SHA256SUMS'}
    need(not any((DEST/x).exists() for x in set(a.files) | generated), 'Archive collision; no overwrite')
    for r in a.files.values():
        need(sha(REPO/r['source']) == r['sha256'], 'Source changed after validation')
    DEST.mkdir(parents=True, exist_ok=True)
    hashes = []
    for r in manifest['archived_files']:
        blob = (REPO/r['source']).read_bytes()
        need(hashlib.sha256(blob).hexdigest() == r['sha256'], 'Concurrent source change')
        dst = DEST/r['destination']; dst.parent.mkdir(parents=True, exist_ok=True)
        with dst.open('xb') as stream:
            stream.write(blob)
        need(sha(dst) == r['sha256'], 'Copy mismatch')
        hashes.append((r['destination'], r['sha256']))
    for name, blob in {'.gitattributes': b'# Preserve exact hash-bound evidence bytes.\n* -text\n',
                       'archive-manifest.json': (json.dumps(manifest, indent=2, allow_nan=False)+'\n').encode()}.items():
        with (DEST/name).open('xb') as stream:
            stream.write(blob)
        hashes.append((name, hashlib.sha256(blob).hexdigest()))
    with (DEST/'SHA256SUMS').open('xb') as stream:
        stream.write(''.join(f'{h}  {n}\n' for n, h in sorted(hashes)).encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    a, manifest = prepare()
    if args.execute:
        write(a, manifest)
    print(json.dumps(dict(validated=True, executed=args.execute, destination=str(DEST),
         measured_slots=manifest['measured_slots'], files=len(a.files),
         bytes=sum(r['bytes'] for r in a.files.values()), hash_only_files=len(a.local)), indent=2))


if __name__ == '__main__':
    main()
